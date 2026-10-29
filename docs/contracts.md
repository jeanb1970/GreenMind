# Contrats techniques GreenMind — schéma 3

Le dictionnaire [Nommage_champs_valide.md](Nommage_champs_valide.md) donne les
anciens noms et les noms retenus. Le présent contrat décrit le format utilisé.
L’API applicative reste sous `/api/v1`, indépendamment de la version MQTT.

## Transport et validation

- Mosquitto local : `127.0.0.1:1883`, MQTT QoS 1, sessions non persistantes.
- Préfixe `greenmind/v3`, champ `schema_version: 3` explicite et obligatoire.
- Les anciens topics et schémas ne sont pas acceptés par les consommateurs v3.
- JSON UTF-8 strict : champs supplémentaires, types incorrects, NaN/Inf et valeurs
  hors limites sont refusés. Les messages reçus avec le drapeau retained sont rejetés.
- Un PUBACK confirme le transport ; seul un acquittement métier confirme l’effet.
- Les pertes durant une déconnexion ne sont pas automatiquement récupérées par une
  session MQTT non persistante. Le simulateur s’arrête sur perte de connexion.

## Identifiants persistants

| Champ | Exemple |
|---|---|
| `simulation` | `Simu_001 du 28 Oct. 2026 à 14:30` |
| `event_id` | `Evenement_000001` |
| `control_id` | `Controle_000001` |
| `command_id` | `Arrosage_000001` |
| `proposal_id` | `Proposition_000001` |
| `alert_id` | `Alerte_000001` |

Les compteurs sont partagés entre les processus dans `outputs/identifiers.sqlite`
(`GREENMIND_IDENTIFIERS_PATH` pour un autre emplacement). Leur incrément est atomique.
Chaque catégorie a son compteur, conservé entre sessions et reconstructions de la
base de serre. Les largeurs sont des minimums : trois chiffres pour la simulation,
six pour les autres identifiants. Des réservations abandonnées peuvent laisser des
trous ; les numéros ne sont pas réutilisés. La date de simulation est son démarrage
réel en heure belge, avec mois français, et reste fixe pendant toute la session.

Les clients peuvent réserver une clé avec `POST /api/v1/identifiers/{category}`,
`category` valant `control`, `proposal` ou `command`. La réponse contient
`identifier`. Une tentative répétée conserve la même clé et le même contenu.
Les identifiants fournis et validés font avancer la borne du compteur au besoin,
pour éviter une réallocation ultérieure. Les identifiants techniques des connexions
MQTT ne sont pas les identifiants métier des échanges.

## Dates et horloges

| Champs | Exemple |
|---|---|
| `observed_at`, `simulated_at` | `2026-07-10 12:15:10` |
| Autres champs temporels `*_at` | `2026-07-10 12:15:10.12345` |

Les chaînes représentent l’heure belge `Europe/Brussels`, sans `T`, `Z` ni
suffixe de décalage. Les instants précis ont exactement cinq décimales ; la
précision interne est ramenée à dix microsecondes pour garantir un aller-retour
identique. Les calculs internes utilisent des dates avec fuseau normalisées en UTC.
Une heure locale ambiguë ou inexistante au changement d’heure est refusée : le
format sans décalage ne permet pas de distinguer les deux occurrences d’une heure.
La journée météo simulée doit être une journée de 24 heures sans changement d’heure.

`observed_at` est le début de l’intervalle météo appliqué ; `simulated_at` est
l’heure virtuelle courante. Elles sont égales au pas initial, puis séparées d’une
heure après un pas horaire. Les délais d’expiration et de repos sont réels.

## Télémétrie

Topic : `greenmind/v3/plants/{plant_id}/telemetry`.

