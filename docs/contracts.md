# Contrats techniques GreenMind v1.4

> Ce document décrit les contrats d'échanges techniques de la version 1.4 de GreenMind. Tous les échanges réseau utilisent `schema_version: 2` et le préfixe de topic `greenmind/v2`. Les contrats v1.3 antérieurs sont obsolètes et ne sont plus acceptés par le système.

## 1. Principes généraux d'échange

1. **Transport MQTT** :
   - Broker local Mosquitto (`127.0.0.1:1883`).
   - Qualité de service : **QoS 1** sur tous les flux.
   - Messages retenus : **interdits** (`retain=False`). Tout message reçu avec le drapeau *retained* est immédiatement rejeté.
   - Sessions non persistantes (`clean_session=True`).
   - Format : objet JSON encodé en UTF-8.
2. **Validation stricte** :
   - Implémentée via Pydantic (`strict=True`, `extra="forbid"`, `frozen=True`, pas de NaN/Inf).
   - Les champs inconnus ou non autorisés entraînent un rejet strict sans écriture en base.
   - Les dates sont sérialisées au format ISO 8601 avec fuseau horaire explicite normalisé en UTC (`Z`).
3. **Identité, sessions et révisions** :
   - Chaque exécution du simulateur génère un identifiant de session unique (`run_id` au format UUID v4).
   - Chaque message porte son propre identifiant d'événement (`event_id` au format UUID v4).
   - L'état de la serre est ordonné par un compteur monotone de révision (`state_revision`). Une révision antérieure reçue en retard ne remplace jamais un état plus récent en base de données SQLite.
   - L'ingestion dédoublonne les messages via la contrainte d'unicité `PRIMARY KEY (event_id)` en base.
4. **Langue des messages** :
   - Tous les messages de motif, statuts textuels et diagnostics fonctionnels sont rédigés en français (ENF-11). Les identifiants techniques restent stables.

---

## 2. Flux de télémétrie des plantes

Le simulateur publie périodiquement l'état de chacun des trois bacs configurés (`basilic_01`, `thym_01`, `romarin_01`).

### Transport

- Topic : `greenmind/v2/plants/{plant_id}/telemetry`
- QoS : 1, `retain=False`
- Fréquence : à chaque pas horaire simulé, lors d'un forçage manuel, après un arrosage, ou toutes les 5 secondes en pause (*heartbeat* de présence).

### Champs obligatoires

| Champ | Type JSON | Contraintes et règles |
|---|---|---|
| `schema_version` | entier | Fixé à `2`. |
| `event_id` | chaîne | UUID v4 unique pour chaque émission de message. |
| `run_id` | chaîne | UUID v4 identifiant la session courante du simulateur. |
| `plant_id` | chaîne | Identifiant du bac : `basilic_01`, `thym_01` ou `romarin_01`. Doit correspondre au token du topic MQTT. |
| `observed_at` | chaîne | Horodatage ISO 8601 UTC de l'intervalle météo consommé. |
| `simulated_at` | chaîne | Heure virtuelle courante de la serre (ISO 8601 UTC). Égale à `observed_at` au pas 0, puis `observed_at + 1 heure` au pas horaire. |
| `emitted_at` | chaîne | Heure réelle UTC de fabrication du message. |
| `simulated_tick` | entier | Entier compris entre `0` (initial) et `24` (fin de journée). |
| `state_revision` | entier | Compteur de révision d'état, supérieur ou égal à `simulated_tick`. |
| `paused` | booléen | Indique si le moteur temporel de simulation est en pause. |
| `completed` | booléen | Vrai uniquement au pas 24 (journée terminée, obligatoirement en pause). |
| `air_temperature_c` | nombre | Température ambiante de l'air en degrés Celsius (valeur finie). |
| `air_humidity_pct` | nombre | Humidité de l'air en pourcentage, valeur finie dans `[0.0, 100.0]`. |
| `soil_moisture_sim_pct` | nombre | Humidité du sol simulée en pourcentage, valeur finie dans `[0.0, 100.0]`. |
| `pump_active` | booléen | État de l'actionneur d'arrosage du bac. |
| `provenance` | chaîne | `synthetic_weather_plus_synthetic_soil` ou `historical_weather_plus_synthetic_soil`. |
| `measurement_origin` | chaîne | Origine de l'état : `initial`, `model`, `manual_override`, `watering`, ou `heartbeat`. |

