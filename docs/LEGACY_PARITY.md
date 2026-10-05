# Paridade legada: escopo da evidência

O teste anterior foi renomeado para `tests/integration/test_synthetic_legacy_importer.py`. Ele testa importação de dados gerados pelo próprio projeto, incluindo idempotência, sem provar comportamento da planilha histórica.

O golden master externo está em `apps/legacy_import/parity.py` e `tests/integration/test_real_legacy_workbook.py`, com marcador `legacy_real`. O arquivo real foi efetivamente lido nesta fase. Status atual: **FAIL**. Os resultados por SEI e a reconciliação estão documentados em [REAL_LEGACY_PARITY.md](REAL_LEGACY_PARITY.md).

Estados admitidos: NOT_RUN (arquivo real não executado), PARTIAL (execução com áreas ainda não comparadas), PASS (critérios satisfeitos ou diferenças formalmente aceitas), FAIL (divergências ainda não resolvidas). A ausência do XLSX gera skip do teste externo e mantém NOT_RUN para essa execução. Resultado verde de pytest não muda o status de paridade.

O harness compara identidade, timestamp, analista, município/UF, vagas, grupos, valores financeiros, resultado inicial calculado, requisitos descumpridos, decisão de revisão importada, eventos de diligência e classificação por processo. Diferencia decisão histórica armazenada de resultado recalculado. Não tenta recalcular o Excel genericamente.

O cálculo histórico usando BY materializado e primeira inscrição absoluta reproduziu os 172 classificados, inclusive posições por SEI. O novo cálculo dos checks e o workflow que considera revisões produzem outra população; não se presume equivalência. Empates do ranking operacional seguem bloqueados por decisão do responsável.

Relatórios privados não são commitados. O Git contém apenas contagens, códigos de divergência, schema e resumo sanitizado. O arquivo histórico não foi salvo nem alterado.
