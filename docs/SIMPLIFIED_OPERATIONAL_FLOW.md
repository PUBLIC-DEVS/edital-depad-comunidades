# Fluxo operacional simplificado — DEPAD / MDS

## Escopo e rastreabilidade

Esta fase concentra a interface em um único edital operacional. O domínio continua
configurável: modelos, migrations, snapshots, importação histórica e auditoria
foram preservados. Classificação G1/G2/G3, fórmula de ranking, financeira,
duplicidade, restrições e correção de CNPJ não foram reimplementadas.

Base: `79d5fc199f8b98f12e114511b4f17d2af5b70602`, branch
`feature/edital-2026-simplified-flow`. A branch consolidada e `main` não recebem
estas alterações. Nenhuma migration é necessária.

O inventário anterior à implementação examinou `config/urls.py`, `config/views.py`,
as rotas/templates/selectors/services de editais, processos, avaliações, revisões,
ranking e reporting, a policy de papéis, os validadores e as transições de workflow.
Os principais pontos de intervenção foram:

| Área | Responsabilidade |
| --- | --- |
| `apps/editais/operational.py` | Resolver edital, erro operacional, retirada de rotas antigas |
| `config/views.py`, `templates/base.html` | Entrada e navegação por papel |
| `apps/submissions/selectors.py` | Tabela operacional compartilhada e filtros |
| `apps/evaluations/assessment.py`, `services.py`, `drafts.py` | Decisão humana, progresso e conclusão |
| `apps/reviews/services.py`, `views.py` | Status efetivos, justificativas e conclusão calculada |
| `apps/submissions/services/workflow.py` | Encaminhamento de inaptos e bloqueio de diligências |
| `apps/reporting/services/metrics.py`, `charts.py` | Agregações operacionais e gráficos |

## Um edital operacional

`get_operational_edital()` exige **exatamente um** `Edital.status == ACTIVE`.
Não escolhe o primeiro registro e não usa número, ano ou PK fixos.

Com zero ou mais de um edital ativo, as páginas operacionais retornam HTTP 503.
Administrador/Coordenador recebem a causa explícita; demais papéis recebem
orientação para contatar a coordenação. Nenhuma consulta substitui silenciosamente
essa configuração inválida.

Home, processos, minhas análises, revisão, indicadores, classificação e respectivas
exportações usam o edital operacional. Seletores e services internos podem continuar
recebendo um edital explícito para manutenção, testes e histórico. Acesso a detalhes
mantém as autorizações existentes para o processo/atribuição/revisão correspondente.

O cadastro e a importação CSV fixam o edital no servidor. Parâmetros de edital na
URL e tentativas de enviar outro edital pelo formulário não ampliam a operação.

## Papéis, entrada e navegação

| Papel | Navegação principal | Entrada |
| --- | --- | --- |
| Administrador | Início, Processos, Revisão, Classificação, Administração | Home operacional |
| Coordenador | Início, Processos, Revisão, Classificação, Administração | Home operacional |
| Distribuidor | Processos | Processos |
| Analista | Minhas Análises | `/minhas-analises/` |
| Revisor | Revisão | Fila de revisão |
| Consulta | Início, Processos, Classificação | Home operacional, leitura |

Analista não acessa a lista global de processos. O backend mantém as verificações
de papel, atribuição e titularidade; esconder menus não concede nem revoga sozinho
permissões. Consulta não cria processos, distribui, edita avaliações ou gera ranking.

Administração concentra usuários, instituições, municípios, restrições, importações
e conferência/auditoria. Configuração de editais e programas não são módulos da
operação. URLs antigas de configuração redirecionam Admin/Coord à Administração;
outros papéis recebem 403. Views/forms técnicos continuam no código, sem exposição
na URLconf de produção.

## Home e processos

A home mostra número/ano/nome do edital, seis indicadores e a tabela de processos.
`/processos/` usa a mesma apresentação e oferece as ações permitidas ao papel.

Colunas: SEI, recebimento, instituição, CNPJ, município/UF, vagas F/M/MN e
capacidade, grupo, analista, status e ações. Busca por SEI/CNPJ/instituição, filtros
de status, analista, grupo, município e UF; recebimento é a ordenação padrão.
Paginação de 25 registros preserva os filtros. Não existe seletor de edital.

No mobile, SEI/instituição/status ficam em destaque e os dados complementares
podem ser abertos por linha. Endereço completo permanece no detalhe.

## Análise documental

Minhas análises resume pendentes, em andamento e concluídas, com progresso,
resultado e última atualização. O workspace enumera os documentos e critérios na
ordem configurada no banco. A configuração-base 2026 contém **14 blocos/23 checks**;
esses números e IDs não são fixados na implementação da tela.

A ação principal é `ATENDE` ou `NAO_ATENDE`. `NAO_APLICAVEL` aparece apenas onde
configurado. Ausência documental deve ser registrada como `NAO_ATENDE`.
`NAO_ENVIADO` não é opção nova; um registro antigo aparece como “Não enviado
(histórico)”, permanece preservado e exige decisão atual para concluir.

