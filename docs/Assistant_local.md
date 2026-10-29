# Assistant horticole local

L’assistant combine un instantané des données du bac et des passages des fiches
horticoles locales. Il fonctionne en lecture seule et ne publie aucune commande.

## Préparation et lancement

1. Installer les dépendances du dépôt et préparer [le corpus et MiniLM](Corpus_horticole.md).
2. Démarrer le service Ollama local s’il n’est pas déjà actif, puis vérifier les
   modèles disponibles avec `ollama list`.
3. Préparer un modèle Qwen3 local avant de travailler hors ligne. Le modèle testé
   sur ce poste est `qwen3:4b-instruct`, identifiant Ollama `0edcdef34593`.
4. Démarrer GreenMind avec `.venv/bin/python scripts/demo.py start`.
5. Dans la vue **Serre**, sélectionner une plante, saisir une question et cliquer
   sur **Poser la question**. Les faits, l’explication et les sources sont séparés.

Le lanceur ne démarre ni ne termine le service Ollama de l’utilisateur. Une
indisponibilité de ce service ne bloque pas la partie IoT.

| Variable | Défaut | Rôle |
|---|---|---|
| `GREENMIND_OLLAMA_URL` | `http://127.0.0.1:11434` | Serveur de génération |
| `GREENMIND_LLM_MODEL` | `qwen3:4b-instruct` | Modèle déjà présent dans Ollama |

Définir ces variables avant de lancer l’API ou le lanceur. Si le modèle du poste
porte un autre nom, utiliser son nom exact dans `GREENMIND_LLM_MODEL`. Aucun
modèle n’est téléchargé implicitement par l’assistant. Les modèles, le corpus,
les dépendances et les images de service doivent être préparés avant la séance.

## Route REST

`POST /api/v1/assistant/ask`

```json
{
  "plant_id": "thym",
  "question": "Pourquoi le thym a-t-il besoin d’un sol drainant en pot ?"
}
```

Le corps exige une plante connue et une question non vide d’au plus 1000
caractères. Une plante inconnue retourne 404 ; un contenu invalide retourne 422.
Une panne SQL empêchant de lire les faits retourne 503.

La réponse structurée contient :

| Champ | Contenu |
|---|---|
| `plant_id` | Plante sélectionnée |
| `status` | `répondu`, `sources_insuffisantes`, `indisponible`, `occupé` ou `action_non_exécutée` |
| `facts` | Instantané SQLite et seuils du profil, fourni par le serveur |
| `explanation` | Explication documentaire validée, ou motif de refus/dégradation |
| `sources` | Citations issues du manifeste et du corpus, fournies par le serveur |
| `action_executed` | Toujours `false` |

Lorsque les faits sont disponibles, une panne IA retourne HTTP 200 avec le statut
métier `indisponible`, les faits conservés et aucune explication présentée comme
valide. Le statut HTTP n’indique donc pas à lui seul qu’une génération a réussi.

Les faits comprennent la simulation, la version d’état, les dates, les valeurs
d’humidité et de température, les seuils, l’alerte et la provenance. Ils sont
capturés **avant** la recherche ; ils ne prétendent pas décrire un état modifié
pendant la génération. `fresh` est réévalué au retour et indique si leur émission
date de moins de dix secondes. Une modification manuelle reste explicitement
identifiée par `measurement_origin: modification_manuelle`.

## Recherche et génération

- Le modèle MiniLM local est chargé à la première question ; le démarrage de l’API
  n’exige ni chargement de modèle ni connexion réussie à Ollama.
- Le manifeste et les empreintes du corpus sont revérifiés avant chaque recherche.
- La recherche est limitée à la plante sélectionnée et à trois passages ; un score
  inférieur à 0,25 est écarté. Ce filtre est une heuristique, pas une preuve de pertinence.
- Le prompt reçoit uniquement la question, les faits et les extraits sélectionnés.
  La longueur du contexte JSON est bornée à 11000 caractères ; la fenêtre du modèle
  à 4096 tokens et la sortie à 500 tokens.
- Ollama est appelé via `/api/chat`, sans streaming, avec `think: false`, température
  nulle, graine fixe et schéma JSON de sortie. La variabilité entre versions ou
  moteurs n’est pas exclue par ces paramètres.
