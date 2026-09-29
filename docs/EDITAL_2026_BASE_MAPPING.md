# Mapeamento funcional da base do Edital 2026

Este documento traduz a planilha `Análise Edital 2026.xlsx` em configuração do produto. O arquivo foi tratado como especificação funcional: contém as abas `DISTRIBUIÇÃO`, `ANALISTA` e `REGRAS`, sem dados de processos e sem fórmulas relevantes para execução. Nenhuma operação runtime depende do workbook.

## Distribuição e triagem

| Campo ou regra descrita | Configuração no Django | Tela | Comportamento |
| --- | --- | --- | --- |
| Processo SEI nº | `Submission.processo_sei` | Novo processo / editar processo | Identidade única por edital. |
| Data de envio + horário | `Submission.received_at` | Novo processo / editar processo | Um timestamp de recebimento, informado pelo Distribuidor. |
| Razão social, CNPJ, endereço, CEP | `Institution.name`, `cnpj`, `address`, `postal_code` | Cadastro de processo / instituições | CNPJ é a candidatura declarada no Anexo I; divergências documentais são comparadas com este valor. |
| Município e UF | `Submission.municipality` → `Municipality.name/state` | Cadastro de processo / municípios | Associação canônica quando disponível. |
| Vagas adulto feminino, masculino e mães nutrizes | Campos `Submission.vagas_*` | Cadastro de processo | Não são replicados como colunas configuráveis por requisito. |
| Capacidade total | `Submission.capacidade_total` | Cadastro de processo | Validação de vagas continua no formulário. |
| Grupo | `TargetGroup`, `ClassificationPolicy` e `Submission.target_group_definition` | Grupos e política de classificação do edital | O grupo exibido é calculado e persistido com auditoria. |
| Analista | `Assignment` | Distribuição | Atribuição individual/em lote auditada. |
| CNPJ com contrato ativo | `ParticipationRestriction` | Processos → Exceções → Fontes de restrição contratual | Restrição ativa muda o workflow para inelegível antes da análise e impede atribuição/início. Fonte, período e motivo ficam registrados. |
| Mesmo CNPJ no mesmo edital | `Submission` + detector de anomalias | Fila de exceções | Alerta com SEI, recebimento, situação e analista da outra candidatura. A configuração de novos editais começa em `WARN_ONLY`; não reprova nem suprime candidatura automaticamente. |

## Grupos e enquadramento configurado para 2026

| Grupo | Nome configurado | Tipos / associação | Resultado esperado |
| --- | --- | --- | --- |
| G1 | Gênero Feminino | FEMININO e MÃES NUTRIZES | Vaga feminina ou de mãe nutriz vai para G1. A política de mistas prioriza G1 quando feminino e masculino aparecem juntos. |
| G2 | PRONASCI | MASCULINO + programa PRONASCI + município associado | Masculino em município cadastrado no programa. |
| G3 | Gênero Masculino | MASCULINO sem associação PRONASCI | Masculino fora do programa configurado. |
| — | Sem grupo | Sem vagas enquadráveis ou sem município do programa | Retorna `SEM_GRUPO` e aparece como exceção. |

Essa prioridade é uma configuração/política 2026. `TargetGroup` e `ClassificationPolicy` permitem outros códigos e grupos em novos editais. A base funcional não contém uma lista de municípios PRONASCI; a equipe deve cadastrá-la no CRUD de municípios/programas.

## Estrutura documental (fingerprint do template 2026)

O modelo declarativo contém 14 blocos e 23 checks. Todos os títulos, códigos, macroseções, obrigatoriedade, evidências, valores aceitos e validadores são registros editáveis pelas telas de Requisitos, Subcritérios e Validações Automáticas.

