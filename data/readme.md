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

## Journée variable v1.4 — B2

`fixtures/weather_greenhouse_day.csv` est la fixture du scénario
`demo_greenhouse_day`, avec les profils de `config/greenhouse.yaml`.
La fixture constante `weather_sample.csv` reste utilisée par le pipeline
basilic v1 jusqu'à sa migration en B3.

- Journée fictive du 10 juillet 2026, de 00:00 à 24:00 en Europe/Brussels.
- 24 lignes, une par intervalle `[h, h+1h[`, dates explicites `+02:00`.
- Température : 18 °C vers 04–05 h, maximum de 32 °C à 14 h,
  puis 20,5 °C à 23 h.
- Humidité de l'air : 82 % vers 04–05 h, minimum de 40 % à 14 h,
  puis 74 % à 23 h.
- Provenance : `synthetic_weather_plus_synthetic_soil` ; chiffres créés
  pour le scénario pédagogique, sans source externe ni calibration réelle.

La météo représente une ambiance de serre synthétique commune aux trois bacs.
Il n'y a ni pluie appliquée aux bacs ni modèle thermique de serre. L'expression
« journée typique » désigne une allure illustrative, pas une moyenne climatique.
Le lecteur normalise les dates en UTC ; l'affichage les restitue en heure belge.
Les jours de changement d'heure ne sont pas acceptés pour ce scénario de 24 pas.

### Moteur et conventions vérifiées

`simulator/engine.py` démarre en pause à minuit, pas 0, sans dessèchement.
Le premier pas applique la météo 00:00–01:00 et produit l'état de 01:00.
Au pas 24, l'heure est minuit le lendemain et le moteur repasse en pause,
sans revenir automatiquement au début. La météo attachée à un état est celle
du dernier intervalle appliqué (celle du premier intervalle au pas 0).

En lecture, une horloge monotone déclenche un pas toutes les cinq secondes
réelles. Un appel retardé applique au plus un pas puis attend de nouveau cinq
secondes : aucune ligne météo sautée, aucune rafale de rattrapage. Les valeurs
finales sont identiques à celles de 24 avances manuelles. Pause et reprise
annulent l'attente partielle : après reprise, le délai est de cinq secondes.

Une injection en pause remplace uniquement l'humidité courante du bac choisi.
L'heure et le pas restent inchangés ; la révision augmente. Chaque transition
conserve des instantanés avant/après immuables ; le prochain calcul repart de la
valeur imposée. Les snapshots ne permettent pas de modifier le moteur de l'extérieur.
Pause/reprise incrémentent aussi la révision lors d'un changement effectif.

Ce moteur local ne réalise pas encore le dédoublonnage des contrôles MQTT,
les publications de présence, la validation d'une révision distante ni les
verrous liés à l'arrosage. Ces responsabilités seront raccordées en B3/B5/B6.
L'appelant devra sérialiser les appels au moteur ; les callbacks MQTT ne doivent
pas le modifier concurremment.

### Contrôle reproductible

```bash
cd /Users/jean/Projects/GreenMind
PYTHONPATH=src .venv/bin/python3 scripts/check_simulation_day.py
```

Sans intervention ni arrosage, les valeurs arrondies de fin de journée sont :
basilic 4,39 %, thym 12,19 %, romarin 11,49 %. À midi, elles valent respectivement
34,06 %, 27,03 % et 30,04 %. Ce sont des résultats du modèle pédagogique.

Pour piloter localement au clavier :

```bash
PYTHONPATH=src .venv/bin/python3 scripts/check_simulation_day.py --interactive
```

Commandes : `heure`, `etat`, `humidite thym_01 18`, `lecture`, `quitter`.
Pendant `lecture`, Ctrl+C met en pause ; le prompt revient. Hors lecture,
Ctrl+C termine le contrôle. Aucune donnée n'est envoyée à MQTT ou SQLite.