| Champs | Règle |
|---|---|
| `schema_version`, `event_id`, `simulation` | Version 3 et identifiants ci-dessus |
| `plant_id` | `basilic`, `thym` ou `romarin`, identique au topic |
| `observed_at`, `simulated_at`, `emitted_at` | Formats belges ci-dessus |
| `cycle` | Entier positif, 1 par défaut pour les anciens messages ; numéro du jour rejoué |
| `heure_virtuelle` | Entier 0–24 : pas du cycle courant ; heures cumulées = `(cycle - 1) × 24 + heure_virtuelle` |
| `current_state` | Compteur entier de version, au moins égal à `heure_virtuelle` |
| `paused`, `day_complete`, `arroseur_active` | Booléens |
| `air_temperature_c` | Température finie en °C |
| `air_humidity_pct`, `soil_moisture_pct` | Nombres entre 0 et 100 |
| `provenance` | `meteo_simulee` ou `meteo_historique` ; sol toujours simulé |
| `measurement_origin` | `initial`, `calcul_horaire`, `modification_manuelle`, `arrosage`, `signal_presence`, `jour_suivant` |

`day_complete` correspond au pas 24 et impose la pause. L’origine `initial`
impose le pas et la révision à zéro, au cycle 1. Chaque émission nouvelle reçoit un nouvel `event_id` ;
un doublon identique est ignoré par SQLite. Une mesure tardive reste dans
l’historique sans remplacer l’état courant ni rejouer ses transitions d’alerte.
Un signal de présence est publié toutes les cinq secondes, sans dessèchement en pause.

## Contrôles de simulation

Topic commande : `greenmind/v3/simulation/controls`.

Champs : `schema_version`, `control_id`, `simulation`, `expected_state`, `action`,
`requested_at`, `expires_at`, `plant_id`, `moist_request_pct`.

| Action | Arguments |
|---|---|
| `pause` | `plant_id` et `moist_request_pct` à `null` |
| `reprendre` | Mêmes contraintes |
| `avancer_1_heure` | Mêmes contraintes ; uniquement en pause |
| `jour_suivant` | Uniquement au pas 24 en pause ; conserve session et sol, incrémente cycle et révision, revient au pas 0 en pause |
| `modifier_humidite_sol` | Bac et humidité demandée entre 0 et 100 ; uniquement en pause |

Le simulateur vérifie la session, l’expiration et `expected_state`. L’expiration
réseau est strictement positive et au plus 60 secondes après la demande ; l’API
utilise 30 secondes. Un doublon exact retrouve le résultat d’origine sans effet
supplémentaire. Une clé avec un autre contenu est refusée.

Topic résultat : `greenmind/v3/simulation/events`.
Champs : `schema_version`, `event_id`, `simulation`, `control_id` (ou `null`),
`status`, `current_state`, `heure_virtuelle`, `simulated_at`, `emitted_at`,
`paused`, `day_complete`, `reason`.
Les statuts réseau sont `etat_actuel`, `appliqué` et `refusé`.

L’API persiste le contrôle avant publication. Avant acquittement, un rejeu REST
republie le message initial exact, dates comprises. Après acquittement, il retourne
la même acceptation sans publication. Un échec MQTT retourne 503 ; la commande reste
persistée pour une tentative explicite, sans prolongation de l’expiration.

## Arrosage : proposition, confirmation et suivi

- `POST /api/v1/plants/{plant_id}/arrosage-proposals` : corps `{}` ou avec
  `proposal_id`. Retour 201 avec `simulation`, `current_state`, `plant_id`,
  `watering_duration_s`, `moist_before_pct`, `moist_after_pct`, `duration_limited`,
  `reason` et `expires_at`. Aucun effet ni publication MQTT.
- `POST /api/v1/plants/{plant_id}/arrosage-commands` : `proposal_id` obligatoire,
  `command_id` optionnel. Confirmation explicite ; retour 202 avec le suivi.
- `GET /api/v1/arrosage-commands/{command_id}` : `status`, `reason`,
  `resulting_state`, `measurement_pending`, session, bac, proposition et expiration.

La confirmation revalide session, version, fraîcheur d’émission inférieure à dix
secondes, synchronisation du bac et seuil bas. Une présence sans changement de
version ne périme pas la proposition. La proposition expire après 60 secondes et
n’est consommable qu’une fois. Durée :
`min(watering_max_duration_s, (moist_target_pct - soil_moisture_pct) / watering_gain_pct_per_s)`.
Le plafond est de dix secondes virtuelles ; la proposition indique si la cible ne
sera pas atteinte. Le repos initial est de 60 secondes réelles par bac.

