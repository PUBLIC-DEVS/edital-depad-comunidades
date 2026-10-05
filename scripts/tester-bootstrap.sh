#!/usr/bin/env bash
# LOCAL DEVELOPMENT ONLY. No reset, volume deletion or automatic Git operations.
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if ! command -v docker >/dev/null 2>&1; then
  echo "Erro: instale e inicie Docker Desktop antes de executar este script." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Erro: Docker não está em execução. Inicie Docker Desktop e tente novamente." >&2
  exit 1
fi
docker compose version >/dev/null
docker compose config --quiet
docker compose up --build -d

db_container="$(docker compose ps -q db)"
if [[ -z "$db_container" ]]; then
  echo "Erro: o serviço PostgreSQL não foi criado." >&2
  exit 1
fi
db_ready=false
for ((attempt = 1; attempt <= 60; attempt++)); do
  db_health="$(docker inspect --format '{{.State.Health.Status}}' "$db_container")"
  if [[ "$db_health" == "healthy" ]]; then
    db_ready=true
    break
  fi
  if [[ "$db_health" == "unhealthy" ]]; then
    echo "Erro: PostgreSQL está unhealthy. Consulte docker compose logs db." >&2
    exit 1
  fi
  sleep 2
done
if [[ "$db_ready" != true ]]; then
  echo "Erro: PostgreSQL não ficou healthy no prazo de 120 segundos." >&2
  exit 1
fi

docker compose exec -T web python manage.py migrate --noinput
docker compose exec -T web python manage.py seed_homologation
docker compose exec -T web python manage.py check
docker compose exec -T web python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health/", timeout=10)'

cat <<ACCESS
Ambiente de homologação pronto.

URL: http://localhost:${DEPAD_WEB_PORT:-8000}/
Usuários:
homolog.admin
homolog.coordenador
homolog.distribuidor
homolog.analista
homolog.revisor
homolog.consulta

Senha inicial: Homolog.Edital#2026 (preservada em reexecuções)
Somente desenvolvimento local. Não usar em produção.
Guia: docs/MANUAL_TEST_GUIDE.md
ACCESS
