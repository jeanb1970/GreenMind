#!/bin/sh

# GreenMind v1.3 — Configuration des bibliothèques natives
# Contournement du plantage observé sur macOS avec une puce Apple M3.
# La limitation des threads a permis de réussir les tests.
# La cause native exacte du plantage reste indéterminée.
# Charger ce fichier avant le démarrage des processus Python concernés.

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export TOKENIZERS_PARALLELISM=false
