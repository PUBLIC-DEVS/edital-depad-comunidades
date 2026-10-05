# Edital 2026 — resumo consolidado para revisão do PR

## 1. Objetivo

Este projeto substitui o fluxo operacional de análise baseado em planilhas por uma aplicação web Django, multiusuário, configurável e auditável. A meta não é reproduzir uma planilha dentro do navegador: é permitir que Administração configure novos editais pela interface e que as equipes cadastrem, distribuam, analisem, revisem e classifiquem processos sem depender do Excel.

A branch feature/edital-2026 preserva a cadeia de commits desde o início da plataforma, incluindo a productização, a adaptação da especificação 2026 e a remediação auditada da Fase 17.1. Ela parte do HEAD validado e09e64c3bb2e474acb923da77c7de7d277978d4d. A main permanece em 230ec63b49dffe4263ca4c8336216cf84d19aee8; nenhum merge foi realizado.

## 2. Escopo funcional

Um administrador pode criar, editar, validar, clonar e publicar editais por telas próprias. A configuração inclui:

- dados, status, datas, versão das regras e snapshot da configuração publicada;
- grupos/públicos, política de classificação e associação a programas e municípios;
- requisitos, subcritérios, ordem, obrigatoriedade, estados aceitos e comportamento de falha;
- evidências pertinentes a cada check, sem exibir campos irrelevantes;
- validators tipados com parâmetros persistidos na configuração;
- regras financeiras por tipo de vaga e percentual patrimonial quando requerido;
- instituições, processos e fonte de restrição pré-análise.

O fluxo operacional abrange intake manual e CSV, triagem e fila de exceções, distribuição individual/em lote, workspace de análise, revisão, diligência, snapshots de ranking, métricas e exportações CSV. Alterações ordinárias entre editais são dados de configuração; uma política nova que não pertença ao conjunto de políticas e validators disponíveis ainda pode exigir implementação e versionamento deliberados. Não existe engine de regras arbitrárias.

## 3. Especificação do Edital 2026

Análise Edital 2026.xlsx foi tratado como especificação funcional da coordenação, não como uma base operacional histórica. Seu conteúdo foi traduzido em configuração Django. Nenhum fluxo novo abre o arquivo, consulta fórmulas ou depende dele em runtime.

A base configurada contém 14 blocos documentais e 23 checks decisórios:

1. Anexo I — Requerimento de Participação;
2. Anexo II — Ficha Cadastral da Entidade;
3. Anexo III — Experiência Prévia da Entidade;
4. Estatuto, com sete checks;
5. SICAF de VI níveis;
6. Ata de eleição;
7. Comprovante de endereço da entidade;
8. Documentos do representante legal e endereço do representante;
9. Inscrição no CNPJ, idade e CNAE;
10. Alvará do Corpo de Bombeiros;
11. Alvará Sanitário;
12. Anexo IV — Programa Terapêutico;
13. Planta baixa;
14. Relatório fotográfico.

Os campos de evidência — como SEI, página, CNPJ, validade, data de abertura, CNAE e observação — aparecem por check conforme sua configuração. A apresentação é organizada em seções e cards, não em uma tabela de 81 colunas.

| Bloco | Decisões configuradas | Evidências/validações relevantes |
| --- | --- | --- |
| Anexo I | Requerimento atende? | SEI, página e observação. O CNPJ declarado é a identidade canônica da candidatura e exige confirmação explícita. |
| Anexo II | Ficha cadastral atende? | SEI, página e observação. |
| Anexo III | Experiência atende?; comprovação quando autodeclarada | SEI, página e observação; o segundo check permite N/A e é obrigatório quando aplicável. |
| Estatuto | Objetivos/finalidades; ausência de remuneração; natureza sem fins lucrativos; dissolução e destinação patrimonial; admissão/demissão/exclusão/direitos/deveres; mandato da diretoria; escrituração conforme NBC | SEI, páginas e observação em cada check. A experiência da coordenação deve confirmar eventual compartilhamento de evidências por bloco; isso está adiado em F17-07. |
| SICAF | SICAF de VI níveis atende? | CNPJ, validade, SEI, página e observação; CNPJ documental e data são validados automaticamente. |
| Ata de eleição | Vigência do mandato; registro em cartório | SEI, página e observação. |
| Endereço da entidade | Comprovante do local de acolhimento | CNPJ, SEI, página e observação; CNPJ comparado com o canônico. |
| Representante legal | CPF/RG/CNH; comprovante de endereço do representante | SEI, página e observação quando aplicável. |
| CNPJ | Inscrição com idade mínima | Data de abertura, CNAE, SEI, página e observação; validators de idade e CNAE usam parâmetros do edital. |
| Corpo de Bombeiros | Alvará atende? | CNPJ, validade, SEI, página e observação; verifica identidade e vigência. |
| Alvará Sanitário | Alvará atende? | CNPJ, validade, SEI, página e observação; verifica identidade e vigência. |
| Anexo IV | Programa Terapêutico atende? | SEI, página e observação. |
| Planta baixa | Assinatura por técnico habilitado (engenheiro/arquiteto) | CNPJ, SEI e página; CNPJ comparado com o canônico. |
| Relatório fotográfico | Relatório atualizado da unidade | SEI e página. |