### Cohérence d'état

- Au démarrage (`measurement_origin == "initial"`), `simulated_tick == 0` et `state_revision == 0`.
- Lorsque `completed == true`, `simulated_tick` doit valoir 24 et `paused` doit être `true`.
- Tout message reçu dont le `plant_id` ne correspond pas exactement au topic MQTT d'émission est rejeté.

### Exemple illustratif de télémétrie

```json
{
  "schema_version": 2,
  "event_id": "7f093206-8d1f-4efc-8b83-b097ef7ff894",
  "run_id": "95914fa0-6893-424f-9e79-cfc0be9ff99a",
  "plant_id": "basilic_01",
  "observed_at": "2026-07-10T00:00:00Z",
  "simulated_at": "2026-07-10T00:00:00Z",
  "emitted_at": "2026-10-27T18:45:00.123456Z",
  "simulated_tick": 0,
  "state_revision": 0,
  "paused": true,
  "completed": false,
  "air_temperature_c": 20.0,
  "air_humidity_pct": 75.0,
  "soil_moisture_sim_pct": 50.0,
  "pump_active": false,
  "provenance": "synthetic_weather_plus_synthetic_soil",
  "measurement_origin": "initial"
}
```

---

## 3. Flux des commandes de simulation

Les contrôles de l'horloge et de la serre sont émis par les services autorisés (scripts de test, API backend ou console) vers le simulateur.

### Transport

- Topic : `greenmind/v2/simulation/controls`
- QoS : 1, `retain=False`

### Champs obligatoires

| Champ | Type JSON | Contraintes et règles |
|---|---|---|
| `schema_version` | entier | Fixé à `2`. |
| `control_id` | chaîne | UUID v4 identifiant la commande (clé d'idempotence). |
| `run_id` | chaîne | UUID v4 de la session visée. Si différent du `run_id` courant du simulateur, la commande est refusée. |
| `expected_revision` | entier | Révision attendue de la serre avant application. Si différente de la révision courante, la commande est rejetée (`REJECTED`) pour prévenir les conflits concurrents. |
| `action` | chaîne | Action demandée : `PAUSE`, `RESUME`, `ADVANCE` ou `SET_SOIL_MOISTURE`. |
| `requested_at` | chaîne | Date réelle de demande (ISO 8601 UTC). |
| `expires_at` | chaîne | Date réelle d'expiration (ISO 8601 UTC). Doit être comprise entre `0` et `60` secondes après `requested_at`. |
| `plant_id` | chaîne \| null | Obligatoire si `action == "SET_SOIL_MOISTURE"`, interdit (`null`) sinon. |
| `value` | nombre \| null | Obligatoire si `action == "SET_SOIL_MOISTURE"` (flottant entre `0.0` et `100.0`), interdit (`null`) sinon. |

### Traitement et idempotence

- Le simulateur traite les commandes sur un seul thread d'exécution.
- Si une commande portant un `control_id` déjà traité est reçue à nouveau (ex. retransmission QoS 1), le simulateur republie le résultat précédent sans réexécuter l'action.
- Si l'heure réelle courante dépasse `expires_at`, la commande est rejetée.
- `ADVANCE` avance la simulation d'exactement une heure (+1 tick) et n'est autorisée qu'en mode pause.
- `SET_SOIL_MOISTURE` modifie immédiatement l'humidité du bac désigné (créant une nouvelle révision d'état avec `measurement_origin: manual_override`), sans affecter les deux autres bacs.

