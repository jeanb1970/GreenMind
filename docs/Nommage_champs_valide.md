# Nommage et formats validés — GreenMind

Ce document consigne les décisions prises avec Jean le 28 octobre 2026.
Il constitue le dictionnaire de référence du schéma 3. Les mêmes concepts conservent les mêmes noms dans la
configuration, les échanges MQTT, l’API, la base, les interfaces et les tests.

## Simulation et identités

| Champ actuel | Champ retenu | Contenu retenu |
|---|---|---|
| `run_id` | `simulation` | `Simu_001 du 28 Oct. 2026 à 14:30` |
| `plant_id` | `plant_id` | `basilic`, `thym`, `romarin` |
| `bed_id` | `bed_id` | `bac_basilic`, `bac_thym`, `bac_romarin` |
| `actuator_id` | `arroseur_id` | `arroseur_basilic`, `arroseur_thym`, `arroseur_romarin` |
| `display_name` | `display_name` | `Basilic`, `Thym`, `Romarin` |
| `scenario` | `scenario` | `journee_serre` |
| `schema_version` | `schema_version` | Entier de version du contrat |

Le compteur de simulation est automatique et persistant entre les redémarrages,
avec au moins trois chiffres ; après 999, il passe à 1000. La date correspond au
démarrage réel en heure belge, sans secondes. L’identifiant reste fixe pendant
toute la simulation.

## Identifiants d’échanges et d’alertes

| Champ conservé | Exemple de valeur |
|---|---|
| `event_id` | `Evenement_000001` |
| `control_id` | `Controle_000001` |
| `command_id` | `Arrosage_000001` |
| `proposal_id` | `Proposition_000001` |
| `alert_id` | `Alerte_000001` |

Chaque catégorie a son propre compteur automatique persistant, sans remise à zéro
entre simulations. Une retransmission conserve le même identifiant ; seule une
nouvelle demande ou un nouvel événement incrémente le compteur. L’allocation devra
préserver l’unicité et l’idempotence, y compris en cas de concurrence.

Les noms `opening_event_id` et `closing_event_id` sont conservés ; ils contiennent
un identifiant d’événement du format retenu, ou `null` pour une clôture absente.

## Dates et heures

Tous les noms de champs temporels sont conservés. Les contenus utilisent l’heure
belge, selon `Europe/Brussels`, avec prise en compte de l’heure d’été/hiver.

| Champs | Format |
|---|---|
| `observed_at`, `simulated_at` | `2026-07-10 12:15:10` |
| `emitted_at`, `received_at` | `2026-07-10 12:15:10.12345` |
| `requested_at`, `expires_at` | `2026-07-10 12:15:10.12345` |
| `opened_at`, `closed_at` | `2026-07-10 12:15:10.12345` |
| `first_received_at`, `created_at`, `executed_at` | `2026-07-10 12:15:10.12345` |

Les instants précis ont exactement cinq chiffres après le point. Les valeurs
optionnelles restent `null` lorsqu’aucun instant ne leur correspond.

## Horloge, état et mesures

| Champ actuel | Champ retenu | Contenu |
|---|---|---|
| `simulated_tick` | `heure_virtuelle` | Entier de 0 à 24 : heures virtuelles écoulées |
| `state_revision` | `current_state` | Compteur entier de version de l’état |
| `expected_revision` | `expected_state` | Version attendue par une commande |
| `resulting_revision` | `resulting_state` | Version après traitement |
| `paused` | `paused` | Booléen |
| `completed` | `day_complete` | Booléen |
| `presence` | `presence` | Booléen |
| `air_temperature_c` | `air_temperature_c` | Nombre, °C |
| `air_humidity_pct` | `air_humidity_pct` | Nombre, de 0 à 100 |
| `soil_moisture_sim_pct` | `soil_moisture_pct` | Nombre, de 0 à 100 |
| `pump_active` | `arroseur_active` | Booléen |

`current_state`, `expected_state` et `resulting_state` désignent des versions
numériques, et non un objet contenant l’ensemble de l’état de la serre.

### Provenance

Champ `provenance` conservé :

| Valeur actuelle | Valeur retenue |
|---|---|
| `synthetic_weather_plus_synthetic_soil` | `meteo_simulee` |
| `historical_weather_plus_synthetic_soil` | `meteo_historique` |

Champ `measurement_origin` conservé :

| Valeur actuelle | Valeur retenue |
|---|---|
| `initial` | `initial` |
| `model` | `calcul_horaire` |
| `manual_override` | `modification_manuelle` |
| `watering` | `arrosage` |
| `heartbeat` | `signal_presence` |

## Commandes et statuts

Champ `action` conservé :

