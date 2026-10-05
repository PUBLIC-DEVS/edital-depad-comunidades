# Real legacy workbook parity — fase 15

Data: 2026-09-28. Status: **FAIL**. Arquivo externo efetivamente lido duas vezes por execução, com fórmulas e cached values separados, sem salvar ou recalcular. SHA-256: `030b28f5ca61a3fa79e1b07834cee952fa262d3aef7b6641242d44865bf55ac2`. O hash foi conferido antes/depois nos testes reais.

## FACTS FROM WORKBOOK

| Observação externa | Resultado |
| --- | --- |
| Abas / abas individuais ANÁLISE - | 23 / 11 |
| DISTRIBUIÇÃO com SEI em E | 282 processos únicos |
| Linha adicional DISTRIBUIÇÃO 14 | CNPJ presente, SEI ausente; issue e exclusão do universo seguro |
| Carga por analista | Quatro com 25, sete com 26 |
| Grupos brutos G1/G2/G3/SEM GRUPO | 9 / 34 / 212 / 27 |
| BY inicial armazenado | 180 APTA / 102 INAPTA |
| REVISÃO, SEI C e resultado CG | 216; 131 pré-inabilitados / 70 pré-habilitados / 15 vazios |
| DILIGÊNCIA, SEI C | 165 linhas / 158 SEIs; eventos repetidos preservados |
| MÉTRICAS exibidas | 177 APTA / 105 INAPTA / 0 em análise |
| CLASSIFICAÇÃO materializada G1/G2/G3 | 5 / 24 / 143 = 172 |
| CNPJs repetidos / inscrições excedentes | 20 / 21 |
| ANÁLISE consolidada | 283 linhas com identidade; 8 sem SEI; todos os 283 resultados BX sem valor cached |

As 109 divergências de resultado inicial têm BY **literal**, sem fórmula naquela célula, e checks negativos. O BZ é comparado separadamente; não é usado para tornar o resultado calculado igual ao BY manual.

A fórmula de CLASSIFICAÇÃO usa o BY das abas individuais: ordena todas as inscrições por CNPJ/data/hora, mantém a primeira inscrição absoluta e somente depois filtra APTA/grupo. Não usa o resultado da REVISÃO como fonte de elegibilidade. Nas duplicatas, seis inscrições posteriores APTAS são bloqueadas por primeiras inscrições INAPTAS; outras duas APTAS são suprimidas por primeiras APTAS.

## CALCULATED BY NEW SYSTEM

- Importação lenient: 282 submissions, 261 instituições, 228 municípios, 282 assignments, 282 avaliações, 216 revisões, 165 diligências e 33 vínculos PRONASCI. Códigos IBGE não resolvidos ficam nulos.
- Grupos: 9/34/212/27, iguais ao universo bruto observado.
- Resultado inicial dos checks reais: 71 APTA / 211 INAPTA. 109 resultados diferem do BY manual; a lista completa está no CSV privado de avaliações.
- Finanças: regras extraídas das fórmulas U/V reconhecidas, por tipo de vaga; 1172.23 feminino/masculino, 1527.37 nutriz, 12 meses e patrimônio de 10%, com Decimal. U coincide nos 282 processos; V possui um cached vazio versus zero calculado.
- Ranking histórico reconstruído com BY armazenado: 172 entradas, grupos 5/24/143, **zero diferenças de presença/posição por SEI** contra CLASSIFICAÇÃO. Isso é reprodução histórica explícita, separada do workflow operacional.
- Ranking inicial recalculado, antes de decisões de revisão: 69 entradas, grupos 1/8/60. Há 169 diferenças de presença/posição em relação ao ranking histórico, inclusive deslocamentos de posição.
- Após revisões e supressão absoluta: 130 candidatos elegíveis. Há dois conjuntos de empate absoluto, envolvendo quatro candidatos; nenhum snapshot operacional foi emitido, conforme decisão do responsável.
- Revisões: zero diferenças na importação de revisor/resultado normalizado e provenance. Não se afirma recálculo jurídico da decisão do revisor.
- Diligências: zero diferenças de quantidade/provenance por SEI. Prazo, data e solicitante permanecem nulos; status e resultado operacionais LEGACY_UNKNOWN.
- Idempotência em execuções Python separadas: todas as oito contagens permaneceram iguais. Runs/observações da fonte são novos registros por execução, intencionalmente.

## MISMATCHES