Na configuração-base 2026, G1 recebe vagas femininas e mistas; a regra para mães nutrizes também foi configurada para G1, pendente de confirmação formal da coordenação. Vagas masculinas em município associado ao programa PRONASCI seguem para G2; vagas masculinas fora dessa associação seguem para G3. Sem vagas, o processo fica sem grupo e gera exceção. Os TargetGroups e associações de município-programa são dados administráveis; a fonte oficial PRONASCI continua pendente. O template 2026 não exige regra financeira porque a especificação não define valores financeiros.

### Anexo III

O check de comprovação documental é obrigatório quando aplicável, e permite Não Aplicável. Com os demais checks satisfeitos:

| Valor | Efeito |
| --- | --- |
| ATENDE | Satisfaz o check. |
| NÃO ATENDE | Resultado INAPTA e falha identificada. |
| NÃO APLICÁVEL | Satisfaz quando permitido pela configuração. |
| Pendente/em branco | Mantém EM ANÁLISE e impede concluir. |

Essa semântica foi corrigida após auditoria independente. O cálculo usa a configuração genérica de obrigatoriedade/status, sem regra especial por código Anexo III.

## 4. Triagem pré-análise

Fontes configuráveis de restrição de participação guardam CNPJ, motivo, origem, período de referência e estado ativo. Uma restrição aplicável bloqueia o processo antes da análise documental, impede avaliação normal e é exibida como exceção crítica. Desativar a fonte não reabre automaticamente processos antigos; Administração/Coordenação pode solicitar liberação formal, com justificativa, confirmação, ausência de outras restrições e trilha de auditoria.

Duplicidade é detectada por edital e CNPJ. Ela produz aviso e detalhe da candidatura anterior, mas não reprova automaticamente na configuração WARN_ONLY. A fila de exceções permite revisar restrições, duplicidades, CNPJ inválido e grupo pendente.

Cadastro manual e CSV usam SubmissionIntakeService para validar, classificar, verificar restrições, produzir alertas e registrar auditoria pelo mesmo pipeline. O CSV de intake é transacional por arquivo; linhas inválidas não são parcialmente aplicadas.

## 5. CNPJ canônico e recuperação

A fonte canônica da candidatura é submission.institution.cnpj; não existe CNPJ duplicado em Submission. O valor informado para documentos é comparado com essa identidade por validator. Divergência aparece como resultado de validação, sem substituição automática.

Administração/Coordenação dispõe de ação formal de correção com confirmação e motivo. A operação reassocia somente a candidatura a uma instituição de CNPJ correto, preservando a Institution compartilhada por outras candidaturas. Evaluation, CheckResults e CNPJs documentais são preservados; a confirmação canônica anterior é invalidada e os validators pertinentes são reavaliados. A operação registra ator, instante, identidade antiga/nova e motivo em AuditEvent. Correções não reescrevem decisões concluídas e não contornam restrição ativa do novo CNPJ durante a análise.

## 6. Validators

Validators são tipos fixos, implementados e testados em código; sua associação e seus parâmetros são configurados pela interface. Não há eval, exec ou Python arbitrário armazenado no banco.

| Validator | Evidência exigida no check |
| --- | --- |
| CNPJ_MATCH_CANONICAL | document_cnpj |
| DATE_NOT_EXPIRED | valid_until |
| CNPJ_MINIMUM_AGE | opened_on |
| CNAE_REQUIRED | cnae |

A publicação verifica dependências e parâmetros. A regra de idade recebe anos e data de referência; validade e idade não usam “hoje” como critério jurídico implícito. O CNAE esperado e o modo de comparação são dados configurados.

## 7. Workflow

Os estados operacionais reais incluem RECEIVED, ASSIGNED, UNDER_ANALYSIS, PENDING_REVIEW, PENDING_DILIGENCE, ELIGIBLE_FOR_RANKING, INELIGIBLE, RANKED e CLOSED.

Fluxo normal:

RECEIVED → ASSIGNED → UNDER_ANALYSIS

