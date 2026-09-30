# Guia de Estilo de Interface e Sistema de Design (UI Style Guide) — DEPAD / MDS

Este documento define os princípios de concepção visual, a arquitetura de tokens, componentes reutilizáveis, critérios de acessibilidade e diretrizes de governança visual para o **Sistema de Gestão e Análise de Editais da DEPAD/MDS** (Departamento de Entidades de Apoio e Acolhimento Atuantes em Álcool e Drogas / Ministério do Desenvolvimento e Assistência Social, Família e Combate à Fome).

---

## 1. Propósito e Relação com a Referência Visual

O sistema foi desenhado para proporcionar um ambiente de trabalho corporativo, sóbrio, altamente legível e ergonomicamente balanceado para analistas, revisores, distribuidores e coordenadores de editais públicos.

### Referência de Concepção Externa
- Os conceitos de ritmo, geometria, curvas suaves de transição e paleta de cores foram inspirados no documento técnico institucional de referência visual (`identidade_visual.pdf`).
- **Nota Importante:** O arquivo de referência visual (`identidade_visual.pdf`) é estritamente uma referência externa de concepção utilizada durante o desenho inicial. **Ele não integra nem deve ser versionado no repositório de código**.

---

## 2. Regras Estritas de Neutralidade Institucional

Para garantir a perenidade do software como política de Estado e preservar a conformidade jurídica da administração pública:

1. **Vedação a Logomarcas e Símbolos de Gestão:** É terminantemente proibido o uso de logomarcas transitórias de governo, marcas de campanhas publicitárias ou elementos promocionais de mandatos eletivos.
2. **Vedação a Slogans Políticos ou Governamentais:** Nenhuma tela, relatório ou cabeçalho deve exibir slogans de governos ou campanhas (por exemplo, "União e Reconstrução", "Do lado do povo brasileiro" ou equivalentes).
3. **Ausência de Fotografias ou Menções Personalistas:** É vedada a inclusão de fotografias, citações ou menções nominais a ministros, secretários ou quaisquer autoridades públicas, preservando o princípio da impessoalidade (Art. 37, § 1º da CF/88).
4. **Identificação Puramente Funcional:** A aplicação identifica-se exclusivamente por sua sigla institucional funcional: **DEPAD / MDS** e seu título operacional: *Sistema de Gestão de Editais*.

---

## 3. Arquitetura de Design Tokens e Cores

O sistema utiliza CSS custom properties padronizadas centralizadas em `static/css/tokens.css` e importadas globalmente via `static/css/styles.css`.

### 3.1 Paleta Primária e Institucional (Brand Indigo)
Inspirada nos tons escuros e profundos da identidade de acolhimento e gestão pública:
- `--depad-brand-dark`: `#171B55` — Fundo principal do cabeçalho institucional e elementos de máximo contraste.
- `--depad-brand`: `#222873` — Azul marinho corporativo intermediário.
- `--depad-brand-light`: `#2B3291` — Azul marinho claro para destaques sóbrios e variações de cabeçalho.
- `--depad-brand-subtle`: `#EEF0F8` — Superfície sutil para áreas ativas ou agrupamentos institucionais.

### 3.2 Ação e Interatividade (Action Blue)
Utilizada para links navegáveis, botões de ação principal e estados de seleção:
- `--depad-blue-primary`: `#0248AB` — Cor padrão para botões primários e links operacionais.
- `--depad-blue-hover`: `#0B57C5` — Estado hover com realce sutil.
- `--depad-blue-active`: `#003785` — Estado ativo / pressionado.
- `--depad-blue-focus`: `#1A73E8` — Anel de foco acessível.
- `--depad-blue-surface`: `#E8F0FE` — Fundo para badges e cards informativos.