Observação é opcional e visível. Campos documentais configurados ficam em
“Detalhes do documento”. Mudanças são salvas por HTMX, com feedback **Salvo**,
sem reload. Há salvamento explícito de fallback. A conclusão aguarda respostas
pendentes de salvamento; navegação com alterações ainda não salvas gera aviso.
Erros de campos são sinalizados com `aria-invalid`.

Progresso = quantidade de checks com resposta diferente de `EM_BRANCO` / total
de checks configurados. `NAO_APLICAVEL` conta como respondido. O indicador de
progresso não substitui a validação de conclusão: status histórico ou não permitido
pode exigir correção mesmo estando respondido.

Conclusão recalcula o parecer no backend:

- Obrigatório aplicável pendente: bloqueia e informa a quantidade.
- Obrigatórios aplicáveis satisfatórios: `APTA` → `ELIGIBLE_FOR_RANKING`.
- Obrigatório aplicável com falha: `INAPTA` → `PENDING_REVIEW`, criando Review.

O analista não escolhe o parecer. Falhas documentais não pulam a revisão em razão
do antigo `failure_behavior=MARK_INELIGIBLE` ou `NONE`.

### Anexo III e validadores

O check condicional preserva F17-01: quando aplicável, `ATENDE` satisfaz,
`NAO_ATENDE` falha e `EM_BRANCO` bloqueia. Quando não aplicável,
`NAO_APLICAVEL` satisfaz. A configuração permanece a autoridade da condição.

Antes desta fase, `EvaluationService.conclude_evaluation()` podia bloquear por
erros do motor automático. Agora CNPJ, validade, idade, CNAE e demais validadores
continuam avaliados e apresentados como alertas de apoio; **não substituem nem
bloqueiam silenciosamente o parecer humano**. Isso é uma mudança explícita de
produto, coberta por teste. As regras e configurações não foram removidas.
Bloqueios independentes de cadastro, financeira, permissão e workflow permanecem.

O workspace reaproveita definições/resultados e faz prefetch de checks/validadores.
O teste de 23 checks limita a renderização a 20 queries; a medição do browser smoke
registrou **9 queries** para o workspace completo.

## Revisão auditável

A fila mostra processo, instituição, analista, data, quantidade de “Não atende” e
status. O revisor assume a revisão conforme policy existente.

Todos os checks aparecem em ordem, inclusive os aprovados. Falhas originais são
destacadas. Cada item mostra o parecer original e os botões do revisor.
O usuário escolhe o status; o service deduz concordância/divergência:

- Mesmo status: `agrees_with_analyst=True`.
- Status diferente: `agrees_with_analyst=False`, `reviewer_status` e motivo obrigatório.

“Concordar/Divergir” não é uma etapa da interface. Alterações recebem badge discreto.
A revisão nunca altera `CheckResult`, analista, timestamp ou Evaluation concluída.
Substituir uma decisão de revisão registra seu conteúdo anterior e novo no
`AuditEvent`, incluindo justificativas e ator.

Status efetivo = `reviewer_status` de decisão divergente, ou status original quando
não houver alteração. A mesma avaliação de obrigatoriedade/aplicabilidade calcula
o resultado. Itens originalmente impeditivos precisam de conferência registrada.

O rodapé mostra “Resultado calculado: APTA/INAPTA”, observação final e “Finalizar
revisão”. Não há dropdown de parecer. Internamente APTA continua mapeado a
`PRE_HABILITADO` → elegível; INAPTA a `PRE_INABILITADO` → `INELIGIBLE`.
Não foi necessária migration de enum.

## Diligência desativada

Não há menu, botão, card, atalho, contador, KPI ou convite ao fluxo.
Todas as URLs antigas de diligências retornam **404**, inclusive POST.
`WorkflowService.open_diligence()` rejeita abertura e `transition()` rejeita destino
`PENDING_DILIGENCE`. Nenhum papel pode iniciar diligência pela operação.

Model, enums, campos, migrations, dados históricos e implementação técnica
anterior são preservados. Os templates antigos não têm rota operacional acessível.
Um processo em estado histórico fora das etapas atuais aparece com rótulo neutro
e continua incluído no total de inscrições; não é apresentado como ação disponível.

## Indicadores e gráficos

Os KPIs usam estado **atual do workflow**, sem confundir inaptidão do analista com
resultado final após revisão:

| KPI | Fórmula |
| --- | --- |
| Inscrições | Todas as Submission do edital operacional |
| Sem distribuição | `RECEIVED` sem Assignment ativo |
| Em análise | `ASSIGNED` + `UNDER_ANALYSIS` |
| Em revisão | `PENDING_REVIEW` |
| Aptas | `ELIGIBLE_FOR_RANKING` + `RANKED` |
| Inaptas / Inelegíveis | `INELIGIBLE` |

Registros encerrados/históricos fora dessas cinco etapas não são redistribuídos
artificialmente em categorias. O gráfico informa essa diferença e usa o total de
inscrições como denominador do percentual. Não há KPI de diligência nem percentual
de conclusão exibido sem contexto.

