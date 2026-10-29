# Reprise GreenMind — 28 octobre 2026

## État actuel et prochaine étape

Mise à jour du 29 octobre : refactorisation du front en `app.py`, `client.py`
et `views.py`, courbes et styles conservés séparément. Règles transversales dans
`simulation_rules.py`, dont type d’action commun REST/MQTT. Incohérence corrigée :
le journal est plafonné à 100 et les mesures à 1 000 par bac. Test au-delà de
100 lignes ajouté ; suite complète : 281 tests. Matrice des responsabilités et
entités dans `docs/Coherence_code_CDC.md`, CDC et plan actualisés. Les services
n’ont pas été redémarrés : les changements backend prendront effet au prochain
redémarrage contrôlé, sans nécessité de reconstruire la base.


Dernières évolutions livrées : Jour suivant conserve la session et les bacs,
rejoue le même profil météo fixe (aucun calendrier civil/DST), et revient en pause
au pas 0 du cycle suivant. Colonne `cycle` ajoutée automatiquement au schéma v3
compatible, ancienne télémétrie au cycle 1. Courbes cumulées, 1 000 mesures/bac.
Supervision rafraîchie toutes les cinq secondes via fragment, formulaire assistant
préservé. Santé IA vérifiée avant question via `/assistant/health`, affichée toutes
les dix secondes, recherche locale préparée en arrière-plan. `demo.py from-scratch`
efface base ET compteurs après confirmation EFFACER et arrêt contrôlé ; testé
uniquement sur fichiers temporaires. `reset` conserve historique et compteurs.
La démo a été relancée pour charger le moteur après constat de la fin de session.

Projet : `/Users/jean/Projects/GreenMind`, Python 3.12 dans `.venv`.
B1 à B8 sont réalisées. Les corrections du front et les cinq traitements de la
revue (`INC-01-bis`, `INC-02`, `INC-04`, `INC-06`, `INC-16`) sont appliqués.
**Dernière suite complète exécutée : 281 tests réussis.** B9 (recette finale,
gel, répétitions et supports) reste à réaliser. Aucune tâche de correction des
trois courbes ou du logo n’est encore en attente dans cette reprise.

Ne pas refaire les briques déjà livrées. Lire le CDC, les contrats et le plan avant
une modification. Le dépôt comporte des changements indexés et non indexés,
notamment B8, le renommage des modules `watering.py` en `arrosage.py`, les documents
et les corrections visuelles. Les préserver. Consulter `git status --short` et
`git diff` pour l’état réel ; un ancien instantané Git ne fait pas autorité.
Aucun commit ni push n’a été effectué par cette conversation pour ces corrections.

## Corrections de la revue appliquées

- **INC-01-bis** : le bandeau distingue absence de simulation, absence de mesure
  de référence, simulateur sans présence récente, pause connectée, lecture
  connectée et journée terminée. Les actions du front sont désactivées si la
  présence n’est pas confirmée. L’état est réévalué avec **Actualiser**.
- **INC-02** : la météo commune est visible sur Serre (température, humidité de
  l’air, provenance et début de l’intervalle appliqué). Elle provient de la même
  mesure que l’horloge de `/simulation`. Une donnée ancienne est explicitement
  présentée comme dernière météo enregistrée.
- **INC-04** : les cartes montrent seuil bas, réarmement, seuil haut, cible,
  `arroseur_id` et état à la dernière mesure. L’arrosage étant instantané dans le
  modèle, cet état ne remplace pas le suivi de commande et son acquittement.
- **INC-06** : l’API désactive les contrôles de simulation par défaut.
  `GREENMIND_SIMULATION_MODE=1` les active explicitement ; `0` les désactive.
  Les autres valeurs sont refusées au démarrage. Le mode actif exige un hôte API
  loopback. Le lanceur de démo active explicitement le mode ; les recettes de
  contrôles créent explicitement une application de test avec le mode actif.
  Un contrôle en mode désactivé retourne **403 avant accès SQL, allocation de clé
  ou publication MQTT**. Les lectures et suivis restent disponibles.
- **INC-16** : ce fichier décrit l’état courant. Les résultats antérieurs de
  248 tests (B8 initiale) et 250 tests (corrections des courbes) sont historiques ;
  ils ne sont plus présentés comme les derniers résultats.

## Front actuellement livré

- Deux vues : **Serre** et **Console · Mode simulation**, avec titres de navigateur
  correspondants. Apparence **Clair / Sombre**, choisie par l’utilisateur et
  conservée pendant la navigation dans sa session.
- Fond clair et tuiles sauge, ou fond bleu nuit et panneaux clairs. Illustration
  locale et dessins des trois plantes. Deux familles locales maximum : Source
  Sans et Source Code Pro.
- Logo minimaliste fourni par Jean, conservé dans
  `src/greenmind/dashboard/assets/greenmind-logo.png`. Utilisation directe du PNG
  pour le favicon et de `st.logo` pour l’en-tête de la barre latérale (160 px).
  Ne pas réintroduire le SVG imbriquant une image pour le favicon : la présence
  d’un lien ne suffisait pas à prouver son affichage. Le bouton natif de fermeture
  reste visible hors survol, dans les deux thèmes ; fermeture/réouverture vérifiées.
- Libellé **Humidité du sol**, pourcentages à deux décimales avec virgule française.
  Les calculs, la base et les champs numériques REST conservent leur précision.
- Un graphique Altair commun : Basilic bleu, Thym orange, Romarin violet, légende
  visible, axes nommés (heures cumulées entre cycles et humidité 0–100 %), points initiaux
  et infobulles. Les interventions à heure constante suivent `current_state`.
