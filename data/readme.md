# Données de démonstration GreenMind

## Origine

Le fichier `fixtures/weather_sample.csv` contient 24 lignes de
météo entièrement synthétique, créées pour le scénario
`demo_dry_basil`.

Ces données ne proviennent ni de capteurs physiques, ni
d’Open-Meteo, ni d’observations météorologiques réelles.
Aucune source externe n’a été utilisée pour les produire.

## Contenu

- Période fictive : 10 juillet 2026, de 00 h à 23 h UTC.
- Intervalle entre deux lignes : une heure.
- Température de l’air constante : 25 °C.
- Humidité relative de l’air constante : 50 %.
- Provenance : `synthetic_weather_plus_synthetic_soil`.

Ces conditions constantes permettent de vérifier simplement
la reproductibilité du calcul de dessèchement.

## Horloges

`observed_at` représente l’heure dans le scénario synthétique.
Ce champ ne représente pas l’heure réelle d’exécution.

Lors de la publication MQTT :
- `emitted_at` indiquera l’heure UTC réelle d’émission ;
- `simulated_tick` indiquera le numéro du pas de simulation.

La cadence réelle de publication est distincte de l’intervalle
horaire représenté par les données météo.

## Humidité du substrat

Le CSV ne contient pas l’humidité du substrat.
Celle-ci sera calculée par le simulateur à partir de la météo
et des paramètres définis dans `config/plants.yaml`.

Elle est exprimée sur une échelle interne de 0 à 100,
sans équivalence établie avec une mesure physique réelle.

## Limites et utilisation

Ces données servent uniquement aux tests et à la démonstration
pédagogique. Elles ne permettent pas de formuler des prescriptions
agronomiques ni de piloter une pompe physique.

Le fichier CSV est conservé dans Git pour rendre les essais
reproductibles. Aucun téléchargement météo n’est nécessaire
pendant l’exécution.