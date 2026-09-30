# Guia de Desenvolvimento Local

Este documento orienta o setup e execução do ambiente de desenvolvimento do **edital-depad-comunidades**.

---

## Homologação da feature

Para testar a feature atual, siga [MANUAL_TEST_GUIDE.md](MANUAL_TEST_GUIDE.md):

```bash
git clone --branch feature/edital-2026 \
  https://github.com/PUBLIC-DEVS/edital-depad-comunidades.git
cd edital-depad-comunidades
./scripts/tester-bootstrap.sh
```

O dataset 2026 é criado por `seed_homologation`, somente com execução explícita.
`seed_demo` continua sendo uma demonstração simples alternativa; não execute os
dois seeds no mesmo banco, pois a operação exige exatamente um edital ACTIVE.

Para validação isolada, Compose aceita `COMPOSE_PROJECT_NAME`,
`DEPAD_DB_CONTAINER`, `DEPAD_WEB_CONTAINER`, `DEPAD_DB_PORT` e `DEPAD_WEB_PORT`.
Defina nomes/portas distintos em conjunto; o volume PostgreSQL pertence ao projeto.
O padrão continua sendo `db`/`web`, portas 5432/8000. Nenhum script apaga volumes.

## 1. Caminho Oficial Recomendado (Docker + PostgreSQL)

O ambiente padrão e recomendado para desenvolvimento reproduzível utiliza **Docker** e **Docker Compose**, executando a aplicação Django integrada a um banco de dados **PostgreSQL 16**.

### Pré-requisitos
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado e em execução;
- Git.

### Passo a Passo

1. **Clonar o repositório:**
   ```bash
   git clone --branch feature/edital-2026 https://github.com/PUBLIC-DEVS/edital-depad-comunidades.git
   cd edital-depad-comunidades
   ```

2. **Garantir que o Docker daemon esteja ativo e validar o ambiente:**
   ```bash
   ./scripts/dev-check.sh
   ```
   O script verifica se o daemon do Docker e o Docker Compose estão operacionais, valida o arquivo `.dockerignore` e a integridade da configuração.

3. **Construir as imagens e iniciar os serviços em segundo plano:**
   ```bash
   docker compose up --build -d
   ```
   *Nota:* O banco PostgreSQL aguardará até estar saudável (`healthy`) antes da inicialização do serviço web.

4. **Aplicar as migrações do banco de dados:**
   ```bash
   docker compose exec web python manage.py migrate
   ```

5. **Popular o banco com dados de demonstração (seed):**
   ```bash
   docker compose exec web python manage.py seed_homologation
   ```

6. **Acessar a aplicação:**
   - Acesse no navegador: `http://127.0.0.1:8000/` (ou `http://localhost:8000/`);
   - Healthcheck: `http://127.0.0.1:8000/health/`.

7. **Encerrar a execução:**
   ```bash
   docker compose down
   ```

---

## 2. Persistência de Dados do Docker

- **`docker compose down`**:
  Para e remove os containers e a rede, mas **preserva os volumes de dados**. Todas as alterações no PostgreSQL (usuários criados, editais, processos) são mantidas para a próxima execução.
- **`docker compose down -v`** *(ATENÇÃO)*:
  Remove os containers **e deleta permanentemente os volumes** (inclusive `postgres_data`). Utilize apenas quando desejar resetar o banco de dados do zero.

---

## 3. Ambiente Local com SQLite (Execução Rápida sem Docker)

Caso prefira rodar sem Docker para testes pontuais ou desenvolvimento offline leve:

- O projeto suporta SQLite configurado via `.env` (ou fallback padrão);
- Requisitos: Python 3.12+;
- Comandos:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -e ".[dev]"
  cp .env.example .env
  python manage.py migrate
  python manage.py seed_homologation
  python manage.py runserver
  ```

---

## 4. Otimização do Contexto Docker e `.dockerignore`

O arquivo `.dockerignore` na raiz do repositório é indispensável para evitar que artefatos pesados da máquina host sejam enviados ao daemon do Docker durante o build.

Estão explicitamente ignorados:
- Ambientes virtuais locais (`.venv`, `venv`, `env`);
- Arquivos de banco locais (`db.sqlite3`, `*.sqlite3`);
- Arquivos de cache e cobertura (`__pycache__`, `.pytest_cache`, `.ruff_cache`, `.coverage`, `htmlcov`);
- Arquivos compactados e planilhas volumosas (`*.zip`, `*.tar.gz`, `*.xlsx`, `*.xls`);
- Artefatos e relatórios privados (`artifacts/`, `private/`, `tmp/`);
- Variáveis de ambiente reais com credenciais (`.env`, `.env.*` — preservando `!.env.example`);
- Lixo de sistema operacional (`.DS_Store`).

---

## 5. Nota Importante para Usuários de macOS (iCloud Drive / File Provider)

No macOS, se o repositório for clonado dentro de pastas sincronizadas pelo iCloud Drive (como `~/Documents` ou `~/Desktop`) com a opção **"Otimizar Armazenamento no Mac"** (Optimize Mac Storage) ativada:

- Arquivos locais podem ser descarregados pelo sistema operacional tornando-se **`dataless`** (arquivos sob demanda);
- Leituras por ferramentas como Git, Docker e indexadores podem sofrer lentidão severa, timeouts ou erros como `Operation canceled`;
- **Recomendação:** Para desenvolvimento no macOS com máxima performance e estabilidade de I/O, clone repositórios preferencialmente em diretórios fora do escopo do iCloud, como `~/Developer` ou `~/Projects`.
