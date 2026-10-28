# GreenMind 🌱

**Une serre virtuelle pour comprendre la chaîne complète d’un système IoT : simulation, MQTT, stockage, API et commandes acquittées.**

GreenMind simule trois bacs indépendants — **basilic, thym et romarin** — soumis à une même journée météo synthétique. Chaque espèce possède son profil de dessèchement, ses seuils d’alerte et son arroseur virtuel. L’utilisateur peut faire évoluer la simulation, provoquer une sécheresse et confirmer un arrosage dont il suit ensuite l’exécution.

Projet pédagogique en développement, conçu pour une démonstration locale. Les données et coefficients sont illustratifs : ils ne constituent ni des mesures réelles ni des recommandations agronomiques. Aucune pompe physique n’est pilotée.

## Ce qui fonctionne

- Une journée de 24 heures, avec une météo variable commune aux trois bacs.
- Pause, reprise, avance d’une heure virtuelle et injection d’humidité sur un bac.
- Transport MQTT réel via Mosquitto, contrats JSON stricts et stockage SQLite.
- Alertes de sécheresse persistantes, réarmement et journal filtrable par bac.
- API REST FastAPI pour consulter et piloter la serre.
- Arrosage en deux étapes : **proposition → confirmation → commande MQTT → acquittement → mesure après effet**.
- Protection contre les doublons, anciennes sessions, révisions périmées et commandes concurrentes ; repos d’arrosage par bac et suivi des exécutions incertaines.

Les briques **B1 à B5 sont réalisées**. Les deux pages Streamlit, les scripts de lancement/reset et l’assistant RAG intégré restent à construire. Les scripts d’expérimentation FAISS/MiniLM présents dans `scripts/` ne constituent pas encore un assistant applicatif.

## Architecture

```mermaid
flowchart LR
    U[Utilisateur / documentation interactive] --> API[API REST FastAPI]
    API -->|Contrôles et arrosages confirmés| MQTT[Broker Mosquitto]
    MQTT --> SIM[Simulateur des trois bacs]
    SIM -->|Mesures et acquittements| MQTT
    MQTT --> ING[Service d’ingestion]
    ING --> DB[(SQLite)]
    API -->|Lecture des états et résultats| DB
    API -->|Persistance des propositions et commandes| DB
```

Les échanges MQTT utilisent le schéma **v2** et les topics `greenmind/v2/...`. L’API utilise le préfixe **`/api/v1`** : sa version est indépendante de celle du contrat MQTT.

## Installation

### Prérequis

- **Python 3.12**.
- **Docker avec Docker Compose**, pour le broker Mosquitto.
- Un environnement Unix ; le projet est développé et vérifié sur **macOS Apple Silicon**. Le verrou du simulateur utilise `fcntl`, indisponible nativement sous Windows.

Depuis le dossier qui contiendra le projet :

```bash
git clone https://github.com/jeanb1970/GreenMind.git
cd GreenMind
python3.12 -m venv .venv
source .venv/bin/activate
source scripts/runtime_env.sh
python -m pip install -r requirements.lock.txt
```

Le fichier de dépendances inclut les bibliothèques des expérimentations IA. La partie IoT ne nécessite ni Ollama ni téléchargement de modèle. L’installation des dépendances et le premier téléchargement de l’image Docker nécessitent un accès réseau.

## Essayer la simulation sans broker

Ces commandes n’écrivent pas en base et ne publient rien sur MQTT :

```bash
PYTHONPATH=src .venv/bin/python scripts/check_greenhouse.py
PYTHONPATH=src .venv/bin/python scripts/check_simulation_day.py
```

Pour piloter la journée au clavier :

```bash
PYTHONPATH=src .venv/bin/python scripts/check_simulation_day.py --interactive
```

Commandes disponibles : `etat`, `heure`, `lecture`, `humidite thym_01 18` et `quitter`. Pendant la lecture, `Ctrl+C` met en pause.

## Lancer la chaîne MQTT et l’API

Démarrer Docker, puis le broker depuis la racine du dépôt :

```bash
docker compose up -d mosquitto
```

Ouvrir **trois terminaux**, chacun dans le dossier du projet. Dans chaque terminal, préparer l’environnement :

```bash
source .venv/bin/activate
source scripts/runtime_env.sh
export PYTHONPATH=src
```

Lancer ensuite les services **dans cet ordre** :

| Terminal | Commande | Avant de continuer |
|---|---|---|
| 1 | `python -m greenmind.ingestion.main` | Attendre le message `Ingestion prête` |
| 2 | `python -m greenmind.simulator.main` | Attendre le message `Simulateur prêt en pause` |
| 3 | `python -m greenmind.api.main` | Attendre le démarrage du serveur HTTP |

La serre démarre **en pause au pas 0**. En lecture, une heure virtuelle s’écoule toutes les cinq secondes réelles. Au pas 24, la simulation s’arrête en pause.

