# Decisões ainda abertas — Edital 2026

Estas escolhas não estão respondidas inequivocamente pela especificação funcional. O sistema mantém parâmetros explícitos e bloqueios quando a regra não pode ser aplicada com segurança.

1. **Data oficial de referência:** qual data deve ser usada para verificar vigência de documentos e idade mínima do CNPJ? A publicação é bloqueada quando validadores ativos dependem dessa data e ela está vazia.
2. **CNAE `87.20-4-99`:** precisa ser o único CNAE, o principal ou basta aparecer entre CNAEs? A comparação tem modos `EXACT` e `CONTAINS`; a configuração-base preserva o valor e deixa a escolha como `UNRESOLVED`/aviso.
3. **CNPJ duplicado:** qual inscrição prevalece quando a mesma entidade envia mais de uma candidatura? A configuração inicial de novos editais é `WARN_ONLY`: alerta e mantém todas para análise, sem exclusão automática.
4. **Mães nutrizes em G1:** confirmar formalmente se vagas de mães nutrizes sempre devem enquadrar a entidade no G1 em 2026. O template atual configura essa prioridade conforme a regra indicada, sem torná-la universal.
5. **Municípios PRONASCI:** qual fonte oficial/lista deve alimentar as associações município-programa do edital 2026? O workbook especifica o grupo, mas não traz a lista de municípios.

Até a coordenação confirmar os itens, não interprete o template como aprovação jurídica final do edital.