- Le graphique demande `limit=1000&include_presence=false` par bac. Le filtre SQL
  exclut les présences avant la limite ; le comportement REST par défaut conserve
  toutes les origines de mesure. Une longue pause ne masque plus les étapes utiles.

## B8 à préserver

- `rag/assistant.py` filtre la recherche sur la plante et utilise Ollama/Qwen3
  avec sortie JSON structurée, sans outil MQTT ni capacité d’action.
- `api/assistant.py` ferme la transaction de lecture avant toute génération.
  Les faits numériques et les sources sont construits par le serveur.
- `api/app.py` gère un client partagé `httpx2.AsyncClient` via lifespan. Le paquet
  installé est **httpx2**, pas `httpx` ; conserver cet import.
- Une génération à la fois ; délai global de 40 s et requête Streamlit à 45 s.
  Une recherche native tardive garde le slot jusqu’à sa fin.
- Les faits sont séparés de l’explication, avec origine et fraîcheur. Une panne IA
  conserve les faits et la consultation IoT ; statut métier `indisponible` possible
  avec HTTP 200. Question invalide : 422 ; plante inconnue : 404.
- Modèle local testé : `qwen3:4b-instruct`, identifiant `0edcdef34593`, Ollama sur
  `http://127.0.0.1:11434`. Ne pas arrêter le service Ollama de l’utilisateur.
- Dernière recette B8 réelle réussie avant cette revue : réponses sourcées sur les
  trois espèces, aucune mutation métier, panne IA isolée. Latences observées :
  15,79 / 6,59 / 7,25 s ; lectures IoT : 0,010 / 0,012 / 0,011 s. Ces observations
  ne sont pas des garanties. La revue actuelle a réexécuté la suite automatisée,
  sans refaire la génération réelle qui n’a pas été modifiée.

## Nommage et données

Le dictionnaire `docs/Nommage_champs_valide.md` reste la référence. Notamment :

- `simulation` : `Simu_001 du 28 Oct. 2026 à 14:30` ; `plant_id` : `basilic`,
  `thym`, `romarin` ; `bed_id` et `arroseur_id`.
- `heure_virtuelle`, `current_state`, `expected_state`, `resulting_state`,
  `soil_moisture_pct`, `arroseur_active`, `paused`, `day_complete`.
- Identifiants distincts persistants : `Evenement_000001`, `Controle_000001`,
  `Arrosage_000001`, `Proposition_000001`, `Alerte_000001`. Compteurs dans
  `outputs/identifiers.sqlite`, préservés entre sessions et reconstructions ordinaires ; effacés explicitement par `from-scratch`.
- Dates publiques en heure belge `Europe/Brussels`, secondes pour météo/heure
  virtuelle, cinq décimales pour les instants précis. Schéma MQTT 3,
  préfixe `greenmind/v3`, API `/api/v1`.
- Origines : `initial`, `calcul_horaire`, `modification_manuelle`, `arrosage`,
  `signal_presence`, `jour_suivant` ; provenances météo : `meteo_simulee`, `meteo_historique`.

Ne pas reconstruire la base pour une correction d’affichage. `scripts/demo.py
reset` relance une session en conservant l’historique ; `reset_database.py` est une
reconstruction distincte et explicite, sans conservation de la base de serre.

## Exécution et vérifications

```bash
source scripts/runtime_env.sh
.venv/bin/python -m pytest tests -q
```

Les limites de threads doivent être chargées avant les bibliothèques IA natives.
Aucun téléchargement de modèle n’est nécessaire. Ne pas lancer une recette MQTT
avec un second simulateur pendant la démo.

Interface : `http://127.0.0.1:8501/` ; API : `http://127.0.0.1:8000/docs`.
Le registre `outputs/demo/processes.json` permet de retrouver les processus ;
vérifier leurs commandes avant un arrêt. Les services ont été rechargés avec
`demo.py reset` après constat du pas 24 de la session précédente, dont les données
restent en base. Recette réelle : 24 avances REST → MQTT → SQLite, puis clic
Jour suivant dans la console ; les trois humidités finales sont exactement
conservées en J2 et la session reste identique. Lecture réelle bornée sept secondes,
puis pause confirmée : J2 pas 1, 25 h cumulées, révision 28, session
`Simu_007 du 28 Oct. 2026 à 17:17`. Le front a suivi l’heure sans Actualiser.
L’assistant est déclaré disponible par son contrôle local, sans génération.
Preuves dans `outputs/demo/cycle1_end.json`, `cycle2_start.json`,
`lecture_automatique.json` et `cycle2_console.png`. Revérifier l’état réel à la
prochaine reprise. Aucun effacement de base ni de compteurs dans cette recette.

## Références et préférences

Lire `docs/Cahier_des_Charges_v1.4_Serre.md`, `docs/contracts.md`,
`docs/Plan_de_realisation_v1.4.md`, `docs/Corpus_horticole.md`,
`docs/Assistant_local.md` et `README.md` selon la tâche.

Échanger en français, avancer concrètement et demander à Jean en cas de véritable
dilemme. Maintenir la lisibilité et le choix utilisateur Clair/Sombre. Le README
présente le projet final (fin de formation Architecte AIoT chez Technofutur TIC),
sans points d’avancement ; le plan conserve les étapes et preuves. Mettre à jour
la documentation afférente à chaque changement. Si la conversation devient longue,
mettre cette reprise à jour et recommander une nouvelle conversation avec ce fichier
et le CDC. Échéance de soutenance : 5 novembre 2026 ; aucun travail le week-end.
