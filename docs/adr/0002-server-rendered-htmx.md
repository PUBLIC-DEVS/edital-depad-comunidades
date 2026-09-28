# ADR 0002: Renderização Server-Side com Django Templates, HTMX e Tailwind CSS

## Contexto
O sistema requer interfaces reativas e de alta produtividade (como filtros dinâmicos de processos, atualização de painéis de checagem documental e busca sem recarregar a página inteira), mas sem a complexidade de manter builds de JavaScript pesados, roteamento no cliente ou duplicação de validações inerentes a SPAs (React, Vue, Angular).

## Decisão
Adotamos renderização server-side com **Django Templates**, aprimorada com **HTMX** para interações dinâmicas parciais (*HTML over the wire*), **Tailwind CSS** para estilização semântica e acessível, e **Alpine.js** exclusivamente para comportamentos declarativos efêmeros no cliente (como modais e abas visuais).

## Consequências
- **Positivas:** Nenhuma lógica de negócio ou cálculo oficial vive no frontend; validação de permissões e integridade sempre executada pelo servidor; carga cognitiva reduzida; excelente performance e acessibilidade.
- **Negativas:** Requer organização cuidadosa de *partials* de templates (`templates/partials/...`) para reutilização limpa entre respostas completas e parciais HTMX.
