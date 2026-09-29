# Design System & Padrões de Interface — DEPED/MDS

Este documento estabelece a arquitetura visual, os componentes reutilizáveis, os critérios de densidade e as diretrizes de acessibilidade para o Sistema de Gestão e Análise de Editais da DEPED/MDS.

---

## 1. Filosofia de Design e Princípios Visuais

O sistema foi concebido para o ambiente de trabalho de analistas, revisores e gestores públicos que operam sob alta carga cognitiva e examinam dezenas de documentos técnicos diariamente. A interface prioriza:

1. **Sobriedade Institucional:** Alinhamento estrito à identidade visual do Governo Federal brasileiro (MDS / Padrão Digital de Governo), com predominância de azul marinho profundo, cinzas neutros e contraste rigoroso.
2. **Densidade de Informação Equilibrada:**
   - *Alta Densidade:* Tabelas operacionais de triagem, filas de distribuição e listagem de processos para maximizar o número de registros visíveis sem rolagem desnecessária.
   - *Densidade Confortável:* Espaço de trabalho da análise documental, revisão e conferência de requisitos, privilegiando tipografia arejada, leitura fluida de justificativas e agrupamento visual em seções sanfonadas.
3. **Feedback Não Intrusivo e em Tempo Real:** Utilização de HTMX para salvar rascunhos automaticamente e atualizar o painel lateral de conformidade sem recarregar a tela, com indicadores discretos de estado ("Salvando...", "Salvo automaticamente").
4. **Navegabilidade por Teclado e Acessibilidade:** Objetivo de acessibilidade WCAG 2.1 AA, com foco visível, navegação por teclado, rótulos semânticos e contraste adequado. Conformidade integral exige auditoria de acessibilidade; não foi comprovada nesta fase.

---

## 2. Paleta de Cores Institucional

```
+--------------------------------------------------------------------------+
|  Azul Governo (govblue)                                                 |
|  #F0F6FF (50)  | #E0ECFF (100) | #0C326F (600) | #002256 (700) | #001A42 |
+--------------------------------------------------------------------------+
|  Cores Semânticas de Conformidade                                       |
|  Atende / Apto:       #16A34A (Verde 600)  / #DCFCE7 (Fundo Verde 100)   |
|  Não Atende / Inapto: #DC2626 (Vermelho 600) / #FEE2E2 (Fundo Vermelho)   |
|  Não Enviado:         #D97706 (Âmbar 600)  / #FEF3C7 (Fundo Âmbar 100)   |
|  Não Aplicável:       #64748B (Slate 500)  / #F1F5F9 (Fundo Slate 100)   |
|  Em Análise:          #2563EB (Azul 600)   / #DBEAFE (Fundo Azul 100)    |
|  Diligência / Alerta: #9333EA (Roxo 600)   / #F3E8FF (Fundo Roxo 100)    |
+--------------------------------------------------------------------------+
|  Neutros e Fundos                                                        |
|  Fundo da Aplicação:  #F8FAFC (Slate 50)                                 |
|  Superfície / Cards:  #FFFFFF (Branco)                                   |
|  Bordas Estruturais:  #E2E8F0 (Slate 200)                                |
|  Texto Principal:     #0F172A (Slate 900)                                |
|  Texto Secundário:    #475569 (Slate 600)                                |
+--------------------------------------------------------------------------+
```

---

## 3. Tipografia e Escala

A tipografia utiliza a pilha nativa do sistema operacional (Inter, Segoe UI, Roboto, SF Pro Text), complementada por fontes monoespaçadas para identificadores formais:

- **Títulos de Página:** `text-2xl font-bold tracking-tight text-slate-900`
- **Subtítulos e Seções:** `text-base font-bold text-slate-900`
- **Texto Corrido / Descrições:** `text-sm text-slate-600 leading-relaxed`
- **Rótulos e Tabela Densa:** `text-xs font-semibold text-slate-700`
- **Metadados SEI / CNPJ / Datas:** `font-mono text-xs font-semibold text-slate-800`

---

## 4. Componentes Estruturais

### 4.1 Skip Links de Acessibilidade
Para permitir que usuários de leitores de tela ou navegadores por teclado saltem diretamente para o conteúdo operacional:
```html
<a href="#main-content" class="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-white focus:text-govblue-700 focus:p-2 focus:rounded focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-govblue-600">
    Pular para o conteúdo principal
</a>
```

### 4.2 Badges e Chips Semânticos
```html
<!-- Atende -->
<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
    Atende
</span>

<!-- Não Atende -->
<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-800 border border-red-200">
    Não Atende
</span>

<!-- Não Enviado -->
<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">
    Não Enviado
</span>

<!-- Não Aplicável -->
<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
    Não Aplicável
</span>
```

### 4.3 Indicadores de Salvamento HTMX
Para conferir segurança ao analista durante a conferência de 30+ itens documentais:
```html
<div class="flex items-center gap-2 text-xs text-slate-500">
    <div id="save-indicator" class="htmx-indicator flex items-center gap-1.5 text-blue-600">
        <svg class="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span>Salvando alterações...</span>
    </div>
</div>
```

### 4.4 Tabelas Densas com Foco Visível
- Cabeçalhos fixos com fundo contrastante (`bg-slate-50`, texto em maiúsculas `text-[11px] font-semibold text-slate-600 uppercase tracking-wider`).
- Linhas alternadas ou com hover suave (`hover:bg-blue-50/40 transition`).
- Contorno de foco visível em todos os links e botões interativos (`focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-1`).

---

## 5. Diretrizes de Impressão e Relatórios
As folhas de estilo suportam a impressão limpa de relatórios e extratos de classificação:
- Ocultação automática de barras de navegação superior, rodapés de tela e botões de ação (`@media print { header, nav, footer, .no-print { display: none !important; } }`).
- Forçamento de preto sobre branco e preservação de quebras de página em tabelas longas (`break-inside: avoid`).