- avaliação APTA concluída → ELIGIBLE_FOR_RANKING, sem Review automática;
- avaliação INAPTA concluída → PENDING_REVIEW e Review pendente, inicialmente sem revisor;
- Review concluída como PRE_HABILITADO → elegível para ranking;
- Review concluída como PRE_INABILITADO → inelegível;
- diligência é um workflow próprio, ligado aos itens pertinentes, com resposta, prazo, responsável, conclusão e retorno ao estágio aplicável;
- geração de ranking cria snapshot; somente inscrições elegíveis recebem posições.

EM_ANALISE não pode ser concluída. Revisão exige claim explícito, revisor distinto do analista e decisão para todos os itens impeditivos.

## 8. RBAC

As permissões são verificadas no servidor, nas views, services e seletores de objetos; ocultar links no template não é controle de acesso.

| Papel | Capacidades principais |
| --- | --- |
| ADMINISTRADOR | Configura/publica editais, administra catálogos e usuários, consulta dados globais, distribui, atua em revisão, gera ranking e executa operações formais de identidade/restrição. |
| COORDENADOR | Consulta visão global, distribui, atua em revisão, gera ranking e executa operações formais de identidade/restrição; não substitui o papel administrador para configuração estrutural. |
| DISTRIBUIDOR | Cadastra processos, intake CSV/manual, consulta processos globais e atribui/redistribui dentro das regras de workflow. |
| ANALISTA | Consulta e edita avaliações em rascunho dos processos atribuídos a si; não acessa ranking/métricas globais nem processo de outro analista. |
| REVISOR | Acessa a fila autorizada, assume revisão e edita apenas a revisão que lhe pertence após claim. |
| CONSULTA | Leitura global autorizada de processos, avaliações, ranking e métricas; não pode executar mutações. |

Views POST e permissões por objeto protegem avaliações, reviews, diligências, operações de CNPJ/liberação e exports. GETs de workspace e preview são somente leitura.

## 9. Audit trail

AuditEvent é append-only pelo ORM comum: instâncias não podem ser atualizadas/excluídas e o QuerySet protege update, delete e bulk_update. Os eventos registram ator, entidade, campo, valor antigo/novo, timestamp e metadados operacionais necessários.

O fluxo registra transições de workflow, distribuição, mudanças de campo em CheckResult, criação/claim/conclusão de Review, diligências, correção de CNPJ, liberação de restrição e geração de ranking. Metadados evitam incluir documentos ou segredos sem necessidade.

## 10. Ranking

Snapshots oficiais contêm apenas candidatos elegíveis nas políticas configuradas. Exclusões — como inelegibilidade, ausência de grupo ou supressão de duplicata conforme a política escolhida — são registradas separadamente e não recebem posição. Posições válidas são consecutivas dentro dos grupos.

RankingSnapshot e entradas são imutáveis pelo fluxo comum e read-only no Admin. Transições para RANKED usam o workflow auditado. A política de grupo é configurável/versionada; G1/G2/G3 não são a representação universal do domínio. Empates absolutos permanecem bloqueados sem política configurada.

## 11. Métricas

O reporting separa dimensões para evitar contar o mesmo processo como APTA e INAPTA na mesma métrica:

- Resultado inicial da análise: APTA, INAPTA, EM_ANALISE.
- Situação consolidada/workflow: revisão, habilitação/inabilitação, diligência, elegibilidade, classificação e encerramento conforme o estado atual.

Ranking, métricas globais e exports têm autorização server-side.

## 12. Fronteira do legado

legacy_import permanece isolado para migração, regressão e auditoria histórica. Não configura editais novos nem dirige intake, análise, classificação ou telas operacionais. O ciclo 2026 passou sem Excel e com ENABLE_LEGACY_IMPORT=false; a suíte correspondente executou 283 testes. Os 7 testes sintéticos do marcador legacy exercitam apenas o importador. O golden master histórico não recebe PASS quando o workbook real está ausente.

## 13. Segurança e integridade

- CSRF middleware do Django e rotas mutáveis POST-only;
- RBAC server-side e controles de acesso por objeto;
- exportação CSV neutraliza células que poderiam iniciar fórmulas;
- AuditEvent append-only, imutabilidade de snapshots e GETs sem mutação;
- operações críticas transacionais, com locks para identidade/restrições e constraints de unicidade do domínio, incluindo processo SEI por edital e uma Assignment ativa por Submission;
- sem credenciais de produção ou workbook privado no repositório.

## 14. Arquitetura e framework

