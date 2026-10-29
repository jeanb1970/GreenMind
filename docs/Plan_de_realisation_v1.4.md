# GreenMind v1.4 — Réalisation par briques

**Date :** 27 octobre 2026.  
**Cible :** [CDC v1.4](Cahier_des_Charges_v1.4_Serre.md).  
**Avancement au 28 octobre :** B0 validée, **B1 à B8 réalisées et testées** ; B9 à réaliser. Les trois bacs sont raccordés à MQTT, ingérés dans SQLite avec gestion atomique des alertes et du journal, et consultables/pilotables via l'API REST FastAPI (/api/v1).

**Échéance confirmée : jeudi 5 novembre 2026.** Disponibilité : environ deux tiers des journées de semaine, **aucun travail le week-end**. Du 28 octobre au 4 novembre, six jours ouvrés représentent environ quatre journées pleines équivalentes, auxquelles s'ajoute seulement le reliquat disponible du 27 octobre. Aucun nombre d'heures quotidien n'est présumé.

## 0. Calendrier révisé et arbitrages validés

Le périmètre v1.4 complet n'est pas un engagement crédible dans cette capacité, compte tenu de l'API, des commandes, des fronts et du RAG applicatif encore à construire. Les six demandes restent la cible produit. Les réductions ci-dessous constituent le **périmètre de livraison validé par Jean le 27 octobre 2026**. Les ambitions reportées restent des évolutions après la soutenance.

### Périmètre validé pour la soutenance

| Élément | Décision | Gain et conséquence |
|---|---|---|
| Trois plantes et trois arroseurs | Conserver | Cœur de la comparaison ; réutiliser une même logique paramétrée |
| Journée météo variable | Conserver un CSV synthétique fixe et une seule vitesse accélérée | Pas de recherche météo historique ni sélecteur de vitesses |
| Simulation interactive | Conserver pause, reprise, avance de +1 heure et injection d'humidité | Reporter avance vers une heure arbitraire et opérations groupées |
| Second front | Deux pages dans une seule application Streamlit : serre et console | Un seul processus et lancement ; remplace les deux applications séparées, tout en gardant deux vues distinctes |
| Historique | Derniers événements persistants de l'exécution courante, filtre par bac, limite serveur | Reporter filtres temporels avancés et navigation entre anciennes exécutions |
| RAG | Trois fiches Markdown sourcées, une par espèce, recherche et génération locales réelles | Reporter l'import PDF générique, l'extraction et la citation par page ; couverture PDF non revendiquée |
| Questions IA | Une plante sélectionnée à la fois | Reporter la comparaison automatique des trois espèces ; la comparaison des règles reste visible dans le tableau de bord |
| Présentation | Cartes, tableau et courbes sobres | Pas de dessin animé de serre, de personnalisation graphique ni d'export |

Les reports validés concernent l'import PDF, les applications séparées, la comparaison RAG multi-espèces et les commandes/filtres avancés. Le CDC et ses critères A14 ont été alignés sur cette livraison : quatre processus Python, trois fiches Markdown et deux pages. MQTT réel, RAG local, confirmation, acquittement, reset et répétitions restent obligatoires.

### Calendrier de travail proposé

| Date | Priorité | Point de contrôle |
|---|---|---|
| Mardi 27 octobre — reliquat | Cadrage et arbitrage, préparation B1 | Périmètre de soutenance explicite |
| Mercredi 28 octobre | B1/B2 : profils et moteur journalier | Trois états indépendants, pause/avance/injection testables localement |
| Jeudi 29 octobre | B3/B4 : pipeline, alertes et API minimale | Trois bacs consultables, événements persistants |
| Vendredi 30 octobre | B5 : arrosage et cycle de lancement/reset | Proposition → confirmation → effet unique → acquittement pour les trois bacs |
| Samedi 31 octobre et dimanche 1er novembre | **Aucun travail** | Aucun jalon ni rattrapage prévu |
| Lundi 2 novembre | Interfaces sobres et intégration RAG minimale | Parcours utilisateur complet ; objectif de gel fonctionnel le soir |
| Mardi 3 novembre | Recette hors ligne, corrections bloquantes et supports | Fonctionnement complet vérifié ; aucun ajout de fonction |
| Mercredi 4 novembre | Répétitions chronométrées et sauvegarde | Deux parcours après reset, capture de secours |
| Jeudi 5 novembre | Présentation | Vérification de lancement uniquement |

Même réduit, ce calendrier reste tendu, particulièrement le 2 novembre. Préparer les trois fiches sourcées et vérifier l'appel LLM local dans les créneaux dégagés avant cette date ; si aucun créneau ne se libère, le retard doit être déclaré au point de contrôle du vendredi, pas absorbé le week-end. Les tests sont réalisés au fil de chaque brique, pas uniquement le 3 novembre.

**Points de décision :**