### 3.3 Acento Geométrico e Alertas (Accent Red / Coral)
Inspirado nas curvas vibrantes de transição da identidade visual:
- `--depad-red-accent`: `#D12B32` — Tom vibrante utilizado na linha de acento da barra superior (`.depad-accent-bar`).
- `--depad-red-dark`: `#B4232A` — Tom de alta densidade para botões de perigo e badges de rejeição.
- `--depad-red-light`: `#E33A40` — Variação clara para destaques.
- `--depad-red-surface`: `#FDF2F2` — Superfície suave para caixas de erro e anomalias críticas.

### 3.4 Status Semânticos de Fluxo e Conformidade
| Estado de Conformidade | Cor do Texto / Borda | Fundo da Superfície | Classe do Badge |
| :--- | :--- | :--- | :--- |
| **Atende / Apto / Concluído** | `#065F46` (Esmeralda escuro) | `#D1FAE5` (Verde 100) | `.depad-badge-success` |
| **Não Atende / Inapto / Erro** | `#991B1B` (Vermelho escuro) | `#FEE2E2` (Vermelho 100) | `.depad-badge-danger` |
| **Não Enviado / Diligência** | `#92400E` (Âmbar escuro) | `#FEF3C7` (Âmbar 100) | `.depad-badge-warning` |
| **Em Análise / Informação** | `#1E40AF` (Azul escuro) | `#DBEAFE` (Azul 100) | `.depad-badge-info` |
| **Não Aplicável / Neutro** | `#334155` (Slate escuro) | `#F1F5F9` (Slate 100) | `.depad-badge-neutral` |

### 3.5 Superfícies Neutras e Foco
- Fundo geral da aplicação: `--depad-bg`: `#F8FAFC` (Slate 50).
- Fundo dos cartões: `--depad-surface`: `#FFFFFF`.
- Bordas estruturais: `--depad-border`: `#E2E8F0` (Slate 200).
- Anel de foco acessível: `--depad-focus-ring`: `0 0 0 3px rgba(2, 72, 171, 0.35)`.

---

## 4. Tipografia e Escala