### Exemple illustratif de commande

```json
{
  "schema_version": 2,
  "control_id": "c1f7a42b-5867-4e3e-bf6e-63f52479e083",
  "run_id": "95914fa0-6893-424f-9e79-cfc0be9ff99a",
  "expected_revision": 0,
  "action": "SET_SOIL_MOISTURE",
  "requested_at": "2026-10-27T18:45:10Z",
  "expires_at": "2026-10-27T18:45:40Z",
  "plant_id": "thym_01",
  "value": 18.0
}
```

---

## 4. Flux des événements et acquittements de simulation

À chaque transition ou en réponse à une commande, le simulateur publie un événement corrélé.

### Transport

- Topic : `greenmind/v2/simulation/events`
- QoS : 1, `retain=False`

### Champs obligatoires

| Champ | Type JSON | Contraintes et règles |
|---|---|---|
| `schema_version` | entier | Fixé à `2`. |
| `event_id` | chaîne | UUID v4 propre à l'événement émis. |
| `run_id` | chaîne | UUID v4 de la session courante. |
| `control_id` | chaîne \| null | UUID v4 de la commande ayant produit l'événement, ou `null` pour un événement périodique d'état (*heartbeat* ou transition d'horloge). |
| `status` | chaîne | `STATE` (état courant régulier), `APPLIED` (contrôle exécuté avec succès) ou `REJECTED` (contrôle refusé). |
| `state_revision` | entier | Révision d'état résultante. |
| `simulated_tick` | entier | Pas horaire courant (0 à 24). |
| `simulated_at` | chaîne | Heure virtuelle courante (ISO 8601 UTC). |
| `emitted_at` | chaîne | Heure réelle UTC d'émission. |
| `paused` | booléen | État de pause courant. |
| `completed` | booléen | État de fin de journée courant. |
| `reason` | chaîne | Message explicatif en français décrivant l'état ou le motif d'acceptation/refus. |

### Exemple illustratif d'acquittement

```json
{
  "schema_version": 2,
  "event_id": "58e2e291-0bd3-4194-9dd7-9d45d1582661",
  "run_id": "95914fa0-6893-424f-9e79-cfc0be9ff99a",
  "control_id": "c1f7a42b-5867-4e3e-bf6e-63f52479e083",
  "status": "APPLIED",
  "state_revision": 1,
  "simulated_tick": 0,
  "simulated_at": "2026-07-10T00:00:00Z",
  "emitted_at": "2026-10-27T18:45:10.250000Z",
  "paused": true,
  "completed": false,
  "reason": "Humidité du sol imposée à 18.0 % sur thym_01."
}
```

---

## 5. Contrats cibles des étapes suivantes

### 5.1. Commandes et acquittements d'arrosage (B5)

- Topic de commande : `greenmind/v2/plants/{plant_id}/commands`
  - Clés : `command_id`, `run_id`, `plant_id`, `actuator_id` (concordants avec la configuration de serre), `volume_ml` ou durée virtuelle, `expected_revision`, horodatages d'émission et d'expiration.
- Topic d'acquittement : `greenmind/v2/plants/{plant_id}/events`
  - Clés : `event_id`, `command_id`, `status` (`APPLIED` / `REJECTED`), `volume_dispensed_ml`, `soil_moisture_after_pct`, `resulting_revision`.

### 5.2. Surface d'API REST applicative (B4)

- Préfixe d'accès : `/api/v1` (FastAPI sur `127.0.0.1:8000`).
- Les mutations asynchrones publiées sur MQTT retournent `202 Accepted` avec identifiant de suivi, jamais une garantie immédiate d'effet physique.
- Consultation de l'état : `/api/v1/plants`, `/api/v1/plants/{plant_id}`, `/api/v1/events` (borné côté serveur), `/api/v1/simulation`.