- Le 29 octobre au soir : sans pipeline des trois bacs et API de lecture opérationnels, réestimer immédiatement la charge restante.
- Le 30 octobre au soir : sans boucle d'arrosage acquittée et préparation RAG suffisante, revoir avec Jean ce qui pourra réellement être montré. Aucun rattrapage prévu le week-end.
- Le 2 novembre au soir : geler les ajouts, consigner les manques et conserver les 3–4 novembre pour la fiabilité et la présentation. Une fonction absente reste annoncée comme telle.

## 1. Ordre et preuves de fin de brique

| Brique | Résultat concret | Principaux fichiers concernés ou à créer | Preuve avant passage à la suite |
|---|---|---|---|
| B0 — Cadrage | Six ajouts classés, cible cohérente, parcours de démo écrit | CDC v1.4 et présent plan | Exigences, choix proposés et inconnues distingués |
| B1 — Trois profils | Une configuration de serre validée et trois états indépendants | `config/greenhouse.yaml`, `greenhouse_config.py`, `domain/greenhouse.py`, `tests/test_greenhouse.py` | Même météo, trois profils ; une modification ne touche pas les autres ; ancienne suite compatible avec la transition |
| B2 — Journée et horloge | CSV journalier variable et moteur pilotable sans réseau | fixture, `data/README.md`, `simulator/weather.py`, nouveau moteur d'état/horloge | 24 pas, pause, avance, lecture accélérée et injections déterministes ; scénario 32 % vérifié |
| B3 — Contrats et pipeline | Trois bacs transitent réellement par MQTT jusqu'à SQLite | `docs/contracts.md`, `schemas.py`, `simulator/main.py`, ingestion, modèles SQL, scripts de contrôle | Schéma v3, identités/session/révisions, sauvegarde/reconstruction base documentée, dédoublonnage avec vrai broker |
| B4 — Alertes, journal et API | État des trois bacs et historique consultables via REST | `domain/alerts.py`, persistance alertes/journal, `api/`, tests d'intégration | Injection puis ouverture/clôture d'alerte atomique, journal borné et filtré par bac, erreurs et rollback vérifiés |
| B5 — Trois arroseurs | Boucle de commande complète sans IA | règles, propositions, MQTT API, commandes simulateur, acquittements SQL | Pour chaque bac : proposition → confirmation → effet unique → ack ; refus et timeout |
| B6 — Deux pages | Tableau de bord et console contrôlent la même application | `dashboard/app.py`, `dashboard/charts.py`, `dashboard/style.py`, routes de contrôle, scripts start/stop/reset | Pause/avance/injection depuis le front, effet via MQTT visible dans le journal ; deux cycles de reset |
| B7 — Corpus Markdown | Trois fiches sourcées et index local traçable | `knowledge/`, préparation/extraction RAG, manifeste, tests | Une fiche par espèce ; chaque citation retrouve sa section et son extrait ; fiche invalide rejetée |
| B8 — Assistant intégré | Explications contextualisées pour chaque bac | `rag/assistant.py`, API assistant, front, tests/questions de recette | Mesures exactes, sources pertinentes, aucune action depuis le LLM, timeout sans blocage IoT |
| B9 — Gel et soutenance | Parcours complet répétable et documenté | README, guide démo, résultats de recette, supports | A14-01 à A14-13, hors ligne, deux répétitions chronométrées, sauvegarde/capture de secours |

B1/B2 disposent de tests et contrôles locaux. La migration B3 est terminée : `config/greenhouse.yaml` est l’unique configuration, tous les producteurs et consommateurs utilisent le schéma MQTT v3. L’ancien fichier `config/plants.yaml` et son chargeur ont été retirés.

Le contrat des contrôles est défini en B3 ; son application par le simulateur et son suivi API sont terminés en B6. B4 utilise un producteur de test pour vérifier les mesures marquées `modification_manuelle`, sans écrire directement dans les tables. B5 peut être démontrée via l'API avant la construction des fronts.

## 2. Première brique de code : B1 — réalisée

**Objectif pédagogique :** remplacer « une plante codée en dur » par « trois profils configurés », tout en conservant une seule logique de calcul.

1. Relire les consommateurs de `load_plant_config` et les tests existants ; exécuter une suite de référence et consigner le résultat réellement obtenu.
2. Introduire le modèle de serre et les identités de bac/arroseur. Vérifier les contraintes et doublons ; conserver les messages en français.
3. Ajouter les trois profils et séparer leurs états. Conserver la fonction pure de dessèchement ; préciser ses unités plutôt que multiplier trois implémentations.
4. Ajouter des tests utiles : identités uniques, profil absent/inconnu, seuils incohérents, résultats déterministes et absence d'effet sur un autre bac.
5. Faire un contrôle local montrant les trois profils et l'évolution calculée sous une même météo. Expliquer ce qui vient du paramétrage pédagogique.
6. Mettre à jour le statut de la brique avec fichiers modifiés, vérifications réellement effectuées et prochaine manipulation.