O produto usa Django 5.2 LTS, PostgreSQL, Django Templates, HTMX e services de domínio num monólito modular. A arquitetura preserva limites por domínio sem adicionar uma SPA, microserviços, BPMN ou um motor que execute regras arbitrárias. As necessidades ordinárias conhecidas — configuração de requisitos, evidências, grupos, valores, municípios e parâmetros de validators tipados — são dados de configuração; novas semânticas estruturais podem receber políticas versionadas em código.

## 15. Testes e validação

Validação final da Fase 17.1 reproduzida localmente:

| Verificação | Resultado |
| --- | --- |
| Suíte completa | 295 passed, 2 skipped |
| ENABLE_LEGACY_IMPORT=false | 283 passed |
| pytest -m legacy | 7 passed |
| tests/regression/ | 66 passed |
| Coverage report anterior da mesma revisão | 84,28% |
| Ruff lint e format | PASS |
| Django system check | PASS |
| Migration check | PASS, nenhuma migration da Fase 17.1 |
| git diff --check | PASS |
| CI PostgreSQL 16 | PASS, run 36641868421 |

CI foi executada no SHA e09e64c3bb2e474acb923da77c7de7d277978d4d: suíte 295 passed, 2 deselected; lifecycle sem legado 1 passed. Os dois skips locais pertencem ao teste real que exige LEGACY_XLSX_PATH; ele permanece NOT_RUN e não confere paridade.

## 16. Auditorias independentes

As revisões independentes identificaram o check condicional do Anexo III, recuperação de identidade, intake desigual, liberação de bloqueio, compatibilidade validator/evidência, CEP não editável, CSV formula injection, alerta financeiro indevido e preview desalinhado. A remediação implementou regressões específicas e passou auditoria curta antes desta consolidação.

| Finding | Severidade original | Resultado |
| --- | --- | --- |
| F17-01 | Bloqueador | FIXED |
| F17-02 | Alto | FIXED |
| F17-03 | Médio | FIXED |
| F17-04 | Alto | FIXED |
| F17-05 | Alto | FIXED |
| F17-06 | Médio | FIXED |
| F17-07 | Médio | DEFERRED_TO_HOMOLOGATION |
| F17-08 | Médio | FIXED |
| F17-09 | Médio | FIXED |
| F17-10 | Baixo | FIXED |
| F17-11 | Médio | DEFERRED_PRE_HOMOLOGATION |

O último commit anterior a esta consolidação, e09e64c, contém a implementação validada. O commit de consolidação é documental.

## 17. Itens deliberadamente pendentes

F17-07 é uma decisão de UX sobre evidências compartilhadas no documento versus em cada check; foi adiado para homologação. F17-11 é otimização de queries, sem refactor nesta entrega.

Continuam decisões da coordenação, não bugs de código:

1. data oficial de referência para validade e idade do CNPJ;
2. CNAE exigido como único, principal ou presente entre os CNAEs;
3. política definitiva de prevalência quando há duplicidade;
4. confirmação formal de mães nutrizes no G1 para 2026;
5. fonte oficial dos municípios PRONASCI;
6. política de desempate absoluto.

## 18. Microsoft e autenticação

MicrosoftAuthAdapter é uma boundary/scaffold que recebe claims já decodificados; não implementa sozinho validação JWT/OIDC, login Entra nem integração SharePoint. Nesta cópia do repositório não foi encontrada branch separada com trabalho de autenticação: origin/login_test aponta para o mesmo commit que main (230ec63b49dffe4263ca4c8336216cf84d19aee8). Portanto AUTH_BRANCH=NONE_FOUND; nenhuma branch de autenticação foi incorporada ou apagada. Não se afirma que Microsoft/Entra esteja integrado.

## 19. Migrations

As fases anteriores introduziram migrations aditivas em accounts, audit, editais, evaluations, institutions, legacy_import, ranking, reviews e submissions. Os grupos de alterações cobrem publicação/versionamento, requisitos e validators, tipos de vaga/financeiro, grupos e municípios, metadados de importação, Review/Diligence, identidade institucional/CEP, restrições de participação, estados de ranking e constraints de Assignment/Submission. A lista completa versionada encontra-se em apps/*/migrations/. Na Fase 17.1 não foi necessária migration; makemigrations --check --dry-run não encontrou diferenças.

## 20. Status de revisão

READY_FOR_PR — esta classificação é de prontidão para revisão de código, não de aprovação jurídica ou readiness de produção. Ainda faltam homologação visual com usuários, staging e execução das decisões administrativas abertas. Autenticação institucional final também continua fora do escopo desta branch.

Base proposta do PR: main. Compare/head: feature/edital-2026. Não houve PR automático nem merge.