302 ocorrências registradas: 297 comparações de campos, 3 erros estruturais da fonte e 2 diferenças de métricas globais. Há 183 SEIs afetados por ao menos uma diferença de campo; isso não significa 302 processos distintos.

| Código de comparação | Ocorrências |
| --- | --- |
| INITIAL_RESULT | 109 |
| RECALCULATED_INITIAL_POSITION | 169 |
| INSTITUTION | 6 |
| MUNICIPALITY | 12 |
| PATRIMONIO_MINIMO | 1 |

As seis diferenças de instituição são nomes divergentes para o mesmo CNPJ. Algumas são de grafia, outras exigem confirmação cadastral; não se presume que sejam aliases oficiais. O cadastro conserva o primeiro nome e a fonte conserva todas as variantes. Dez diferenças de município são caixa/grafia canônica; duas linhas têm município informado sem UF resolvida. Há ainda quatro warnings MISSING_MUNICIPALITY, incluindo campos ausentes. Nenhum município ou UF foi inventado.

Erros críticos: MISSING_SEI (1) e UNKNOWN_CHECK_STATUS (2). Também há 32 valores de validade documental não interpretados e 802 observações de fórmulas com cached None nas células selecionadas. Cached None pode representar saída intencionalmente vazia; openpyxl não distingue essa hipótese de ausência de cache. A importação strict foi executada e rejeitou a fonte, revertendo alterações operacionais e preservando issues.

Reconciliação histórica comprovada:

| Etapa | Quantidade |
| --- | --- |
| APTAS iniciais nas abas individuais | 180 |
| APTAS suprimidas por primeira inscrição absoluta | -8 |
| APTAS mantidas sem grupo | 0 |
| Classificados reconstruídos e materializados | 172 |
| APTAS exibidas em MÉTRICAS | 177 |

Os três registros de diferença entre 180 e 177 não podem ser identificados a partir dos caches da consolidação. Por grupo, as abas individuais têm APTAS 5/24/151 e INAPTAS 4/10/61/27; MÉTRICAS exibe APTAS 4/24/149 e INAPTAS 5/10/63/27. Não há evidência para atribuir silenciosamente a diferença a cinco duplicatas ou forçar 177 como ranking.

## INTENTIONAL DIFFERENCES

Decisões expressas do responsável nesta sessão, em 2026-09-28:

1. Preservar os resultados BY manuais como histórico; manter o resultado inicial recalculado no fluxo operacional. As 109 diferenças e suas consequências no ranking continuam visíveis, sem alterar o workbook.
2. Manter bloqueio por empate absoluto e registrar OPEN BUSINESS QUESTION. Não autorizar desempate SEI nem ordem da linha por inferência.

O sistema operacional considera resultados de revisão, enquanto a fórmula histórica classifica pelo BY inicial. Escopo ABSOLUTE/ELIGIBLE de duplicidade e desempate são parâmetros explícitos. O default ABSOLUTE reproduz a sequência histórica, inclusive a primeira INAPTA bloqueando segunda APTA. O valor financeiro é arredondado em centavos e vazios permanecem rastreáveis como vazios na fonte.

## UNRESOLVED QUESTIONS

- Precedência jurídica em empates absolutos e eventual adoção de outra política de segunda inscrição.
- Efeito jurídico de cada evento histórico de diligência; não é inferível como SANEADA/NAO_SANEADA.
- Significado de status não padronizados ou números inseridos em células de status.
- Mapeamento das métricas exibidas 177/105 para processos, sem caches de consolidação.
- Resolução oficial de IBGE, UF ausente e nomes institucionais discrepantes por CNPJ.

Não há PASS geral. A comparação do snapshot operacional permanece incompleta por política não autorizada, e as decisões jurídicas de revisão/diligência não são recalculadas por suposição.

## Artefatos

Todos os arquivos por processo ficam em `artifacts/private/`, ignorado pelo Git:

- `legacy-real-summary.json`
- `legacy-real-submissions-diff.csv`
- `legacy-real-evaluations-diff.csv`
- `legacy-real-reviews-diff.csv`
- `legacy-real-diligences-diff.csv`
- `legacy-real-ranking-diff.csv`
- `legacy-real-reconciliation-diff.csv`
- `legacy-real-duplicates-diff.csv`
- `legacy-real-issues-diff.csv`
- `legacy-real-ranking-ties.csv`
- `legacy-real-idempotency.json`

Resumo agregado público: [legacy-real-summary.json](../artifacts/legacy-real-summary.json). CSVs não incluem cópias integrais das evidências documentais de revisão; a provenance completa fica no banco privado.