| Valeur actuelle | Valeur retenue |
|---|---|
| `PAUSE` | `pause` |
| `RESUME` | `reprendre` |
| `ADVANCE` | `avancer_1_heure` |
| `SET_SOIL_MOISTURE` | `modifier_humidite_sol` |

`value` devient `moist_request_pct` : nombre de 0 à 100, renseigné uniquement
pour une modification manuelle de l’humidité.

Champ `status` conservé, selon le contexte :

| Contexte | Valeur actuelle | Valeur retenue |
|---|---|---|
| Simulation | `PENDING` | `en_attente` |
| Simulation | `STATE` | `etat_actuel` |
| Simulation ou acquittement MQTT | `APPLIED` | `appliqué` |
| Simulation ou arrosage | `REJECTED` | `refusé` |
| Suivi arrosage | `PENDING` | `en_attente` |
| Suivi arrosage | `SENT` | `envoyé` |
| Suivi arrosage | `EXECUTED` | `exécuté` |
| Suivi arrosage | `TIMED_OUT` | `TIMED_OUT` |
| Alerte | `OPEN` | `ouverte` |
| Alerte | `CLOSED` | `clôturée` |
| Santé | `ok` | `ok` |
| Santé | `degraded` | `dégradé` |

Un timeout indique une exécution non confirmée, et non une preuve d’absence
d’effet. La distinction entre acquittement métier et confirmation de transport
reste inchangée.

## Arrosage et alertes

| Champ actuel | Champ retenu |
|---|---|
| `duration_sim_s` | `watering_duration_s` |
| `duration_applied_sim_s` | `watering_applied_duration_s` |
| `measurement_pending` | `measurement_pending` |
| `soil_moisture_before_pct` | `moist_before_pct` |
| `soil_moisture_after_pct` | `moist_after_pct` |
| `capped` | `duration_limited` |
| `reason` | `reason` |
| `trigger_moisture_pct` | `moist_trigger_pct` |
| `resolved_moisture_pct` | `moist_resolved_pct` |
| `has_active_alert` | `has_active_alert` |
| `active_alert` | `active_alert` |
| `consumed_by` | `consumed_by_command` |
| `late_ack` | `late_ack` |

Les durées d’arrosage restent en secondes virtuelles. `measurement_pending`,
`duration_limited`, `has_active_alert` et `late_ack` restent des booléens.
`active_alert` reste un objet JSON ou `null`. `reason` reste un texte français.

## Paramètres des profils

| Champ actuel | Champ retenu |
|---|---|
| `low_threshold_sim_pct` | `moist_low_pct` |
| `rearm_threshold_sim_pct` | `moist_rearm_pct` |
| `high_threshold_sim_pct` | `moist_high_pct` |
| `target_soil_moisture_sim_pct` | `moist_target_pct` |
| `irrigation_gain_per_sim_s` | `watering_gain_pct_per_s` |
| `max_watering_duration_sim_s` | `watering_max_duration_s` |
| `watering_cooldown_real_s` | `watering_rest_s` |
| `initial_soil_moisture_sim_pct` | `moist_initial_pct` |
| `base_evaporation_per_hour` | `evaporation_pct_per_hour` |
| `reference_temperature_c` | `reference_temperature_c` |
| `temperature_factor_per_c` | `temperature_factor_per_c` |

Le gain et l’évaporation sont exprimés en points de pourcentage par unité de temps.
Le repos reste en secondes réelles, indépendantes de l’horloge de simulation.

## Journal

Les noms `sequence`, `event_type` et `summary` sont conservés.
`details_json` en base devient `details`, comme dans l’API. `payload` est conservé.
Les descriptions et messages restent en français.

| Type actuel | Type retenu |
|---|---|
| `ALERT_OPENED` | `alerte_ouverte` |
| `ALERT_CLOSED` | `alerte_clôturée` |
| `MANUAL_OVERRIDE` | `modification_manuelle` |
| `CONTROL_APPLIED` | `contrôle_appliqué` |
| `CONTROL_REJECTED` | `contrôle_refusé` |
| `WATERING_PROPOSED` | `arrosage_proposé` |
| `WATERING_PENDING` | `arrosage_en_attente` |
| `WATERING_SENT` | `arrosage_envoyé` |
| `WATERING_EXECUTED` | `arrosage_exécuté` |
| `WATERING_REJECTED` | `arrosage_refusé` |
| `WATERING_TIMED_OUT` | `arrosage_TIMED_OUT` |
| `WATERING_PUBLISH_FAILED` | `arrosage_envoi_non_confirmé` |
| `WATERING_UNMATCHED` | `arrosage_sans_précommande` |
| `WATERING_REFUSED` | `demande_arrosage_refusée` |

## Santé et messages API

`database_connected`, `mqtt_connected` et `message` sont conservés.
`demo_mode` devient `simulation_mode`. Les indicateurs restent des booléens ;
`message` reste un texte français.
