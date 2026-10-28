# Données de démonstration GreenMind v1.4

## Journée variable — trois bacs

`fixtures/weather_greenhouse_day.csv` est la fixture du scénario
`journee_serre`, avec les profils de `config/greenhouse.yaml`.
Cette fixture remplace l’ancien scénario constant `demo_dry_basil` de la v1.3.
Le simulateur, les tests et les recettes MQTT utilisent tous cette journée commune.
L’humidité du sol est calculée séparément pour chaque bac à partir des profils
de `config/greenhouse.yaml`, sur une échelle pédagogique de 0 à 100.

- Journée fictive du 10 juillet 2026, de 00:00 à 24:00 en Europe/Brussels.
- 24 lignes, une par intervalle `[h, h+1h[`, dates belges au format `AAAA-MM-JJ HH:MM:SS`.
- Température : 18 °C vers 04–05 h, maximum de 32 °C à 14 h,
  puis 20,5 °C à 23 h.
- Humidité de l'air : 82 % vers 04–05 h, minimum de 40 % à 14 h,
  puis 74 % à 23 h.
- Provenance : `meteo_simulee` ; chiffres créés
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

Le moteur local réalise uniquement les transitions d’état. Le service
`simulator/mqtt_service.py` sérialise ses appels et publie les trois bacs en MQTT v3 ;
`simulator/controls.py` vérifie les sessions, révisions, expirations et doublons.
Un signal_presence est publié toutes les cinq secondes, y compris pendant la pause.
Les arrosages virtuels sont traités par `simulator/arrosage.py` : confirmation
via l’API, gain instantané sur le bac ciblé et acquittement corrélé, sans avancer
l’heure météo. Le repos reste mesuré en secondes réelles.

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

Commandes : `heure`, `etat`, `humidite thym 18`, `lecture`, `quitter`.
Pendant `lecture`, Ctrl+C met en pause ; le prompt revient. Hors lecture,
Ctrl+C termine le contrôle. Aucune donnée n'est envoyée à MQTT ou SQLite.


### Format des dates et provenance

Le CSV utilise l’heure belge `Europe/Brussels` au format `2026-07-10 12:15:10`,
sans suffixe de fuseau dans le texte. Le lecteur convertit les dates en instants
UTC pour les calculs internes. La provenance est `meteo_simulee` ;
`meteo_historique` désigne une météo historique avec sol toujours simulé.
Les instants précis des échanges et de la base ont cinq décimales après les
secondes : `2026-07-10 12:15:10.12345`. Une heure locale ambiguë ou inexistante
au changement d’heure est refusée plutôt que convertie arbitrairement.
