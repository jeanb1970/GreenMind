# Contrats techniques GreenMind v1.3

## 1. Télémétrie MQTT

Le simulateur publie les mesures du basilic. Le service
d’ingestion valide chaque message avant son enregistrement
dans SQLite.

### Transport

- Topic : `greenmind/v1/plants/basilic_01/telemetry`
- Qualité de service : QoS 1.
- Message conservé par le broker : non (`retain=False`).
- Format : objet JSON encodé en UTF-8.
- Version du schéma : 1.

QoS 1 peut entraîner une livraison multiple du même événement.
L’ingestion doit dédoublonner les événements grâce à `event_id`.

### Champs obligatoires

| Champ | Type JSON | Contrainte |
|---|---|---|
| `event_id` | chaîne | UUID identifiant un événement |
| `schema_version` | entier | Valeur 1 |
| `plant_id` | chaîne | Valeur `basilic_01` |
| `observed_at` | chaîne | Date ISO 8601 avec fuseau, sérialisée en UTC |
| `emitted_at` | chaîne | Date ISO 8601 avec fuseau, sérialisée en UTC |
| `simulated_tick` | entier | Supérieur ou égal à 1 |
| `air_temperature_c` | nombre | Valeur finie |
| `air_humidity_pct` | nombre | Valeur finie entre 0 et 100 inclus |
| `soil_moisture_sim_pct` | nombre | Valeur finie entre 0 et 100 inclus |
| `pump_active` | booléen | État de la pompe virtuelle |
| `provenance` | chaîne | Une des deux valeurs autorisées ci-dessous |

Provenances autorisées :

- `synthetic_weather_plus_synthetic_soil`
- `historical_weather_plus_synthetic_soil`

La fixture actuelle utilise exclusivement la première valeur.
Les champs supplémentaires sont refusés pour détecter les erreurs
de nommage et les divergences entre composants.

### Horloges et pas de simulation

- `observed_at` provient de la ligne météo consommée.
- `emitted_at` est l’heure UTC réelle de création du message
  pour publication.
- `simulated_tick` compte les pas effectués depuis le démarrage
  du simulateur.

Convention retenue pour le scénario :

- L’état initial correspond au pas 0, avant tout dessèchement.
- La première ligne météo sert à calculer le pas 1.
- La première télémétrie contient le résultat de ce calcul.
- Chaque ligne suivante produit un nouveau pas.
- Un redémarrage du scénario recommence au pas 1 ; le compteur
  n’est donc pas un identifiant unique en base.

Les contrôles de fraîcheur utilisent `emitted_at`, jamais
`observed_at`, puisque la météo est rejouée.

### Identité des événements

Un nouvel événement reçoit un nouvel `event_id`.
Une retransmission du même événement conserve son identifiant.

Le service d’ingestion vérifie que le `plant_id` du message
correspond à celui du topic MQTT.

### Exemple illustratif

Les UUID et horodatages suivants sont des exemples.
L’heure réelle d’émission et l’identifiant seront générés
pendant l’exécution.

```json
{
  "event_id": "3dd6b710-66f2-4243-8a24-725a03a22800",
  "schema_version": 1,
  "plant_id": "basilic_01",
  "observed_at": "2026-07-10T00:00:00Z",
  "emitted_at": "2026-10-25T13:00:00Z",
  "simulated_tick": 1,
  "air_temperature_c": 25.0,
  "air_humidity_pct": 50.0,
  "soil_moisture_sim_pct": 37.5,
  "pump_active": false,
  "provenance": "synthetic_weather_plus_synthetic_soil"
}
```

### Erreurs et langue

Un message invalide est rejeté sans écriture en base.
L’ingestion doit continuer à traiter les messages suivants.

Les messages explicatifs rédigés par GreenMind sont en français,
conformément à ENF-11. Les identifiants techniques restent inchangés.

## 2. Contrats à implémenter aux étapes suivantes

Les contrats des commandes d’arrosage, des acquittements et
des routes REST restent définis par le cahier des charges v1.3.
Ils seront détaillés ici lors de leur implémentation.