**Résultats observés :** sous 25 °C et 50 % d'humidité de l'air, une heure virtuelle fait passer le basilic de 50 à 47,5 %, le thym de 35 à 33,75 % et le romarin de 40 à 38,4375 %. À 32 %, seul le basilic ouvre une nouvelle alerte. Les tests vérifient notamment les profils invalides, les identités, l'immuabilité de la configuration, le déterminisme et l'isolation entre bacs/exécutions.

**Rejouer la manipulation locale :**

```bash
cd /Users/jean/Projects/GreenMind
PYTHONPATH=src .venv/bin/python3 scripts/check_greenhouse.py
```

**Rejouer les tests :**

```bash
cd /Users/jean/Projects/GreenMind
source scripts/runtime_env.sh
PYTHONPATH=src .venv/bin/python3 -m pytest tests -q
```

Cette brique ne modifie pas la base et ne publie aucun message. Les paramètres d'arrosage sont configurés mais les commandes restent à implémenter en B5. B2 est désormais réalisée (voir ci-dessous). Prochaine brique : B3, contrats et raccordement MQTT des trois bacs.

**Hors B1 :** nouvelle API, fronts, commandes d'arrosage et extraction PDF. Ces éléments disposent de leurs propres preuves d'acceptation.

## 3. Discipline pour une démo maîtrisée

- Chaque brique livre une manipulation courte que Jean peut refaire et expliquer.
- Les tests d'une brique visent ses risques : isolation des bacs, horloges, doubles commandes, sources ou reprise ; les tests existants sont conservés/adaptés sans prétendre qu'ils valident des fonctions nouvelles.
- Les décisions de simulation sont consignées avec leurs unités et leur statut illustratif.
- Les scripts réutilisables vont dans `scripts/`, les tests dans `tests/`, les résultats constatés dans une fiche de recette.
- Les seuils, scénario, modèle et corpus sont gelés avant les répétitions ; les changements pendant la préparation finale se limitent aux défauts bloquants.
- Le calendrier ci-dessus est contrôlé à chaque brique. Une insuffisance de temps entraîne un arbitrage explicite, pas une suppression silencieuse de deux plantes ou du second front.

## 4. Points à fixer lors des briques

| Point | Moment | Règle provisoire |
|---|---|---|
| Disponibilité effective et durée de présentation | Au fil du planning et avant répétitions | Échéance du 5 novembre confirmée ; deux tiers des journées de semaine, aucun week-end ; durée orale à confirmer |
| Seuils et coefficients | B1/B2 | Valeurs pédagogiques proposées dans le CDC, validées par le scénario |
| Courbe météo précise | B2 | Journée synthétique d'été, ambiance commune, valeurs explicitement non mesurées |
| Base SQLite | B3 | Sauvegarde puis migration ou reconstruction explicite des données de développement |
| Corpus exact et droits | B7 | Trois fiches Markdown sourcées ; PDF reportés après soutenance |
| Durée et latence de démo | B8/B9 | Mesures sur le Mac et répétitions, aucun temps garanti sans observation |


## 5. B2 — Journée météo et horloge : réalisée le 27 octobre

Fichiers : `data/fixtures/weather_greenhouse_day.csv`, `simulator/engine.py`,
`tests/test_simulation_engine.py`, `scripts/check_simulation_day.py` et
`data/README.md`.

Résultats : 24 intervalles variables, pause initiale et finale, avance de +1 h,
lecture à 5 secondes par heure virtuelle, injection isolée avec avant/après,
révisions et snapshots immuables. Suite complète : **155 tests réussis**.
Le contrôle scripté des 24 heures a été exécuté. Les contrôles de pause,
reprise et injection sont aussi disponibles via `--interactive`.

Les 28 nouveaux cas couvrent notamment l'égalité lecture/avance manuelle,
l'absence de saut de pas après un retard, les données invalides, la fin de
journée, les fuseaux et l'isolation des injections. Les transitions sont locales ;
il n'y a pas encore de journal SQL ni d'acquittement MQTT des commandes de simulation.

La migration en B3 a intégré ces règles avec les contrats réseau, la
session, le dédoublonnage et la persistance.

## 6. B3 — Contrats et pipeline : réalisée le 27 octobre

Fichiers : `docs/contracts.md`, `src/greenmind/schemas.py`, `src/greenmind/db/models.py`,
`src/greenmind/db/readings.py`, `src/greenmind/db/session.py`, `src/greenmind/simulator/main.py`,
`src/greenmind/simulator/mqtt_service.py`, `src/greenmind/simulator/controls.py`,
`src/greenmind/ingestion/main.py`, `src/greenmind/ingestion/handler.py`,
`tests/test_pipeline.py`, `scripts/check_mqtt_pipeline.py`, `scripts/check_database.py`.

