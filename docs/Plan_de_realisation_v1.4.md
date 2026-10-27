# GreenMind v1.4 — Réalisation par briques

**Date :** 27 octobre 2026.  
**Cible :** [CDC v1.4](Cahier_des_Charges_v1.4_Serre.md).  
**Avancement au 27 octobre :** B0 validée, **B1, B2 et B3 réalisées et testées** ; B4–B9 à réaliser. Les trois bacs sont raccordés à MQTT (schéma v2) et ingérés dans SQLite avec dédoublonnage et contrôles d'état. Les contrôles MQTT et IA externes restent séparés.

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
| B3 — Contrats et pipeline | Trois bacs transitent réellement par MQTT jusqu'à SQLite | `docs/contracts.md`, `schemas.py`, `simulator/main.py`, ingestion, modèles SQL, scripts de contrôle | Schéma v2, identités/session/révisions, sauvegarde/reconstruction base documentée, dédoublonnage avec vrai broker |
| B4 — Alertes, journal et API | État des trois bacs et historique consultables via REST | `domain/alerts.py`, persistance alertes/journal, `api/`, tests d'intégration | Injection puis ouverture/clôture d'alerte atomique, journal borné et filtré par bac, erreurs et rollback vérifiés |
| B5 — Trois arroseurs | Boucle de commande complète sans IA | règles, propositions, MQTT API, commandes simulateur, acquittements SQL | Pour chaque bac : proposition → confirmation → effet unique → ack ; refus et timeout |
| B6 — Deux pages | Tableau de bord et console contrôlent la même application | `dashboard/`, `dashboard/pages/`, routes de contrôle, scripts start/stop/reset | Pause/avance/injection depuis le front, effet via MQTT visible dans le journal ; deux cycles de reset |
| B7 — Corpus Markdown | Trois fiches sourcées et index local traçable | `knowledge/`, préparation/extraction RAG, manifeste, tests | Une fiche par espèce ; chaque citation retrouve sa section et son extrait ; fiche invalide rejetée |
| B8 — Assistant intégré | Explications contextualisées pour chaque bac | `rag/assistant.py`, API assistant, front, tests/questions de recette | Mesures exactes, sources pertinentes, aucune action depuis le LLM, timeout sans blocage IoT |
| B9 — Gel et soutenance | Parcours complet répétable et documenté | README, guide démo, résultats de recette, supports | A14-01 à A14-13, hors ligne, deux répétitions chronométrées, sauvegarde/capture de secours |

B1/B2 utilisent d'abord des tests et contrôles locaux. La bascule publique des messages et de la configuration utilisée par le simulateur se fait de façon cohérente en B3 : ne pas laisser un nouveau YAML casser silencieusement le programme existant. Transition retenue : configuration v1.4 dans `config/greenhouse.yaml`, avec son chargeur, jusqu'à la bascule des consommateurs en B3. Le fichier `config/plants.yaml` et le chargeur v1 restent utilisés par le pipeline actuel ; ils seront retirés après sa migration.

Le contrat des contrôles est défini en B3 ; son application par le simulateur et son suivi API sont terminés en B6. B4 utilise un producteur de test pour vérifier les mesures marquées `manual_override`, sans écrire directement dans les tables. B5 peut être démontrée via l'API avant la construction des fronts.

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
| Base v1 vers v2 | B3 | Sauvegarde puis migration ou reconstruction explicite des données de développement |
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
- Contrats techniques v1.4 formalisés dans `docs/contracts.md` (schéma v2, `greenmind/v2/`).
- Validation stricte Pydantic (`TelemetryV2`, `SimulationControl`, `SimulationEvent`).
- Bascule des trois bacs (`basilic_01`, `thym_01`, `romarin_01`) via Mosquitto QoS 1 vers SQLite (`sensor_readings`, `simulation_runs`, `simulation_events`).
- Commandes de simulation (`PAUSE`, `RESUME`, `ADVANCE`, `SET_SOIL_MOISTURE`), dédoublonnage par `event_id` et `control_id`, protection contre les révisions périmées, battement de cœur (`heartbeat`) en pause et rejet strict des messages non conformes.
- Sauvegarde de l'ancienne base v1 (`outputs/greenmind.v1.sqlite.bak`) et validation de la structure SQLite v2 propre (WAL, timeout 5000 ms, clés étrangères actives).
- Suite de tests : 37 tests de pipeline (`tests/test_pipeline.py`) et suite complète `pytest` réussie (127 tests).
- Preuve réelle sur deux processus et broker validée avec succès via `scripts/check_mqtt_pipeline.py`.

Prochaine brique : B4, alertes, journal et API REST.