- Documentation interactive : [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Santé des services : [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)
- État des trois bacs : [http://127.0.0.1:8000/api/v1/plants](http://127.0.0.1:8000/api/v1/plants)

Pour arrêter : `Ctrl+C` dans les trois terminaux, puis `docker compose stop mosquitto`. Pour rejouer la journée, relancer le simulateur après son arrêt : il crée une nouvelle session. Les données des anciennes sessions restent dans SQLite ; les vues courantes de l’API sélectionnent la plus récente. Les scripts de reset automatisé sont prévus en B6.

### Configuration

Les profils et les coefficients sont définis dans [`config/greenhouse.yaml`](config/greenhouse.yaml). La météo de démonstration est décrite dans [`data/readme.md`](data/readme.md).

| Variable | Valeur par défaut | Usage |
|---|---|---|
| `GREENMIND_MQTT_HOST` | `127.0.0.1` | Adresse du broker |
| `GREENMIND_MQTT_PORT` | `1883` | Port du broker |
| `GREENMIND_DATABASE_PATH` | `outputs/greenmind.sqlite` | Base utilisée par l’ingestion et l’API |
| `GREENMIND_API_HOST` | `127.0.0.1` | Adresse d’écoute HTTP |
| `GREENMIND_API_PORT` | `8000` | Port HTTP |

Appliquer les mêmes paramètres MQTT aux trois services et le même chemin de base à l’ingestion et à l’API. Le broker fourni est lié à l’interface locale ; le PoC ne fournit pas d’authentification applicative.

## Utiliser l’API

La page `/docs` permet d’exécuter les requêtes et d’inspecter leurs schémas.

| Route sous `/api/v1` | Fonction |
|---|---|
| `GET /plants` et `GET /plants/{plant_id}` | État, profil et alerte d’un bac |
| `GET /plants/{plant_id}/measurements` | Mesures récentes |
| `GET /events?plant_id=thym_01` | Journal filtré ; au plus 100 événements |
| `GET /simulation` | Session, horloge et révision courante |
| `POST /simulation/controls` | `PAUSE`, `RESUME`, `ADVANCE`, `SET_SOIL_MOISTURE` |
| `GET /simulation/controls/{control_id}` | Résultat d’un contrôle |
| `POST /plants/{plant_id}/watering-proposals` | Proposition déterministe sans effet sur la serre |
| `POST /plants/{plant_id}/watering-commands` | Confirmation d’une proposition |
| `GET /watering-commands/{command_id}` | Suivi de l’arrosage et attente éventuelle de sa mesure |

Pour provoquer un cas de démonstration : lire la révision dans `/simulation`, puis envoyer un contrôle `SET_SOIL_MOISTURE` sur `thym_01` avec `value: 18.0` et cette `expected_revision`. Attendre son résultat `APPLIED`, demander une proposition d’arrosage avec un corps `{}`, puis confirmer son `proposal_id`. L’injection nécessite une simulation en pause.

### Identifiants et confirmation d’effet

- **`run_id`** distingue chaque démarrage du simulateur.
- **`control_id` / `command_id`** identifient une demande : conserver la même clé lors d’une nouvelle tentative. Une clé réutilisée avec un autre contenu est refusée.
- **`event_id`** permet à SQLite de dédoublonner les mesures et événements reçus.

Une réponse HTTP **202** ou un **PUBACK MQTT** confirme la prise en charge ou le transport, pas l’effet de l’arrosage. Son état devient `EXECUTED` uniquement après l’acquittement métier. Sans acquittement dans les dix secondes, le suivi indique `TIMED_OUT` : l’exécution reste incertaine, les nouvelles mutations sont bloquées et aucun renvoi automatique n’est effectué. Un acquittement tardif peut résoudre cette incertitude.

Une proposition expire après 60 secondes réelles. Après un arrosage, le bac doit respecter son repos de 60 secondes réelles. Ces délais sont indépendants de l’heure virtuelle.

## Vérification

La suite automatisée ne nécessite pas de broker actif :

```bash
.venv/bin/python -m pytest tests -q
```

État vérifié à la livraison de B5 : **198 tests réussis**.

Pour les recettes avec le **vrai broker**, démarrer Mosquitto et arrêter préalablement les services Python manuels, puis lancer les scripts **l’un après l’autre** :

```bash
PYTHONPATH=src .venv/bin/python scripts/check_mqtt_pipeline.py
PYTHONPATH=src .venv/bin/python scripts/check_api.py
PYTHONPATH=src .venv/bin/python scripts/check_watering.py
```

Chaque recette démarre ses propres services avec une base temporaire et les arrête ensuite. Une seule instance du simulateur peut détenir le verrou du projet. La recette d’arrosage couvre les trois bacs, les doublons, le repos, le timeout et un acquittement tardif.

Les bases, journaux et index générés se trouvent dans `outputs/`, ignoré par Git. Une ancienne base de schéma v1 est refusée : son remplacement demande une sauvegarde et une migration ou reconstruction explicite.

## Organisation du dépôt

```text
config/                 Profils des trois bacs
data/fixtures/          Journée météo synthétique
docs/                   Cahier des charges, plan et contrats
src/greenmind/
  domain/               Calculs de dessèchement, alertes et arrosage
  simulator/            Horloge, états et traitement des commandes MQTT
  ingestion/            Validation des messages et persistance
  db/                   Modèles SQLite et transactions
  api/                  API REST et publication des commandes
scripts/                Contrôles locaux, recettes MQTT et essais IA
tests/                  Tests automatisés
```

## Documentation et suite du projet

- [Cahier des charges v1.4](docs/Cahier_des_Charges_v1.4_Serre.md)
- [Plan de réalisation et résultats par brique](docs/Plan_de_realisation_v1.4.md)
- [Contrats MQTT, API et arrosage](docs/contracts.md)
- [Données et conventions de simulation](data/readme.md)

La prochaine étape est **B6** : deux pages Streamlit — serre et console — et gestion du lancement, de l’arrêt et du reset. Les étapes suivantes portent sur trois fiches horticoles sourcées, un assistant local contextualisé et une démonstration reproductible hors ligne.
