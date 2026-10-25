#!/bin/zsh
set -e

cd "$(dirname "$0")/.."

# Charger les paramètres de l'environnement Python
source scripts/runtime_env.sh

exec .venv/bin/python3 -X faulthandler scripts/test_rag.py