Résultats :
- Contrats techniques v1.4 formalisés dans `docs/contracts.md` (schéma courant v3, `greenmind/v3/`).
- Validation stricte Pydantic (`TelemetryV3`, `SimulationControl`, `SimulationEvent`).
- Bascule des trois bacs (`basilic`, `thym`, `romarin`) via Mosquitto QoS 1 vers SQLite (`sensor_readings`, `simulation_runs`, `simulation_events`).
- Commandes de simulation (`pause`, `reprendre`, `avancer_1_heure`, `modifier_humidite_sol`), dédoublonnage par `event_id` et `control_id`, protection contre les révisions périmées, battement de cœur (`signal_presence`) en pause et rejet strict des messages non conformes.
- Validation de la structure SQLite propre (WAL, timeout 5000 ms, clés étrangères actives).
- Suite de tests : 37 tests de pipeline (`tests/test_pipeline.py`) et suite complète `pytest` réussie (127 tests).
- Preuve réelle sur deux processus et broker validée avec succès via `scripts/check_mqtt_pipeline.py`.

Prochaine brique : B4, alertes, journal et API REST (réalisée ci-dessous).

## 7. B4 — Alertes, journal et API REST : réalisée le 27 octobre

Fichiers : `src/greenmind/db/models.py`, `src/greenmind/db/readings.py`,
`src/greenmind/api/schemas.py`, `src/greenmind/api/dependencies.py`,
`src/greenmind/api/routes.py`, `src/greenmind/api/app.py`, `src/greenmind/api/main.py`,
`tests/test_alerts.py`, `tests/test_api.py`, `scripts/check_api.py`.