| Bloco | Checks | Evidências adicionais/validações |
| --- | ---: | --- |
| Anexo I — Requerimento de Participação | 1 | SEI, página, observação e confirmação explícita do CNPJ da candidatura. |
| Anexo II — Ficha Cadastral | 1 | SEI, página, observação. |
| Anexo III — Experiência Prévia | 2 | Comprovação condicional, obrigatória quando aplicável; aceita `NÃO APLICÁVEL`. `NÃO ATENDE` reprova e pendência impede conclusão. |
| Estatuto | 7 | Um check por alínea a–g; SEI, página e observação. |
| SICAF de VI níveis | 1 | CNPJ, validade, SEI, página; valida CNPJ e vigência. |
| Ata de eleição | 2 | Vigência do mandato e registro em cartório; SEI, página e observação. |
| Endereço da entidade | 1 | CNPJ, SEI, página; compara CNPJ canônico. |
| Representante legal | 2 | Identificação e endereço do representante; SEI, página e observação. |
| Inscrição no CNPJ | 1 | Data de abertura, CNAE, SEI, página; idade mínima configurada em 3 anos e CNAE especificado como `87.20-4-99`. |
| Corpo de Bombeiros | 1 | CNPJ, validade, SEI, página; valida CNPJ e vigência. |
| Alvará Sanitário | 1 | CNPJ, validade, SEI, página; valida CNPJ e vigência. |
| Anexo IV — Programa Terapêutico | 1 | SEI, página, observação. |
| Planta baixa | 1 | CNPJ, SEI, página; valida CNPJ canônico. |
| Relatório fotográfico | 1 | SEI e página. |

Resultado do teste de template: **14 requisitos e 23 checks**, sem acoplar o `EvaluationService` a esses totais.

## Validações tipadas

| Tipo | Dados comparados | Configuração 2026 |
| --- | --- | --- |
| `CNPJ_MATCH_CANONICAL` | CNPJ encontrado no documento vs. CNPJ canônico da candidatura | Crítico nos documentos com CNPJ. O Anexo I pede confirmação do valor cadastral; ele não é alterado automaticamente. |
| `DATE_NOT_EXPIRED` | Validade documental vs. `Edital.validation_reference_date` | SICAF, Bombeiros e Sanitário; bloqueia conclusão se ausente, inválida ou vencida. |
| `CNPJ_MINIMUM_AGE` | Data de abertura + anos configurados vs. data de referência | 3 anos para o CNPJ do edital 2026. |
| `CNAE_REQUIRED` | CNAE informado vs. valor e modo configurados | Preserva `87.20-4-99`; comparação foi deixada `UNRESOLVED` e em aviso até decisão formal. |

Não há `eval`, código fornecido por usuário, nem linguagem de regras. Datas usam apenas a data de referência do edital; o sistema não substitui uma data jurídica ausente por `hoje`.

## Operação pela interface

1. Admin cria o edital em `/admin-editais/` e informa dados, período, versão e data de referência decidida pela coordenação.
2. Admin cria grupos e política de classificação, requisitos e subcritérios, evidências/status aceitos, regras automáticas, financeiro se aplicável e associações de municípios aos programas.
3. A página do edital mostra validação/publicação e uma prévia somente leitura do formulário do analista.
4. Ao publicar, o sistema valida a configuração e preserva um snapshot versionado.
5. Distribuidor cadastra o processo; a triagem sinaliza restrições, duplicidade e ausência de grupo. Restrição ativa bloqueia atribuição e análise.
6. Analista atribuído inicia, preenche os cartões do workspace e conclui. O resultado é calculado no backend.
7. APTA segue para elegibilidade/classificação; INAPTA cria revisão sem responsável. Revisor assume explicitamente e revisa todos os itens impeditivos.

O seed `seed_edital_2026_base` é auxiliar de desenvolvimento. Ele não substitui as telas. Exige usuário administrador, datas de abertura/encerramento e deixa a data oficial de referência vazia se a coordenação ainda não a tiver definido.

## Correções da auditoria — Fase 17.1

- A fonte canônica é `submission.institution.cnpj`. Administração/Coordenação corrige formalmente uma candidatura, inclusive durante análise em rascunho, sem alterar a instituição compartilhada nem apagar evidências.
- A confirmação do Anexo I é invalidada após correção e deve ser feita novamente. Validators de CNPJ são reexecutados e o evento guarda identificadores/status, sem duplicar documentos.
- Manual e CSV usam `SubmissionIntakeService`: mesma classificação, triagem, warnings e auditoria; o CSV continua atômico por arquivo.
- Desativar uma fonte não reabre processos. A ação **Liberar bloqueio pré-análise**, com justificativa e confirmação, retorna a RECEIVED após todas as restrições cessarem, sem atribuição automática.
- Publicação e edição de validators verificam as evidências necessárias. CEP é editável no cadastro institucional; exports operacionais neutralizam fórmulas.
- A prévia e o assessment usam o mesmo selector de checks ativos. Edital sem financeiro não recebe alerta de valor global ausente.

Evidências compartilhadas por bloco (F17-07) e otimização do workspace (F17-11) permanecem adiadas. O ciclo automatizado é **HTTP integration lifecycle**, não teste de navegador.
