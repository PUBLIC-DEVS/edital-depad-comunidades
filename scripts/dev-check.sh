#!/usr/bin/env bash
set -euo pipefail

echo "== Edital DEPAd - ambiente local =="

if ! docker info >/dev/null 2>&1; then
  echo "ERRO: Docker daemon não está disponível ou não está em execução."
  echo "Abra o Docker Desktop e tente novamente."
  exit 1
fi

echo "Docker daemon: OK"

if ! docker compose version >/dev/null 2>&1; then
  echo "ERRO: Docker Compose não encontrado."
  exit 1
fi
echo "Docker Compose: OK"

if [ ! -f .dockerignore ]; then
  echo "ERRO: .dockerignore ausente na raiz do repositório."
  exit 1
fi
echo ".dockerignore: OK"

if ! docker compose config >/dev/null 2>&1; then
  echo "ERRO: docker compose config falhou ao validar os arquivos de configuração."
  exit 1
fi
echo "docker compose config: OK"

echo
echo "Serviços declarados:"
docker compose config --services

if [ "$(uname)" = "Darwin" ]; then
  if pwd -P | grep -qE '^/Users/[^/]+/(Documents|Desktop)'; then
    echo
    echo "NOTA (macOS): O repositório está localizado em ~/Documents ou ~/Desktop."
    echo "Caso a sincronização do iCloud Drive com 'Otimizar Armazenamento' esteja ativa, arquivos locais podem ser descarregados sob demanda (dataless), causando lentidão no Docker/Git."
    echo "Recomendação: prefira clonar repositórios de desenvolvimento em ~/Developer ou ~/Projects."
  fi
fi

echo
echo "Ambiente básico pronto."
echo "Próximos passos recomendados:"
echo "  1. docker compose up --build -d"
echo "  2. docker compose exec web python manage.py migrate"
echo "  3. docker compose exec web python manage.py seed_demo"
echo "  4. Acessar http://127.0.0.1:8000/"
