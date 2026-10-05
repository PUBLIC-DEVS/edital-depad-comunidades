# ADR 0003: Camada Explícita de Serviços de Domínio (Service Layer)

## Contexto
Em aplicações Django convencionais, há a tentação de dispersar regras de negócio críticas em `Model.save()`, Django Signals, métodos de formulários ou diretamente nas Views. No caso deste edital, onde as regras de habilitação, financiamento, elegibilidade, desempate e ranking devem ser 100% auditáveis e passíveis de teste isolado e verificação contra o Excel legadão, o acoplamento excessivo prejudicaria a rastreabilidade.

## Decisão
Estabelecemos o padrão de **Service Layer** explícito:
- Módulos `services/` dentro de cada app de domínio (ex: `apps.evaluations.services.evaluation`, `apps.ranking.services.ranking`, `apps.submissions.services.workflow`).
- Views e forms atuam apenas como adaptadores HTTP / validação de entrada, delegando a execução e as transições para os serviços.
- Signals do Django são evitados para regras de negócio e restritos a efeitos colaterais técnicos (quando estritamente indispensáveis). Mutações de estado de workflow geram eventos de auditoria de forma atômica e explícita no serviço.

## Consequências
- **Positivas:** Lógica determinística testável sem banco de dados ou com fixtures leves; facilidade de comparar resultados com o Golden Master em Python puro; APIs de serviço limpas e previsíveis.
- **Negativas:** Código adicional inicial para orquestrar serviços e entidades em vez de chamadas diretas a `Model.objects.create(...)` nas views.
