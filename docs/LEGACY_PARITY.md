# Relatório e Harness de Paridade com a Planilha Excel Legada

Este documento registra a validação de paridade entre o sistema Django e o histórico operacional executado originalmente na planilha Excel do Edital DEPED/MDS.

---

## 1. Números de Referência do Edital Histórico

A auditoria da planilha legada consolidou o universo de **282 processos** distribuídos conforme as regras de enquadramento:

| Grupo de Enquadramento | Definição Operacional | Quantidade Esperada | Status no Django |
| :--- | :--- | :--- | :--- |
| **Grupo 1 (G1)** | Propostas contemplando Mulheres, Mães Nutrizes e/ou Gestantes (`vagas_femininas + vagas_maes_nutrizes > 0`) | **9** | Identificado rigorosamente |
| **Grupo 2 (G2)** | Vagas masculinas exclusivas em municípios prioritários integrantes do Programa **PRONASCI** | **34** | Identificado via tabela de municípios e convênios |
| **Grupo 3 (G3)** | Vagas masculinas exclusivas nos demais municípios (ampla concorrência) | **212** | Identificado rigorosamente |
| **Sem Grupo** | Inscrições sem vagas válidas solicitadas, pendentes ou zeradas | **27** | Quarentena / Pendência de saneamento |
| **TOTAL** | **Universo Total de Processos Protocolados** | **282** | **100% de paridade** |

---

## 2. Divergências Documentadas do Legado (Vulnerabilidades do Excel)

Durante a migração para o motor determinístico em Python/Django, foram catalogadas falhas sistemáticas inerentes ao uso de planilhas como sistema operacional:

### 2.1 Erros de Fórmulas e Referências Quebradas no Excel
1. **Fórmulas de Enquadramento `SE(E(...))` Quebradas por Inserção de Linhas:**
   - No Excel legada, a inserção manual de linhas intermediárias por diferentes analistas quebrava referências relativas das fórmulas de classificação, deixando proponentes elegíveis classificados como `#REF!` ou caindo silenciosamente no Grupo 3.
   - **Correção no Django:** O `ClassificationService` avalia cada linha a partir do modelo relacional com testes unitários exaustivos.

2. **Divergências de Nome de Município vs. PRONASCI:**
   - Variações ortográficas na digitação da planilha (ex: `São Luís` vs `Sao Luis`, espaços extras após o nome) faziam com que o `PROCV` não encontrasse o município na lista do PRONASCI, rebaixando inadvertidamente propostas do Grupo 2 para o Grupo 3.
   - **Correção no Django:** Comparação mandatória por Código IBGE de 7 dígitos (`Municipality.ibge_code`) e `ProgramMunicipality`.

3. **Sobrescrita Concorrente em Abas de Analistas:**
   - Edições simultâneas via SharePoint / Excel Online resultavam em sobrescrita de células de conferência documental sem trilha de auditoria.
   - **Correção no Django:** Isolamento rigoroso no backend (`RolePermissionPolicy`), bloqueio de edição por analistas não autorizados e histórico append-only em `AuditEvent`.

4. **Inconsistências de Parecer vs. Itens Reprovados:**
   - Na planilha, constatou-se a ocorrência de propostas com a célula de status final preenchida manualmente como "APTA", apesar de conterem "NÃO ATENDE" em requisitos eliminatórios da mesma linha.
   - **Correção no Django:** O `EvaluationService` calcula o status de aptidão de forma imperativa: se qualquer item obrigatório for `NAO_ATENDE` ou `NAO_ENVIADO`, o resultado é obrigatoriamente `INAPTA`. Adicionalmente, o painel de validações (`/metricas/validacoes/`) aponta qualquer discrepância residual.

---

## 3. Harness de Paridade Automatizado

O comando `manage.py import_legacy_edital` executa a leitura da planilha legada (ou do gerador sintético homologado), persistindo os dados e comparando os resultados agregados.

O teste automatizado:
```bash
pytest -m legacy
```
assegura que:
- O número total de 282 processos é recuperado integralmente.
- As contagens por grupo (G1=9, G2=34, G3=212, Sem Grupo=27) coincidem com precisão de 100%.
- A execução repetida do comando é estritamente idempotente (sem duplicação de submissões ou atribuições).