| Gráfico | Pergunta e semântica |
| --- | --- |
| Situação atual dos processos | Barras com quantidade e percentual por etapa atual |
| Carga de trabalho por analista | Barras horizontais: atribuições ativas, workflow em andamento e avaliações concluídas dessas atribuições |
| Distribuição por grupo | Barras por grupo configurado e “Sem grupo” |
| Itens com mais “Não atende” | Top 8 checks; processos distintos com parecer original NAO_ATENDE em avaliações concluídas |
| Inscrições recebidas ao longo do tempo | Linha por data de recebimento, por semana quando o período excede 90 dias |

Na carga, “Concluídos” significa trabalho do analista concluído; pode existir revisão
pendente. No top de falhas, uma reversão da revisão não apaga a constatação original;
essa legenda é explícita. Linha temporal só aparece com pelo menos 5 inscrições,
3 datas/períodos e sem prefixo `DEMO-` usado pelo seed. Isso evita apresentar a
cronologia artificial conhecida como insight; não é detector universal de dados fictícios.

Implementação: barras em HTML/CSS e linha em SVG nativo, com valores textuais,
tooltips e tabela temporal acessível. Números vêm de agregações do backend.
Não há interpolação de JSON em JavaScript, nova biblioteca/CDN ou pipeline Node.
Indicadores detalhados ficam acessíveis a partir da home, sem um módulo extra no menu.

## Validação e compatibilidade dos testes

`tests/integration/test_simplified_flow.py` caracteriza resolução de edital, papéis,
navbar, aposentadoria das rotas, diligência off, status, Anexo III, validadores de
apoio, reversões de revisão, preservação/auditoria, contagens de métricas, séries
temporais e queries. Fixtures controladas independem de `seed_demo`.

Classificação das falhas encontradas durante adaptação:

- **EXPECTED_PRODUCT_CHANGE**: diligência bloqueada, navbar curta, resultado de
  revisão derivado, validadores de apoio e métricas do workflow atual. Os testes
  anteriores foram substituídos por verificações da nova regra, sem apagar cobertura.
- **STALE_TEST**: fixtures sem edital ativo/revisor de publicação, assertions de
  terminologia e chamadas ao CRUD retirado. Fixtures foram publicadas pelo service
  auditado; `tests/technical_urls.py` expõe callbacks genéricos **somente nos testes
  de manutenção**, preservando cobertura sem reativar URLs de produção.
- **REGRESSION**: renderização de linha sem analista gerava erro de template. A
  condição foi corrigida e incluída no teste da tabela de inscrições sem distribuição.

Testes não devem compartilhar o mesmo banco de teste em execuções concorrentes.
Uma execução que colidiu com outra foi invalidada e refeita sequencialmente.
Os dois testes dependentes do XLSX real continuam pulados sem `LEGACY_XLSX_PATH`;
isso não estabelece paridade nova com a planilha histórica.

Browser smoke usa a configuração-base 14/23 em SQLite temporário e um container
separado. Home, processos, lista/workspace do analista, fila/detalhe da revisão,
classificação e indicadores foram verificados em 375, 768, 1024, 1280 e 1440 px.
Capturas 1440×900 e 375×812 são temporárias e não entram no Git. Também foram
exercitados autosave, conclusão pendente/apta, revisão de item aprovado/reprovado,
resultado derivado, estado vazio, navegação de Consulta e acesso proibido.

## Atenção à base de demonstração

A base Docker encontrada contém **DEMO-CRUD/2027, 2 blocos/3 checks**, não o
edital-base 2026. Ela foi preservada. O sistema mostra a configuração ativa real;
não transforma o demo em 14/23 nem escolhe outro edital por ano.

Os **14 blocos/23 checks** foram confirmados nos testes controlados e no ambiente
isolado do browser smoke. Para operação real com essa configuração, a coordenação
deve preparar/publicar o edital adequado pela manutenção técnica, resolver as
decisões documentadas em `EDITAL_2026_OPEN_DECISIONS.md` e assegurar exatamente
um ACTIVE. Esta fase não inventa data jurídica, lista PRONASCI ou dados de produção.


## Resultado da validação final

- Django system check: nenhum problema.
- `makemigrations --check --dry-run`: nenhuma alteração detectada.
- Ruff: todos os checks passaram.
- Pytest completo: **332 passed, 2 skipped, 0 failed**, em 200,62 segundos.
- `git diff --check`: sem erros.
- Browser desktop/mobile: telas sem overflow nas cinco larguras; fluxo de análise
  apta sem Review indevido e revisão apta preservando a falha original confirmados
  também no banco. Navegação por teclado alcança o link de pular para o conteúdo.

O ambiente manual temporário é `http://127.0.0.1:8001/`, container
`edital_simplified_smoke`, com SQLite separado. A operação principal continua em
`http://127.0.0.1:8000/` e seu PostgreSQL demonstrativo foi preservado.
O container temporário usa a branch montada e dados descartáveis; não é ambiente
de produção. Credenciais são fornecidas no relatório de entrega.