Résultats :
- Persistance atomique des alertes (table `alerts`) et du journal d'événements (table `greenhouse_events`) lors de l'enregistrement de chaque mesure.
- Détection du cycle complet de sécheresse selon les seuils propres à chaque bac (ouverture sous seuil bas, maintien jusqu'au réarmement, clôture atomique et réouverture ultérieure).
- Journal unifié avec ordre monotone par séquence SQL, filtre optionnel par bac et limite serveur de 100 événements.
- Surface REST FastAPI complète sous `/api/v1` : `GET /health`, `GET /plants`, `GET /plants/{plant_id}`, `GET /plants/{plant_id}/measurements`, `GET /events`, `GET /simulation`, `POST /simulation/controls` (202 avec clé d'idempotence et publication MQTT) et `GET /simulation/controls/{control_id}`.
- Codes d'erreur conformes : 404 pour bac inconnu, 409 pour conflit de révision, 422 pour paramètre invalide.
- Suite de tests : 8 nouveaux tests d'alertes (`tests/test_alerts.py`), 10 tests d'intégration API (`tests/test_api.py`), portant la suite globale à **145 tests réussis** (100 %).
- Preuve réelle bout-en-bout validée par `scripts/check_api.py` (cycle complet : simulation -> Mosquitto -> ingestion -> SQLite atomique -> API REST FastAPI -> forçage -> alerte ouverte -> réarmement -> alerte fermée et journal).

Prochaine brique : B5 — Trois arroseurs (boucle de commande proposition / confirmation / acquittement).


## 8. Vérification et corrections B3/B4 — 28 octobre

- Les messages MQTT portant le drapeau `retain` sont rejetés avant toute écriture, puis acquittés comme rejets définitifs.
- Les mesures tardives restent consultables dans l’historique sans ouvrir ou fermer une alerte ni rejouer un forçage dépassé.
- Les contrôles REST sont persistés dans `simulation_controls` avant publication. Les rejeux conservent exactement le même message MQTT, y compris après redémarrage de l’API ou échec de publication. Les collisions de contenu retournent 409 ; un contrôle déjà acquitté n’est pas republié.
- L’API respecte `GREENMIND_DATABASE_PATH`, comme l’ingestion. L’ajout de la table des contrôles préserve les données des bases existantes ; aucune base existante n’est effacée implicitement.
- Les consignes obsolètes ont été remplacées dans la documentation des données et du plan. Le calcul pur de dessèchement reste utilisé par les trois bacs.
- Validation : **159 tests réussis sans avertissement**, recettes MQTT B3 et B4 réussies avec Mosquitto local, et contrôle de l’environnement réussi. La recette B4 vérifie aussi le rejeu REST après acquittement et le refus d’une collision de clé.


## 9. B5 — Trois arroseurs : réalisée le 28 octobre

Fichiers : `domain/arrosage.py`, `simulator/arrosage.py`, `db/arrosage.py`,
`api/arrosage.py`, contrats MQTT dans `schemas.py`, nouveaux modèles SQL,
raccordements du moteur, du transport et de l’ingestion,
`tests/test_arrosage.py` et `scripts/check_arrosage.py`.

Résultats :
- Proposition déterministe sous le seuil bas, durée plafonnée, motif et humidité prévue explicites ; confirmation séparée et proposition consommable une seule fois.
- Revalidation de fraîcheur, session, révision, seuil et repos. Propositions valables 60 secondes, suivi sans ACK déclaré incertain après 10 secondes, repos de 60 secondes réelles par bac.
- Persistance avant envoi, clés d’idempotence et refus des confirmations concurrentes. Aucun renvoi automatique après échec, timeout ou redémarrage de l’API.
- Une commande d’arrosage en cours dans toute la serre ; contrôles de simulation bloqués pendant une exécution incertaine ou l’attente de mesure après ACK.
- Effet virtuel unique ciblé, horloge météo inchangée, ACK corrélé, suivi `exécuté`/`refusé`, timeout et résolution tardive journalisés. Télémétrie après effet et clôture de l’alerte ingérées atomiquement ensemble.
- **198 tests réussis** : cycle des trois bacs, isolement, doublons, concurrence, expiration, anciennes sessions, révisions, repos, durée plafonnée, validation réseau, rollback et reprise API sans republication.
- Recette réelle `scripts/check_arrosage.py` réussie : timeout malgré PUBACK sur un topic sans consommateur, mutations bloquées, refus tardif corrélé ; pour chaque bac, proposition → confirmation → effet unique → ACK → mesure, puis rejouabilité REST/MQTT et repos vérifiés. Recette B4 de nouveau réussie.

```bash
PYTHONPATH=src .venv/bin/python scripts/check_arrosage.py
```

Le broker Mosquitto doit fonctionner et aucun autre simulateur ne doit détenir le
verrou du projet. La recette utilise une base temporaire et arrête ses processus.
Aucune base de démonstration n’est effacée.

Prochaine brique : **B6 — Deux pages Streamlit, lancement/arrêt et reset contrôlé**.


## 10. B6 — Première interface et lanceur local, 28 octobre

Deux vues Streamlit : cartes et courbes, propositions/confirmations et journal
sur Serre ; pause/reprise/avance et injection sur Console. Tous les échanges
passent par REST. Les clés de confirmation sont conservées dans la session UI.
Le rafraîchissement est manuel par le bouton Actualiser.

`scripts/demo.py start|stop|reset` lance les quatre services après Mosquitto,
attend leur disponibilité et vérifie les processus enregistrés avant arrêt.
Le reset conserve la base et crée une nouvelle session. Deux resets successifs
et l’arrêt ont été exécutés avec succès ; un test Streamlit vérifie les deux vues.
L’intégration RAG reste à réaliser en B7/B8.


## 11. Nommage validé et contrat v3 — 28 octobre

Les décisions de `Nommage_champs_valide.md` sont appliquées à la configuration,
aux modèles, messages, API, interfaces, scripts et tests. MQTT utilise désormais
`schema_version: 3` et `greenmind/v3`, pour refuser les anciens formats.
Les clés lisibles sont allouées par compteurs atomiques persistants dans
`outputs/identifiers.sqlite`, distinct de la base de serre. Leurs valeurs ne sont
pas remises à zéro par le reset de session ou la reconstruction de la base.
Les dates publiques et stockées utilisent l’heure belge et les précisions validées.

À la demande de Jean, la base principale a été reconstruite sans conserver
l’ancienne. La commande `scripts/reset_database.py` vérifie l’arrêt des services
avant de reconstruire les tables ; elle préserve le fichier des compteurs.
Les contrats techniques, le README et la documentation météo décrivent le format
courant et la procédure de reconstruction.


Validation du renommage : **209 tests réussis**. Les recettes MQTT réelles B3,
B4 et B5 sont réussies au schéma 3. La démo a été redémarrée ; les réponses REST
et les lignes SQLite ont été contrôlées avec les noms retenus, les identifiants
lisibles et les dates belges. Aucun commit/push n’est inclus dans cette opération.


## 12. B7 — Corpus et index local : réalisée le 28 octobre

Trois fiches originales en français dans `knowledge/`, sourcées auprès de la RHS
et de University of Minnesota Extension. Neuf sections indexées, avec métadonnées
strictes, extrait exact, chemin/ancre locale, URL, date de consultation et empreinte.
Les seuils de simulation restent explicitement distincts des connaissances sources.

`rag/corpus.py` valide et découpe les sections ; `rag/index.py` construit un index
FAISS de vecteurs MiniLM normalisés. La révision du modèle est figée et chargée
localement. Le manifeste lie modèle, empreintes et passages ; la publication par
génération évite un couple manifeste/index partiellement remplacé. Une modification
du corpus impose une reconstruction explicite.

Validation : **224 tests réussis**, dont 15 tests documentaires. La recette réelle
`check_knowledge.py --build` a construit puis rechargé neuf vecteurs de 384 dimensions
avec MiniLM local et vérifié des citations pour chacune des trois espèces, en mode
hors ligne. Procédure et sources : `docs/Corpus_horticole.md`.

Prochaine brique : **B8 — Assistant local contextualisé, API et intégration dans la
vue Serre**, avec limites de contexte, timeout et absence de pouvoir d’action du LLM.


## 13. B8 — Assistant intégré : réalisée le 28 octobre

`rag/assistant.py` relie les passages B7 au modèle Qwen3 local. La route
`POST /api/v1/assistant/ask` lit et ferme son instantané SQLite avant génération.
Les faits et références sont construits par le serveur ; le modèle fournit une
explication qualitative et les identifiants des sources utilisées, sans outil.
Les questions hors corpus, demandes d’action, diagnostics et comparaisons sont
refusés. Une sortie non validée n’est pas présentée comme une explication fiable.

La vue Serre affiche faits, explication et extraits locaux dans des blocs distincts.
Le client asynchrone partagé est géré par le lifespan ; une seule génération est
admise avec délai de 40 secondes. Un timeout natif garde le slot jusqu’à la fin du
calcul ; une panne IA conserve les faits et l’accès aux routes de consultation.

Recette réelle `scripts/check_assistant.py` réussie sur les trois espèces, avec
Qwen3 local, citations retrouvées, lectures IoT pendant les réponses et aucune
mutation des tables métier. Second essai : 14,05 / 5,97 / 7,31 secondes ; lectures
IoT de 0,005 à 0,017 seconde. Préparation et limites : `docs/Assistant_local.md`.

Prochaine brique : **B9 — Recette finale, gel, répétitions et supports**.


Validation finale B8 : **248 tests réussis**. Les tests incluent les deux vues
Streamlit, l’affichage des sources locales, les refus, les sorties non validées,
la concurrence et le maintien du slot après un timeout natif. L’API locale a été
redémarrée seule pour activer la route, sans relancer la simulation ni l’ingestion.


## 14. Corrections du front et revalidation B8 — 28 octobre

La vue Serre affiche « Humidité du sol » et des pourcentages à deux décimales
avec virgule française. Les trois petits graphiques sont remplacés par une courbe
commune à trois séries : Basilic bleu, Thym orange, Romarin violet. Les axes sont
nommés (heure virtuelle 0–24 h, humidité 0–100 %), la légende est visible et les
infobulles affichent plante, humidité, version et origine. Les valeurs initiales
sont matérialisées par des points ; les interventions à heure constante suivent
`current_state`, sans moyenne ni décalage artificiel du temps.

Le front demande jusqu’à 100 mesures utiles par bac avec `include_presence=false`.
Le filtre SQL précède la limite et le comportement REST par défaut reste inchangé.
Les nombres restent précis dans les calculs, SQLite et les réponses API. Les faits
présentés par l’assistant et les pourcentages des motifs/journal sont formatés pour
l’affichage ; les anciens événements persistants ne sont pas réécrits.

Validation : **250 tests réussis**, dont conservation d’une étape horaire après
105 présences, coordonnées et ordre des interventions dans le graphique. Contrôle
visuel dans Streamlit sur la simulation existante, sans reset : trois séries,
axes, légende et hausse verticale du romarin à l’heure 24 visibles. Capture locale :
`outputs/demo/serre_courbes.png`. Seule l’API a été redémarrée ; ingestion et
simulateur conservés. Les nouveaux formats des libellés produits par l’ingestion
seront chargés à son prochain démarrage ; les libellés visibles sont déjà formatés
par le front.

B8 revalidée avec la recette réelle locale et une base temporaire : réponses
sourcées des trois espèces, faits exacts, refus d’action/diagnostic/hors sujet,
panne Ollama isolée et aucune mutation métier. Latences observées : basilic
15,79 s, thym 6,59 s, romarin 7,25 s ; lectures IoT pendant génération :
0,010 / 0,012 / 0,011 s. La première tentative sous bac à sable n’avait pas pu
joindre Ollama ; la recette avec accès local autorisé a réussi.

B8 reste réalisée ; la prochaine brique du plan est B9. Aucun commit ni push
réalisé pour ces corrections.


## 15. Habillage visuel des deux pages — 28 octobre

Choix confirmé par Jean : fond bleu nuit et panneaux clairs. Le bandeau utilise
une copie locale de l’illustration fournie ; la grille discrète et les accents
vert menthe reprennent son identité. Trois dessins vectoriels décoratifs distinguent
basilic, thym et romarin. Les textes et mesures restent sur des fonds contrastés ;
les colonnes se réorganisent lorsque la largeur disponible diminue, y compris avec
la barre latérale ouverte. Les contours de focus clavier restent visibles.

Deux familles au maximum : Source Sans pour l’interface et le graphique, Source
Code Pro pour les données techniques, toutes deux incluses localement dans Streamlit.
Aucune police, image ou bibliothèque visuelle distante n’est requise. Le fichier
`.streamlit/config.toml` fixe le thème, `dashboard/style.py` et
`dashboard/assets/dashboard.css` portent l’habillage. L’illustration utilisée est
conservée dans `dashboard/assets/greenmind-architecture.jpeg`, indépendante du dossier
Présentation ignoré par Git. Le PowerPoint de référence n’a pas été modifié.

Titres visibles et titres du navigateur synchronisés à chaque changement de vue :
« Serre » / « GreenMind · Serre » et « Console · Mode simulation » /
« GreenMind · Console · Mode simulation ».

Validation : trois tests dashboard réussis (navigation, commandes REST, faits et
sources de l’assistant, graphique), avec vérification des deux titres visibles.
Contrôle réel dans le navigateur des deux pages, des illustrations chargées et
du titre d’onglet ; vérification avec barre latérale ouverte et fermée. Captures :
`outputs/demo/serre_habillage.png` et `outputs/demo/console_habillage.png`.
Les données et la simulation n’ont pas été réinitialisées.


## 16. Logo d’onglet et choix Clair / Sombre — 28 octobre

Le nouveau logo fourni par Jean est conservé sans modification des pixels dans
`dashboard/assets/greenmind-logo.png`. À sa demande, le favicon affiche uniquement
le symbole de la serre : un cadre SVG carré sélectionne cette partie de l’image
originale, sur un fond très clair pour conserver le contraste dans les onglets.
Le même favicon accompagne les titres distincts Serre et Console.

Le sélecteur **Apparence** de la barre latérale propose Clair et Sombre. Le choix
appartient à l’utilisateur et reste dans sa session pendant les actualisations et
la navigation ; Clair est proposé à la première ouverture. Une option reste
obligatoirement sélectionnée. La variante claire (`dashboard/assets/light.css`)
présente un fond lumineux et des tuiles sauge légèrement plus foncées, y compris
sur la console. Le mode sombre précédent reste disponible. Aucune ressource
distante ni modification des données de simulation n’est nécessaire.

Validation : trois tests dashboard réussis, dont maintien du choix Sombre lors du
passage Serre → Console. Vérification réelle des deux apparences, de la console
claire et du lien favicon SVG dans le navigateur. Capture :
`outputs/demo/serre_light.png`.


Mise à jour du favicon le 28 octobre : remplacement par le fichier fourni
« Logo GreenMind, serre connectée minimaliste.png ». Le cadre SVG utilise ses
dimensions réelles (1254 × 1254) et affiche le symbole de serre seul, avec les
trois plantes et la rampe d’arrosage. Les modes Clair/Sombre sont conservés.
Validation du remplacement : trois tests dashboard réussis ; front Streamlit seul
redémarré pour vider son ancien favicon en cache. Le navigateur sert bien le
nouveau symbole (source 1254 × 1254), autres services conservés.


## 17. Correction de visibilité du logo et du menu — 28 octobre

Le précédent contrôle du favicon vérifiait la présence du lien SVG ; il ne prouvait
pas son affichage dans l’onglet. Le favicon utilise désormais directement le PNG
original fourni (logo complet), sans SVG imbriqué ni fonction en cache. Le même
PNG est déclaré avec `st.logo` et affiché à 160 px dans l’en-tête natif de la barre
latérale, sur un support clair en mode Clair comme Sombre. Il remplace l’ancien
nom GreenMind composé uniquement en texte. Le logo réduit reste visible dans
l’en-tête principal lorsque la barre est repliée.

Le bouton natif de fermeture est positionné en haut à droite de l’en-tête, avec
opacité et visibilité permanentes, une surface de 36 × 36 px et des couleurs
contrastées propres aux deux apparences. Il ne dépend plus du survol du menu.

Validation : trois tests dashboard réussis. Vérifications réelles : logo PNG chargé,
source favicon PNG identique, fermeture/réouverture dans les deux apparences,
visibilité de la flèche après déplacement du pointeur dans la page, présence du
logo et de l’icône PNG sur Console. Captures : `outputs/demo/logo_menu_clair.png`
et `outputs/demo/logo_menu_sombre.png`. Aucune mutation de simulation.


## 18. Traitement de la revue de code — 28 octobre

Les cinq recommandations de la revue sont appliquées :

- **INC-06** : `GREENMIND_SIMULATION_MODE=0` par défaut. Le lanceur de démo
  l’active explicitement avec `1`. Sans activation, les commandes de simulation
  retournent 403 avant accès métier, allocation d’identifiant ou publication MQTT.
  L’activation impose une adresse API locale ; la configuration est lue au démarrage.
- **INC-01-bis** : distinction entre absence de simulation, absence de mesure,
  simulateur sans présence récente, pause connectée et lecture connectée. Les
  commandes sont désactivées lorsque le simulateur est indisponible.
- **INC-02** : météo commune sur Serre, issue du même échantillon de référence
  que l’horloge : température, humidité de l’air, intervalle et provenance explicite.
- **INC-04** : seuils de chaque bac, identité de son arroseur et état à la dernière
  mesure, sans assimiler cet état à un historique des arrosages.
- **INC-16** : dossier de reprise réécrit pour distinguer l’état actuel des recettes
  historiques ; cahier des charges, contrats API et README alignés.

Aucune migration SQLite ni réinitialisation de simulation. Les acquis de B8 sont
conservés ; B9 reste à réaliser. Les 268 tests de la suite passent. Compilation
Python et contrôle des espaces du diff réussis. Vérifications dans le navigateur :
météo, seuils, arroseurs, titre distinct de Console et commandes désactivées lorsque
le signal de présence est ancien. Captures : `outputs/demo/revue_supervision.png`,
`outputs/demo/revue_seuils_arroseurs.png` et `outputs/demo/revue_console.png`.

L’API seule a été redémarrée pour charger la configuration de démo. L’état observé
signale une présence absente ; aucune relance du simulateur n’a été effectuée pour
modifier artificiellement ce constat. Aucune nouvelle recette Ollama réelle dans
cette étape ; les durées précédentes restent des résultats historiques.

Retour visuel du bouton Actualiser : ajout d’un relief au repos, d’un survol
contrasté et d’un enfoncement de 2 px avec ombre intérieure pendant l’appui,
avec couleurs propres aux deux apparences. La préférence de réduction des
animations est respectée. Le bouton conserve son actualisation REST habituelle.
Validation : 8 tests dashboard réussis ; relief et clic contrôlés dans le navigateur
en mode Clair. Capture : `outputs/demo/actualiser_relief.png`.

## 19. Cycles répétés, affichage automatique et disponibilité — livrés

Même profil météo fixe de 24 heures, cycles J1/J2/etc., sans calendrier civil ni
changement été/hiver. `jour_suivant` est disponible seulement au pas 24 ; il
conserve simulation, humidités et historique, incrémente cycle et révision, et
revient au pas 0 en pause. Les protections de conflit et d’idempotence restent
actives. La météo est rejouée et les sols continuent d’évoluer.

La télémétrie et SQLite portent `cycle` (1 pour les anciennes données). Migration
additive de la seule colonne manquante sur un schéma v3 compatible ; aucun
historique effacé. Les courbes utilisent `(cycle - 1) × 24 + heure_virtuelle` et
consultent jusqu’à 1 000 mesures utiles par bac. La supervision et les contrôles
sont dans un fragment Streamlit rafraîchi toutes les cinq secondes ; le formulaire
de question reste hors de ce fragment, pour conserver la saisie.

La santé de l’assistant est affichée avant la question, actualisée toutes les dix
secondes. `/assistant/health` vérifie Ollama et le modèle, prépare et contrôle la
recherche locale sans génération, avec états préparation/disponible/indisponible.
Le résultat documentaire est conservé trente secondes ; une panne IA laisse la
supervision utilisable.

`demo.py from-scratch` demande la saisie `EFFACER`, arrête les services enregistrés,
vérifie qu’aucun service GreenMind n’utilise les bases, puis reconstruit la base
et efface les compteurs. Aucun redémarrage automatique ; `start` démarre ensuite
une démo neuve. Le reset ordinaire conserve historique et compteurs. Aucun
from-scratch n’a été exécuté sur les données de Jean.

Validation : **280 tests réussis**, dont trois cycles continus, transport et
persistance, commande REST dédoublonnée, migration avec conservation des lignes,
affichage du bouton, avertissement IA avant question, contrôle IA sans génération,
reconstruction complète sur fichiers temporaires et refus si services actifs.
Le chargement des nouveaux services utilise `demo.py reset`, après constat que la
session précédente était au pas 24 ; son historique et ses compteurs sont conservés.

Recette réelle supplémentaire : 24 pas REST/MQTT, passage J1 → J2 depuis le
bouton de la console et comparaison exacte des trois humidités avant/après.
Lecture réelle de sept secondes puis pause vérifiée : J2 pas 1, soit 25 h cumulées.
Le front suit l’heure automatiquement ; l’assistant indique disponible sans question
ni génération. Preuves : `outputs/demo/cycle1_end.json`, `cycle2_start.json`,
`lecture_automatique.json`, `cycle2_console.png`. La session précédente est
conservée et aucun `from-scratch` n’a été exécuté sur les données réelles.

L’axe des heures cumulées affiche une décimale avec virgule ; il couvre au moins
0–24 h dès le point initial et s’étend par cycles de 24 h. Validation : 13 tests
front/cycles et vérification de la spécification avec un seul point.


## 20. Refactorisation et cohérence transversale — 29 octobre 2026

Séparation du front en point d’entrée, client REST et composants de présentation ;
centralisation du type d’action, des règles de cycles, de fraîcheur et des limites.
Correction de l’inversion des plafonds journal/mesures, avec test dépassant 100
lignes. Matrice des entités et invariants dans `docs/Coherence_code_CDC.md`, liée
au CDC, dont la table de contrôles et la description de migration sont actualisées.
Aucune reconstruction de base ni réinitialisation des services pour ce travail.

Validation : **281 tests réussis**, contrôle du diff et compilation Python.
La refactorisation n’a pas relancé les services ; les changements backend seront
chargés au prochain redémarrage contrôlé. Aucune donnée de démo modifiée.

Ajustement graphique du 29 octobre : heures entières suffixées « H », graduations
verticales suffixées « % », titres des axes masqués, hauteur portée de 340 à
510 px (+50 %). Basilic vert vif clair (#65d934), thym vert foncé (#166534),
romarin violet conservé. Cette demande remplace le précédent format à une décimale.
