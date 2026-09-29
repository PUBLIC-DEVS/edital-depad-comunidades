# Mapeamento histórico verificado

Coordenadas funcionais residem somente em [schema.py](../apps/legacy_import/schema.py). O parser abre fórmulas e valores materializados separadamente e nunca salva o arquivo externo.

| Fonte | Identidade e resultados | Destino |
| --- | --- | --- |
| DISTRIBUIÇÃO, linha 3+; cabeçalhos linha 2 | E SEI, D CNPJ, C instituição, F data + G hora, I analista, L UF/M município, N/O/P vagas, Q solicitado, R capacidade, U/V valores | Submission, Institution, Municipality, Assignment |
| Somente ANÁLISE -, linha 4+; cabeçalhos linha 3 | A instituição, B CNPJ, C SEI, D analista, BY resultado, BZ falhas | Evaluation, CheckResult e provenance |
| REVISÃO, linha 4+ | C SEI, J revisor, CE análise, CF falhas, CG revisão | Review; decisão importada, sem inventar item decisions |
| DILIGÊNCIA, linha 4+ | C SEI, H situação, CD análise, CE falhas, CF revisão | Um Diligence por linha; estado operacional desconhecido |
| CLASSIFICAÇÃO | B:H G1; J:P G2; R:X G3; Z PRONASCI | Observações independentes de ranking e ProgramMunicipality |
| ANÁLISE consolidada | C SEI, BX análise, BY falhas, BZ revisão, CA falhas, CB revisor | Somente observação de consolidação; nunca aba individual |
| MÉTRICAS | Valores exibidos, distintos dos registros | Fingerprint e reconciliação; não impõem resultado do sistema |

Status de checks e evidências são campos diferentes. SEI/páginas/CNPJ/data de validade não viram checks. ISENTO é NAO_APLICAVEL, aceito somente quando a regra do check permite; ENVIADO é ATENDE no contexto BV. Valores originais permanecem em CheckResult e LegacySourceRecord. A configuração reproduz inclusive a diferença histórica entre BY e BZ quanto a AW/BV.

Municípios usam nome/UF quando não há código oficial; IBGE fica nulo. A lista PRONASCI não está numa aba própria: vem de CLASSIFICAÇÃO Z. Nomes recuperados de caches/abas auxiliares não exigem o workbook externo BASE VIGENTE 2024. Ausências e valores desconhecidos geram issues, sem instituições, datas ou identificadores artificiais.

Idempotência usa get_or_create e confronta dados existentes sem sobrescrever decisões operacionais. Diligências repetidas usam edital/hash/aba/linha. Mudança de hash é nova versão histórica e requer reconciliação, não substituição silenciosa. Datas do import run representam ingestão, nunca data histórica da operação.