- Un client asynchrone HTTPX2, compatible avec l’API HTTPX utilisée ici, est partagé
  par l’application via son lifespan et fermé à l’arrêt.

Référence du protocole : [documentation officielle de l’API Ollama](https://github.com/ollama/ollama/blob/main/docs/api.md).

## Séparation des responsabilités

Les faits numériques ne sont pas rédigés par le LLM : le serveur les expose
séparément. Le texte généré ne doit contenir ni nombres, ni URL, ni marqueurs de
citation inventés. Le modèle renvoie une liste d’identifiants courts parmi les
sources proposées ; le serveur retrouve lui-même les extraits, URL, sections et
liens locaux correspondants. Une référence inconnue, une sortie incomplète ou
invalide, une proposition d’appel d’outil ou certaines affirmations non autorisées
empêchent la publication de l’explication.

Les règles du prompt demandent une synthèse française fidèle aux extraits, sans
transformer drainage en sécheresse permanente ni les seuils de simulation en
prescriptions horticoles. Des contrôles supplémentaires refusent notamment les
nombres dans l’explication et les prétentions d’exécution. Ces contrôles ne
constituent pas une démonstration formelle de la justesse de toute reformulation ;
les extraits exacts restent affichés pour permettre sa vérification.

Le module n’importe aucun producteur MQTT et ne dispose d’aucun outil d’action.
Les instructions contenues dans une question ou un passage sont traitées comme
contenu documentaire, jamais comme permission d’exécuter une commande. Une demande
d’arrosage renvoie vers le parcours proposition/confirmation. Les diagnostics,
traitements et comparaisons entre plusieurs plantes sont refusés dans ce parcours.
Les questions hors du périmètre documentaire reçoivent une réponse d’insuffisance.

## Délais et disponibilité

Une seule recherche/génération est active à la fois dans le processus API. Une
seconde question reçoit `occupé`, sans file d’attente. Le délai total maximal de
réponse est de 40 secondes ; le navigateur accorde 45 secondes à la requête.
La recherche native et les lectures SQLite sont exécutées hors de la boucle
asynchrone. Aucune transaction SQL ne reste ouverte pendant la génération.

Si un calcul natif dépasse le délai, il peut encore terminer en arrière-plan ;
le slot reste réservé jusqu’à sa fin afin d’éviter de lancer un second chargement
concurrent. L’arrêt de l’application annule les tâches asynchrones et ferme son
client HTTP. Aucun échec ne déclenche une nouvelle génération automatiquement.

## Recette reproductible

Avec Ollama démarré, Qwen3 disponible et l’index déjà construit :

```bash
source scripts/runtime_env.sh
PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/check_assistant.py
```

La recette crée une base temporaire et des mesures identifiées comme modifications
manuelles. Elle interroge réellement MiniLM, FAISS et Qwen3 pour les trois plantes,
vérifie les valeurs exactes et les citations, consulte l’API IoT pendant la
requête et compare les comptes des tables avant/après. Elle teste les refus de
question hors corpus et d’action. La panne Ollama est simulée par une adresse
locale inaccessible, sans arrêter le service de l’utilisateur.

Mesures du second essai du 28 octobre 2026 sur ce poste :

| Plante | Réponse complète | Lecture IoT pendant la requête |
|---|---|---|
| Basilic | 14,05 s | 0,005 s |
| Thym | 5,97 s | 0,017 s |
| Romarin | 7,31 s | 0,008 s |

Ce sont des observations de cette recette, pas des garanties de latence. Le premier
essai, avant renforcement de la consigne de reformulation, avait duré 15,95 s,
5,48 s et 5,28 s. Les tests automatisés isolent aussi concurrence, délai maximal,
sortie invalide, références inventées, absence de source et fermeture du client.


Revalidation du 28 octobre après les corrections du front : recette réelle réussie
sur les trois plantes, aucune mutation métier, panne IA isolée. Latences mesurées :
15,79 / 6,59 / 7,25 s ; consultations IoT : 0,010 / 0,012 / 0,011 s. Les faits
numériques restent précis côté API ; leurs pourcentages affichés dans Serre sont
formatés avec deux décimales et une virgule française.
