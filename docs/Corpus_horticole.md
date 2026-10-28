# Corpus horticole et index local

## Documents et sources

Le corpus contient exactement trois fiches de synthèse originales en français :

| Fiche | Espèce | Source primaire consultée le 28 octobre 2026 |
|---|---|---|
| [Basilic](../knowledge/basilic.md) | *Ocimum basilicum* | [University of Minnesota Extension](https://extension.umn.edu/garden-and-home/yard-and-garden/yard-and-garden-problems/growing-basil) |
| [Thym](../knowledge/thym.md) | *Thymus vulgaris* | [Royal Horticultural Society](https://www.rhs.org.uk/herbs/thyme/grow-your-own) |
| [Romarin](../knowledge/romarin.md) | *Salvia rosmarinus* | [Royal Horticultural Society](https://www.rhs.org.uk/herbs/rosemary/grow-your-own) |

Les sections des sources vérifiées concernent l’arrosage, le drainage et la culture
en contenant : « Watering » et les indications générales pour le basilic ;
« Planting », « Watering » et « Problem Solving » pour le thym et le romarin.
Les textes français sont des synthèses courtes, sans copie d’article ni d’image.
Les droits des publications externes restent à leurs titulaires ; aucune licence
ouverte n’est revendiquée pour leurs textes originaux.

Chaque fiche comporte trois sections : besoins en eau, substrat et drainage,
chaleur et culture en bac. Les valeurs numériques de `config/greenhouse.yaml`
sont des paramètres de simulation ; les sources ne valident pas ces pourcentages,
ces durées ni les coefficients d’évaporation. Les fiches ne permettent pas un
diagnostic certain de maladie ou de cause d’un symptôme.

## Préparer le modèle

Le moteur utilise `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`,
révision figée `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, et FAISS en produit
scalaire sur des vecteurs normalisés. Les embeddings ont 384 dimensions.

Avant une première utilisation, avec un accès réseau, charger cette révision dans
le cache Hugging Face de l’utilisateur :

```bash
source scripts/runtime_env.sh
PYTHONPATH=src .venv/bin/python - <<'PYTHON'
from sentence_transformers import SentenceTransformer
from greenmind.rag.index import MODEL_NAME, MODEL_REVISION
SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION, device="cpu")
PYTHON
```

Le moteur d’indexation et de recherche charge ensuite uniquement les fichiers
locaux (`local_files_only=True`). Un modèle absent provoque une erreur ; aucun
téléchargement implicite ne doit être nécessaire pendant la démonstration.

## Construire et vérifier hors ligne

Depuis la racine du dépôt :

```bash
source scripts/runtime_env.sh
PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/check_knowledge.py --build
```

Le script valide les trois fiches, construit l’index, le recharge puis recherche
des passages pour chaque plante. Les citations comprennent l’extrait exact, la
section locale et l’URL source. Pour vérifier l’index dans un autre processus sans
le reconstruire :

```bash
source scripts/runtime_env.sh
PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/check_knowledge.py
```

Aucun service MQTT, API ou Ollama n’est nécessaire pour cette recette documentaire.

## Validation des fiches

Le front matter YAML exige : `doc_id`, `plant_id`, `title`, `botanical_name`,
`source_title`, `source_url`, `consulted_on`, `usage_note`. L’URL est en HTTPS,
la date au format de date `AAAA-MM-JJ`, et l’identité correspond au fichier.

Le chargeur refuse une fiche vide, une métadonnée absente ou inconnue, une URL ou
une date invalide, une identité incohérente, un thème manquant, dupliqué ou vide,
et un corpus autre que les trois fiches attendues. Chaque section constitue un
passage, sans mélange entre espèces ni découpage arbitraire au milieu d’une phrase.

## Persistance et citations

L’index est enregistré dans `outputs/rag/knowledge/`, ignoré par Git. Une génération
contient `index.faiss` et `manifest.json`. Le pointeur `CURRENT` est remplacé
atomiquement après écriture complète de la génération ; un échec de reconstruction
laisse l’ancienne génération disponible.

Le manifeste enregistre le modèle et sa révision, les dimensions, l’empreinte
FAISS et la liste ordonnée des passages. Chaque passage conserve :

- `doc_id`, `chunk_id`, titre, plante et thème ;
- section, ancre et chemin local de la fiche ;
- source, URL, date de consultation et note d’usage ;
- empreinte SHA-256 du document et extrait exact.

`chunk_id` est un identifiant documentaire stable, par exemple
`fiche_thym::drainage`. Il n’utilise pas les compteurs des échanges IoT.

Au rechargement, une modification du corpus, un modèle incompatible ou un fichier
FAISS incohérent impose une reconstruction explicite. Le moteur vérifie la
correspondance intégrale des passages avec le corpus avant d’utiliser les vecteurs.
La recherche filtre la plante choisie et renvoie au plus cinq passages. Chaque
citation comporte un lien local tel que `knowledge/thym.md#substrat-et-drainage`.
L’extrait est une portion exacte de la fiche, consultable sans accès au site source.

Un score vectoriel mesure une proximité textuelle, pas une preuve de pertinence ou
une certitude horticole. Le module retourne des passages et n’exécute aucune action
sur la serre. La génération de réponse contextualisée et la gestion des questions
sans source appartiennent à la couche assistant.

## Tests

```bash
source scripts/runtime_env.sh
.venv/bin/python -m pytest tests/test_knowledge.py -q
```

Les tests de stockage utilisent un encodeur déterministe pour isoler les erreurs
de validation et de persistance. La recette `check_knowledge.py` utilise réellement
MiniLM et FAISS, avec le modèle préparé localement.
