# Homologação manual

Pré-requisitos: Git e Docker Desktop instalado e em execução. Não é necessário
Python/Node local, XLSX ou arquivos de outro desenvolvedor.

## 1. Clone

```bash
git clone --branch feature/edital-2026 \
  https://github.com/PUBLIC-DEVS/edital-depad-comunidades.git
cd edital-depad-comunidades
```

## 2. Bootstrap

```bash
./scripts/tester-bootstrap.sh
```

O script constrói/sobe Docker, aguarda PostgreSQL, aplica migrations, executa
`seed_homologation` e verifica Django e o serviço web. Pode ser executado novamente:
não duplica o dataset, redefine senhas, apaga volumes ou sobrescreve decisões.
Se já existir outro edital ativo, falha com mensagem clara e preserva o banco.
Use um ambiente local separado nesse caso; não remova seus dados para testar.

O seed é explícito e **LOCAL DEVELOPMENT ONLY**: exige `DEBUG=True` e
`AUTH_ADAPTER=local`. Nenhuma inicialização automática cria essas contas.

## 3. Acesse

[http://localhost:8000/](http://localhost:8000/)

O título identifica **EDITAL 2026 — HOMOLOGAÇÃO LOCAL (SINTÉTICO)**.
Instituições, CNPJs alfanuméricos, municípios e vínculos de programa são exemplos
gerados para teste, sem consulta a cadastros reais. Datas, gráfico temporal e lista
de municípios vinculados ilustram o funcionamento; não representam uma operação
real nem a lista oficial PRONASCI. Financeira usa a configuração-base sem regras
financeiras; este roteiro não homologa decisões jurídicas abertas.

## 4. Credenciais

Senha inicial de todos: **`Homolog.Edital#2026`**. Exclusivamente local, nunca produção.
Se você alterar a senha, uma nova execução do seed preservará a alteração.

| Perfil | Usuário |
| --- | --- |
| Administrador | `homolog.admin` |
| Coordenador | `homolog.coordenador` |
| Distribuidor | `homolog.distribuidor` |
| Analista | `homolog.analista` |
| Revisor | `homolog.revisor` |
| Consulta | `homolog.consulta` |

## 5. O que testar

| Perfil | Experiência esperada |
| --- | --- |
| Admin/Coord | Início, Processos, Revisão, Classificação, Administração |
| Distribuidor | Processos e distribuição |
| Analista | Somente Minhas Análises na navegação; workspace 14 documentos/23 checks |
| Revisor | Revisão, parecer original e decisão efetiva em qualquer check |
| Consulta | Início, Processos e Classificação, somente leitura |

Abra **Ver indicadores** na home para conferir os gráficos. Antes de qualquer
alteração, os KPIs são: **8 inscrições, 1 sem distribuição, 2 em análise,
1 em revisão, 3 aptas, 1 inapta**. Há grupos G1/G2/G3 e classificação inicial.

## 6. Fluxos críticos

| Processo sintético | Teste |
| --- | --- |
| `HOMOLOG-2026-001` | Distribuir o recebido sem analista |
| `HOMOLOG-2026-002` | Abrir 17/23; concluir bloqueia por pendência; mudar resposta e conferir autosave |
| `HOMOLOG-2026-003` | Analisar do início: 0/23; marcar todos aplicáveis ATENDE e concluir APTA |
| `HOMOLOG-2026-004` | Assumir revisão com 3 falhas e todos os 23 checks disponíveis |
| `HOMOLOG-2026-005/007/008` | Conferir aptas/classificadas em G1/G2/G3 |
| `HOMOLOG-2026-006` | Conferir INAPTA final e parecer original preservado |

1. Na análise, testar ATENDE/NÃO ATENDE, observação e detalhes colapsáveis.
2. No Anexo III, a comprovação autodeclarada aceita NÃO SE APLICA quando não for
   aplicável. Quando aplicável, ATENDE satisfaz, NÃO ATENDE falha e pendente bloqueia.
3. No processo 003, usar pelo menos um NÃO ATENDE para testar INAPTA → revisão,
   ou todos satisfatórios para testar APTA → classificação.
4. Na revisão do 004, mudar NÃO ATENDE → ATENDE: motivo obrigatório. Corrigir as
   três falhas permite resultado calculado APTA. Mudar também um ATENDE → NÃO
   ATENDE mantém INAPTA. O parecer original continua visível e não é sobrescrito.
5. Finalizar revisão sem dropdown de parecer. Gerar classificação como Admin/Coord
   e consultar/exportar o resultado; Consulta não pode gerar.
6. Conferir URLs diretas: Analista não acessa `/processos/`; Consulta não cria em
   `/processos/novo/`; `/diligencias/` retorna 404 para qualquer papel.
7. Testar desktop e mobile, teclado, status selecionados e feedback de salvamento.

Cada conclusão altera o dataset. Uma reexecução preserva seu trabalho; ela não
restaura os cenários iniciais.

## 7. O que NÃO deve aparecer

Diligência, Solicitar diligência, Configurar editais, Programas, Novo edital e
Duplicar edital. `/admin-editais/` leva Admin/Coord à Administração; demais perfis
não podem configurar por URL direta.

## 8. Como reportar problema

```text
Perfil:
URL:
Ação:
Esperado:
Obtido:
Tipo: visual / fluxo / permissão / dados / desempenho
Severidade: bloqueante / alta / média / baixa
Screenshot:
```

Inclua o processo sintético e, se possível, o SHA mostrado por `git rev-parse HEAD`.
Para logs: `docker compose logs --tail=100 web`. Para encerrar, use
`docker compose down`, que preserva o volume de dados.
