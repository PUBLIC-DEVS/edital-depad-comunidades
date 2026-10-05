# Diretrizes de Segurança, Isolamento e Hardening — DEPED/MDS

Este documento detalha os controles de segurança técnica, isolamento entre analistas e conformidade implementados na plataforma.

---

## 1. Princípios de Segurança e Modelo de Ameaças

1. **Nunca Confiar no Frontend (Zero Trust no HTML):**
   - A ocultação de botões ou links no template é apenas conveniência de interface.
   - Qualquer operação de leitura, alteração ou conclusão é validada imperativamente no backend (`RolePermissionPolicy` e `enforce_evaluation_edit_access`).
2. **Prevenção Rigorosa de IDOR (Insecure Direct Object Reference):**
   - O acesso por ID numérico (`/avaliacoes/<id>/` ou `/processos/<id>/`) obriga a resolução do vínculo de atribuição.
   - Se um analista autenticado tentar abrir a URL de um processo atribuído a outro analista, o sistema responde com `403 Forbidden` (`PermissionDenied`).
3. **Imutabilidade e Append-Only:**
   - Eventos de auditoria (`AuditEvent`) e snapshots publicados de classificação (`RankingSnapshot`) são estritamente imutáveis no banco de dados. Qualquer tentativa de alteração ou exclusão dispara exceção incondicional.

---

## 2. Controle de Acesso Baseado em Papéis (RBAC)

O modelo customizado de usuários (`accounts.User`) define perfis com privilégios mínimos:

| Papel | Escopo de Leitura | Escopo de Escrita / Decisão |
| :--- | :--- | :--- |
| **ANALISTA** | Apenas processos formalmente atribuídos a si (`Assignment.Status.ACTIVE`). | Preenchimento de checklist, notas e conclusão da análise própria. |
| **REVISOR** | Processos em estado `PENDING_REVIEW` após conclusão do analista. | Registro de concordância/divergência e fundamentação da revisão. |
| **DISTRIBUIDOR** | Todos os processos em triagem (`RECEIVED`, `ASSIGNED`). | Atribuição individual ou em lote a analistas ativos. |
| **COORDENADOR** | Visão global de todos os processos, métricas e exceções. | Redistribuição, cancelamento, geração de ranking e diligências. |
| **CONSULTA** | Visão somente leitura de processos concluídos e relatórios. | Nenhuma ação de escrita. |
| **ADMINISTRADOR** | Acesso irrestrito a configurações de editais e parâmetros. | Gestão de parâmetros e auditoria. |

---

## 3. Proteção contra CSRF e Integração HTMX

- O middleware padrão `CsrfViewMiddleware` está ativo em todas as rotas de mutação (POST, PUT, DELETE).
- O elemento `<body>` injeta globalmente o cabeçalho CSRF para todas as requisições assíncronas disparadas pelo HTMX:
  ```html
  <body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
  ```
- O cookie de CSRF possui proteção com flags de segurança em ambiente de produção (`CSRF_COOKIE_SECURE = True`).

---

## 4. Cookies de Sessão e Hardening de Produção

Em `config/settings.py`, foram estabelecidas diretivas de segurança:

- `SESSION_COOKIE_HTTPONLY = True`: Impede que scripts do navegador (XSS) acessem o token da sessão.
- `X_FRAME_OPTIONS = "DENY"`: Bloqueia totalmente ataques de Clickjacking em iframes.
- `SECURE_CONTENT_TYPE_NOSNIFF = True`: Impede MIME-type sniffing no navegador.
- `SECURE_BROWSER_XSS_FILTER = True`: Ativa proteção adicional no browser.
- Em produção (`DEBUG=False`):
  - `CSRF_COOKIE_SECURE = True`
  - `SESSION_COOKIE_SECURE = True`
  - `SECURE_SSL_REDIRECT = True`
  - `SECURE_HSTS_SECONDS = 31536000` (HSTS estrito com subdomínios e preload).

---

## 5. Trilha de eventos e limites da proteção

Todas as ações críticas (criação de processo, redistribuição, conclusão de análise, divergência de revisor, snapshot de classificação) registram uma entrada append-only na tabela `audit_auditevent`. O registro armazena:
- `actor_id`: Usuário autenticado responsável.
- `timestamp`: Instante da operação, armazenado conforme USE_TZ e exibido no fuso da aplicação. Não representa datas históricas ausentes no Excel.
- `entity_type` e `entity_id`: Identificação clara do recurso afetado.
- `action`: Código padronizado da ação realizada.
- `field`, `old_value`, `new_value` e `metadata`: Alteração e contexto da operação.

O hardening inclui início e conclusão de análise, claim e decisões de revisão, abertura/resposta/conclusão de diligência, mudanças de grupo e transições para ranking. Administradores consultam entidades operacionais em modo somente leitura; a interface de operação usa os serviços auditados. A proteção existente de AuditEvent em save/delete e admin foi preservada. Não é uma garantia por triggers contra SQL privilegiado.

RankingSnapshot/Entry/Exclusion têm bloqueios adicionais para save/delete/update/bulk_update e updates por conflito, além de admin somente leitura e criação de entradas apenas durante geração do snapshot. Ranking e métricas globais exigem papel permitido nas views, inclusive exports. A validação local não substitui a conferência da CI em PostgreSQL nem revisão independente.
