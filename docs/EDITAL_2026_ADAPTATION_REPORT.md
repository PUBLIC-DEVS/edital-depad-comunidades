# Relatório de adaptação — base do Edital 2026

## Escopo e revisão

- Branch: `feature/edital-2026-base-adaptation`
- Branch base: `feature/edital-crud-productization`
- Base SHA: `fc185fee64df818cc28a19d010f66566dd4b83ec`
- Commit de baseline desta fase: `05d90f05ccadab6961013edf5d23bd0a094fe3be`
- HEAD validado antes deste commit de documentação: `ac0296491190ad95f5fb2ea4002201f4a0925855`; o commit deste relatório é o commit final da branch.
- `main` permaneceu em `230ec63b49dffe4263ca4c8336216cf84d19aee8`; não houve merge.

Commits desta fase, em ordem:

1. `05d90f0` — baseline da adaptação.
2. `2e6503c` — configuração 2026, validadores e workspace do analista.
3. `3d1616e` — triagem de elegibilidade, exceções e diligências relacionadas.
4. `ac02964` — ciclo 2026 independente de Excel e regressões.
5. `docs: document 2026 edital adaptation and decisions` — este relatório, mapeamento e decisões abertas.

## Resultado funcional

**Sim.** Um administrador consegue criar e configurar o edital pelas telas do produto e o ciclo 2026 passa no teste `test_edital_2026_operational_lifecycle_without_workbook`. O teste cria o edital, grupos, programa e município, 14 requisitos, 23 checks e suas validações por requisições HTTP às telas; publica; registra restrição de participação; cadastra candidaturas; verifica alertas de duplicidade; distribui; analisa; encaminha INAPTA para revisão; classifica elegíveis; e consulta métricas.

O mesmo conjunto operacional passou com `ENABLE_LEGACY_IMPORT=false`. Esse teste não abre workbook, não importa `legacy_import` e confirma que a execução de um edital novo não depende do módulo histórico. O resultado não substitui a confirmação da coordenação das decisões ainda abertas abaixo.

## O que ficou configurável

- Dados gerais, status, versão e datas do edital; publicação validada e snapshot da configuração; clonagem existente da productização.
- Grupos, política de classificação, programa e associações com municípios; a configuração 2026 cria G1 feminino/nutrizes, G2 PRONASCI masculino e G3 masculino geral. A regra mista usa G1 na política configurada do edital.
- Requisitos e subcritérios com título, código, ordem, seção de apresentação, obrigatoriedade, estados permitidos, estados aceitos e campos de evidência.
- Validadores tipados e limitados a implementações seguras no código: correspondência de CNPJ, validade de data, idade mínima do CNPJ e CNAE esperado/modo de comparação.
- Data de referência oficial, parâmetros financeiros, grupos, programa e municípios editáveis na configuração do edital. A estrutura 2026 não exige valores financeiros, pois eles não constam da especificação recebida.
- Restrição de participação por CNPJ com motivo, fonte, período de referência e estado ativo; correção de CNPJ da candidatura é uma operação explícita, autorizada e auditada.
- Duplicidade por edital + CNPJ é um alerta de exceção. O template 2026 usa `WARN_ONLY`: não exclui nem reprova automaticamente candidaturas.

## Telas e operação

- Administração de editais em `/admin-editais/`, com criação, detalhes, edição, publicação, clonagem, configuração por seções e prévia do workspace do analista.
- Configuração de programas e associações com municípios na administração; cadastro de município canônico continua disponível.
- A fila de exceções e a lista de processos exibem restrição crítica, duplicidade, CNPJ inválido e grupo pendente com texto além da cor.
- O workspace do analista apresenta resumo e cards agrupados por seção. Renderiza somente as evidências habilitadas por check, mostra validações e pendências, e mantém o resultado calculado no backend.
- Anexo I identifica `Submission.cnpj` como CNPJ declarado na candidatura. A confirmação ou correção é explícita; CNPJ documental divergente é exibido como falha.
- Restrição ativa impede distribuição e criação/início de avaliação normal. A diligência segue como workflow próprio com checks relacionados, responsável, prazo, resposta e auditoria.

## Modelo e migrations

As alterações são aditivas e não removem modelos operacionais existentes:

- `apps/editais/migrations/0010_classificationpolicy_mixed_group_code_and_more.py`
- `apps/editais/migrations/0011_alter_edital_duplicate_policy.py`
- `apps/evaluations/migrations/0005_checkresult_canonical_cnpj_confirmed_and_more.py`
- `apps/institutions/migrations/0003_institution_postal_code.py`
- `apps/reviews/migrations/0004_diligence_related_check_results.py`
- `apps/submissions/migrations/0006_participationrestriction.py`

Incluem referência temporal e política de grupo para a configuração do edital, campos de evidência de CNPJ/data/CNAE/abertura/confirmação, CEP institucional, checks relacionados à diligência e a entidade `ParticipationRestriction`.

## Verificações

- Suíte completa com cobertura: **229 passaram, 2 skips**, cobertura total **83%**.
- Os dois skips são exclusivamente os testes `legacy_real`; `LEGACY_XLSX_PATH` não foi fornecido e o teste informa `NOT_RUN`, sem atribuir PASS de paridade.
- `ENABLE_LEGACY_IMPORT=false pytest -q`: **217 passaram**; os módulos de teste exclusivos da migração histórica são omitidos da coleta quando a aplicação opcional está desligada. O teste de ciclo operacional 2026 é executado nessa suíte.
- Teste focado de configuração/seed 2026: **15 passaram**.
- `python manage.py check`: sem problemas.
- `python manage.py makemigrations --check`: nenhuma migration pendente.
- `ruff check .`, `ruff format --check .` e `git diff --check`: passaram.
- CI remota: não executada nesta adaptação local; o push pode iniciar a CI configurada no repositório.

## Fronteira e status do legado

O arquivo de especificação 2026 foi lido somente para mapear conceitos e configurar o produto; tinha as abas `DISTRIBUIÇÃO`, `ANALISTA` e `REGRAS`, sem registros preenchidos ou fórmulas relevantes. Não foi copiado para o repositório nem é requerido em runtime.

O golden master da planilha histórica real continua **NOT_RUN** porque seu caminho não foi informado nesta fase. Testes sintéticos continuam cobrindo o importador como ferramenta de migração/regressão, sem estabelecer paridade real. A fronteira está documentada em [legacy-boundary.md](legacy-boundary.md).

## Decisões abertas

1. Confirmar a data oficial que servirá de referência para validade documental e idade do CNPJ. Sem data, a publicação é bloqueada quando há regra ativa dependente dela.
2. Definir se `87.20-4-99` deve ser o único CNAE, o principal ou apenas estar presente. O modo 2026 está como não resolvido; `EXACT` e `CONTAINS` são configuráveis.
3. Definir qual candidatura prevalece quando o mesmo CNPJ envia mais de uma. Até decisão, o alerta `WARN_ONLY` preserva todas.
4. Confirmar formalmente se vagas de mães nutrizes sempre enquadram no G1 em 2026. Atualmente é política configurada no template, não regra global.
5. Fornecer a fonte/lista oficial dos municípios PRONASCI a associar ao edital.
6. Confirmar política de desempate; empate sem decisão continua sujeito à política explícita configurada e não deve receber regra jurídica inventada.

Este relatório comprova o ciclo testado e as verificações executadas; não declara aprovação jurídica final nem paridade com o workbook histórico.