A interface emprega a família do sistema operacional (`Inter`, `-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, `Roboto`), priorizando legibilidade nativa em alta resolução:
- **Títulos Maiores (H1):** `font-size: 1.5rem (24px)`, `font-weight: 700`, cor `#0F172A`.
- **Títulos de Seção (H2):** `font-size: 1.125rem (18px)`, `font-weight: 700`, cor `#1E293B`.
- **Rótulos e Metadados Formais:** `font-family: ui-monospace, SFMono-Regular, monospace` para números SEI, CNPJs, códigos IBGE e versões de snapshot.
- **Tabelas Operacionais:** `font-size: 0.75rem (12px)`, com entrelinha compacta para garantir alta densidade sem poluição visual.

---

## 5. Componentes e Anatomia Visual

Os componentes estilizados estão consolidados em `static/css/components.css`:

### 5.1 Cartões Estruturais (`.depad-card`)
Fundo branco, borda neutra de 1px (`#E2E8F0`), cantos arredondados (`border-radius: 8px`), e sombra suave (`box-shadow: 0 1px 3px rgba(0,0,0,0.06)`).

### 5.2 Barra de Acento Institucional (`.depad-accent-bar`)
Faixa sutil de 4px na base da barra de navegação superior, desenhada com degradê suave entre os tons da paleta (`#171B55` -> `#0248AB` -> `#D12B32`), conferindo elegância sem quebrar a neutralidade.

### 5.3 Botões (`.depad-button`)
- `.depad-button-primary`: Ações de avanço, salvamento e submissão (fundo `#0248AB`, texto branco).
- `.depad-button-secondary`: Ações secundárias e cancelamentos (fundo branco, borda `#CBD5E1`, texto `#334155`).
- `.depad-button-danger`: Ações de remoção ou rejeição (fundo `#DC2626`, texto branco).
- `.depad-button-warning`: Diligências saneadoras e alertas (fundo `#D97706`, texto branco).
- `.depad-button-outline`: Ações secundárias na tabela (fundo transparente, borda `#0248AB`, texto `#0248AB`).

### 5.4 Tabelas Densas (`.depad-table`)
Tabelas operacionais com cabeçalho fixado, fundo `#F8FAFC`, texto em maiúsculas (`text-[11px] font-semibold text-slate-600`), bordas horizontais finas e destaque suave nas linhas ao passar o mouse (`hover:bg-slate-50`).

### 5.5 Formulários Padronizados (`.depad-form-input`, `.depad-form-select`, `.depad-form-textarea`)
Borda de 1px com raio de curvatura de 6px, tamanho de fonte de 12px para evitar saltos visuais, e anel de foco visível em conformidade com WCAG AA.

---

## 6. Diretrizes de Acessibilidade (WCAG 2.1 AA) e Responsividade

1. **Contraste de Cor Rigoroso:** Todas as combinações de texto e superfície foram testadas para atingir contraste mínimo de 4.5:1 para texto normal e 3:1 para texto grande ou badges gráficos.
2. **Navegabilidade por Teclado:** Todo componente interativo possui `:focus-visible` destacado sem remoção de outline. Nenhum elemento bloqueia o foco via script.
3. **Skip to Content:** Todas as páginas incluem um link inicial invisível que se torna visível ao pressionar Tab, permitindo pular direto ao `#main-content`.
4. **Responsividade Garantida:**
   - Telas de até 375px (mobile): tabelas com rolagem horizontal controlada (`overflow-x-auto`), colunas flexíveis e navegação colapsada ou amigável ao toque.
   - Telas de 1200px+ (desktop): layout fluido em grid, painéis laterais de conferência fixos e alta densidade de registros.

---

## 7. Diretrizes de Manutenção para Futuros Desenvolvedores

Ao criar ou estender telas no sistema:
1. **Nunca use cores arbitrárias diretamente no CSS:** Utilize sempre as classes do Tailwind disponíveis ou as variáveis CSS declaradas em `static/css/tokens.css`.
2. **Preserve a Neutralidade Institucional:** Não adicione logomarcas nem imagens promocionais. Mantenha os rodapés institucionais limpos e informativos.
3. **Mantenha a Densidade Operacional:** Nas telas de listagem, use `.depad-table` e texto `text-xs`. Não utilize fontes grandes em tabelas analíticas.
4. **Respeite o Desacoplamento do Backend:** Alterações visuais devem ser feitas estritamente nos templates HTML e arquivos CSS estáticos. Não altere modelos de dados, serializadores ou regras de negócio para fins de formatação de tela.


## 8. Refinamento do fluxo de um edital

Esta seção atualiza a operação descrita nas seções históricas acima. O cabeçalho
usa **Sistema de Gestão e Análise de Edital**, no singular. A navegação varia por
papel conforme [o fluxo operacional](SIMPLIFIED_OPERATIONAL_FLOW.md); diligência
não é exibida, e o âmbar representa atenção/revisão pendente.

- `.operational-table`: leitura próxima à planilha, filtros compactos, colunas
  secundárias em detalhes expansíveis no mobile.
- `.document-block`, `.check-form`: documentos e checks numerados pela configuração,
  sem cartões aninhados para cada campo. Evidências em `<details>` nativo.
- `.status-option`: radio acessível com texto/ícone, borda e superfície selecionada;
  verde ATENDE, vermelho NÃO ATENDE e neutro NÃO SE APLICA. Cor não é o único sinal.
- `.analysis-summary`: progresso com `role=progressbar`, contagens e feedback de
  salvamento; erros são alertas e campos inválidos usam `aria-invalid`.
- `.chart-panel`, `.chart-row`: barras CSS acompanhadas de valores e legendas;
  linha SVG com alternativa tabular. Nenhuma imagem promocional ou gráfico decorativo.

Preservam-se Brand Indigo, Action Blue, Accent Red, superfícies neutras e foco
visível. A validação responsiva inclui 375, 768, 1024, 1280 e 1440 px.
