#!/usr/bin/env bash
#
# Reset do ambiente de HOMOLOGAÇÃO/testes num passo só:
#   1. apaga todos os dados (flush — mantém o schema);
#   2. cria um usuário por papel + edital 2026 completo e publicado (seed_homologation);
#   3. garante os administradores institucionais (ensure_admins).
#
# ⚠️ DESTRUTIVO: apaga TODOS os dados do banco apontado por DATABASE_URL.
#    Use apenas em banco de teste/homologação, nunca em produção real.
#
# Uso:
#   DATABASE_URL="postgresql://USER:SENHA@HOST:5432/postgres?sslmode=require" \
#       ./scripts/reset-homologation.sh
#
# Variáveis opcionais:
#   PYTHON   interpretador a usar (padrão: .venv/bin/python)
#
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERRO: defina DATABASE_URL antes de rodar."
  echo "Ex.: DATABASE_URL='postgresql://...:5432/postgres?sslmode=require' ./scripts/reset-homologation.sh"
  exit 1
fi

PY="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PY" ]; then
  echo "ERRO: interpretador '$PY' não encontrado. Crie o venv (uv venv && uv pip install -e .)"
  echo "ou aponte com PYTHON=/caminho/para/python."
  exit 1
fi

echo ">> [1/4] Apagando todos os dados (flush)..."
"$PY" manage.py flush --noinput

echo ">> [2/4] Usuários por papel + edital 2026 completo e publicado (seed_homologation)..."
"$PY" manage.py seed_homologation

echo ">> [3/4] Garantindo administradores institucionais (ensure_admins)..."
"$PY" manage.py ensure_admins

echo ">> [4/4] Garantindo analistas e revisores da equipe (ensure_team)..."
"$PY" manage.py ensure_team --password "Homolog.Edital#2026"

cat <<'EOF'

============================================================
  Ambiente de homologação pronto. ✅
============================================================
Logins por papel (senha: Homolog.Edital#2026):
  - homolog.admin         (Administrador)
  - homolog.coordenador   (Coordenador)
  - homolog.distribuidor  (Distribuidor)
  - homolog.analista      (Analista)
  - homolog.revisor       (Revisor)
  - homolog.consulta      (Consulta)

Administradores institucionais (login via Microsoft):
  - daniel.brasileiro
  - joao.hall

Edital: HOMOLOG-LOCAL/2026 — completo e ACTIVE.
============================================================
EOF