Commande MQTT : `greenmind/v3/plants/{plant_id}/commands`.
Champs : `schema_version`, `command_id`, `simulation`, `plant_id`, `arroseur_id`,
`watering_duration_s`, `expected_state`, `requested_at`, `expires_at`.
Le bac, le topic et l’arroseur doivent correspondre à la configuration.

Acquittement MQTT : `greenmind/v3/plants/{plant_id}/events`.
Champs : `schema_version`, `event_id`, `command_id`, `simulation`, `plant_id`,
`arroseur_id`, `status` (`appliqué` ou `refusé`), `resulting_state`, `simulated_at`,
`emitted_at`, `moist_after_pct`, `watering_applied_duration_s`, `reason`.
Un refus indique une durée appliquée nulle. Le simulateur vérifie aussi le repos,
la durée déterministe, la version et l’expiration avant d’appliquer un gain unique
au bac ciblé. L’horloge météo reste inchangée. Contrôles et arrosages sont sérialisés.

Cycle du suivi : `en_attente → envoyé → exécuté / refusé / TIMED_OUT`.
L’intention est persistée avant envoi. Après dix secondes sans résultat, le suivi
déclare l’exécution incertaine ; le timeout est évalué lors du suivi et des demandes.
Aucun rejeu REST d’une confirmation ni redémarrage API ne republie l’arrosage.
Un échec de publication retourne 503 avec `command_id` et conserve l’incertitude.
Les mutations restent bloquées jusqu’au résultat tardif ou à une nouvelle session
contrôlée. Après un ACK appliqué, `measurement_pending` reste vrai jusqu’à
l’ingestion de la mesure correspondante. Une seule commande peut être en cours.

## Alertes et journal

Une alerte s’ouvre sous `moist_low_pct` et se clôture strictement au-dessus de
`moist_rearm_pct`. Son statut est `ouverte` ou `clôturée`.
`moist_trigger_pct` et `moist_resolved_pct` décrivent les valeurs aux transitions.
La mesure et sa transition d’alerte sont atomiques. Le résultat d’arrosage et la
transition du suivi/journal sont également atomiques.

`GET /api/v1/events` renvoie au plus 100 événements, triés par `sequence`
décroissante, avec filtre `plant_id`. Champs : `event_id`, `simulation`, `plant_id`,
`created_at`, `simulated_at`, `event_type`, `summary`, `details`.
Les libellés de `event_type` sont ceux du dictionnaire validé, notamment
`alerte_ouverte`, `contrôle_appliqué`, `arrosage_exécuté`, `arrosage_TIMED_OUT`
et `arrosage_sans_précommande`. `payload` conserve un message JSON complet en base.
`consumed_by_command` relie la proposition à sa commande ; `late_ack` indique un
résultat tardif.

## API de consultation et santé

`GET /api/v1/health` : `status` (`ok` / `dégradé`), `simulation`,
`database_connected`, `mqtt_connected`, `simulation_mode`.
`GET /plants`, `/plants/{plant_id}`, `/plants/{plant_id}/measurements`,
`/simulation` et les routes de suivi sont sous le même préfixe `/api/v1`.
Erreurs : 403 mode simulation désactivé, 404 cible inconnue, 409 conflit/expiration/repos, 422 contenu invalide,
503 dépendance indisponible. Les messages explicatifs sont en français.

`GET /plants` expose aussi `moist_low_pct`, `moist_rearm_pct`, `moist_high_pct`,
`moist_target_pct` et `arroseur_active` (null sans mesure). Les seuils proviennent
du profil ; l’état d’arroseur provient de la dernière mesure. Les arrosages étant
appliqués instantanément par le simulateur, le suivi de commande reste la preuve
d’exécution et l’état « au repos » n’implique pas une absence d’arrosage passé.

`GET /simulation` expose `simulation_mode`, `presence`, l’horloge et les champs
`air_temperature_c`, `air_humidity_pct`, `observed_at`, `provenance`. Horloge et
météo proviennent de la même dernière mesure du basilic, bac de référence pour
l’ambiance commune. Sans mesure de référence, les champs météo sont null et
`presence` est faux. La présence exige une émission âgée de moins de dix secondes
réelles et non située dans le futur ; la pause ne change pas ce délai.

