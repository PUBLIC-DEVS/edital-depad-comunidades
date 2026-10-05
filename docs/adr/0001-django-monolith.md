# ADR 0001: Adoção de Monólito Modular Django

## Contexto
O processo anterior de análise, classificação e acompanhamento do edital era realizado via Excel Online, o que gerava inconsistências, concorrência descontrolada em células, fragilidade em fórmulas e ausência de trilha de auditoria. Para a informatização oficial, é necessário um sistema seguro, robusto, determinístico e de manutenção direta pelo time.

## Decisão
Adotamos uma arquitetura de **Monólito Modular Django**.
- As fronteiras entre domínios (instituições, submissões, avaliações, revisões, ranking, auditoria) são separadas em Django apps claros (`apps/*`).
- O banco de dados relacional principal é PostgreSQL, garantindo integridade referencial, transações ACID e consultas relacionais expressivas.
- Rejeitamos a divisão prematura em microserviços ou SPAs complexas, mantendo consistência transacional e simplicidade operacional no contexto do setor público.

## Consequências
- **Positivas:** Transações de banco atômicas sem consistência eventual; facilidade de testes de ponta a ponta e integração; deploy unificado; orquestração simples em container.
- **Negativas:** Requer disciplina estrita na separação de responsabilidades entre os apps para evitar acoplamento espaguete (mitigado pelo padrão de Service Layer).