`GREENMIND_SIMULATION_MODE=1` active les contrôles ; la valeur par défaut est `0`.
Le lanceur `scripts/demo.py start|reset` active explicitement le mode pour la démo.
La configuration est figée à la création de l’application. Toute autre valeur
est refusée ; un mode actif avec `GREENMIND_API_HOST` hors loopback est refusé.
`POST /simulation/controls` retourne 403 en mode désactivé, avant accès SQL,
allocation d’identifiant ou publication MQTT, y compris pour un rejeu. Les routes
de consultation et de suivi restent disponibles. Ce mode concerne les contrôles
de simulation, et ne constitue pas une authentification applicative.

La route `GET /api/v1/plants/{plant_id}/measurements` accepte `limit` (24 par
défaut, 1 000 maximum) et `include_presence` (vrai par défaut). Avec
`include_presence=false`, les signaux de présence sont exclus **avant** la limite ;
les étapes horaires, mesures initiales et interventions restent disponibles pendant
une longue pause. Les valeurs numériques de l’API conservent leur précision.

## SQLite et reconstruction

Les anciens champs/valeurs ne sont pas migrés implicitement. Arrêter les services,
puis exécuter `PYTHONPATH=src .venv/bin/python scripts/reset_database.py` pour
reconstruire la base au schéma 3, sans sauvegarde de l’historique, conformément au
choix validé. Pour une autre base, ajouter `--database CHEMIN`.
Le stockage des compteurs est conservé. L’API et l’ingestion utilisent le même
`GREENMIND_DATABASE_PATH`, par défaut `outputs/greenmind.sqlite`.


## Assistant local en lecture seule

`POST /api/v1/assistant/ask` reçoit `plant_id` et `question` (1 à 1000 caractères).
La réponse sépare `facts` (instantané serveur), `explanation`, `sources` et
`action_executed`, toujours faux. Les valeurs de `status` sont `répondu`,
`sources_insuffisantes`, `indisponible`, `occupé` et `action_non_exécutée`.
Une dégradation du seul service IA conserve les faits et retourne HTTP 200 avec
son statut métier explicite ; une panne SQL retourne 503. La plante inconnue
retourne 404 et le contenu invalide 422.

Une seule génération est active, avec délai global de 40 secondes. Les sources,
extraits et faits numériques proviennent du serveur ; aucun appel de commande
n’est exposé au modèle. Schémas, contraintes, préparation et mesures de latence :
[Assistant_local.md](Assistant_local.md).


### Cycles répétés et disponibilité de l’assistant

`cycle` accompagne les télémétries et événements MQTT, ainsi que les réponses
`GET /simulation` et les mesures REST. Le profil météo et ses dates sont fixes ;
aucune progression du calendrier ni règle été/hiver entre les cycles. Le passage
au cycle suivant produit une télémétrie d’origine `jour_suivant`, consultable dans
l’historique filtré sans signaux de présence. Révision et identifiants restent
monotones ; expiration, conflit et idempotence des contrôles restent applicables.
La migration SQLite ajoute uniquement `sensor_readings.cycle INTEGER NOT NULL
DEFAULT 1` à un schéma v3 compatible. Les lignes anciennes sont conservées au
cycle 1 ; un autre schéma incompatible reste refusé. Les services doivent charger
la même version du code.

`GET /api/v1/assistant/health` répond avec `available`, `status` et `reason`.
Un HTTP 200 signifie que le contrôle a répondu ; seul `available=true` annonce
la disponibilité vérifiée. Le contrôle ne génère aucun texte et ne publie aucune
commande. Ollama et le modèle sont interrogés avec un délai court ; la recherche
locale est préparée en arrière-plan, contrôlée à nouveau après trente secondes.
Une erreur de santé IA ne bloque pas la supervision IoT. Un contrôle réussi ne
garantit pas qu’une future génération réussira : les erreurs de demande restent
prises en charge par `/assistant/ask`.
