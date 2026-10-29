# Cohérence du code et du CDC — 29 octobre 2026

## Organisation et responsabilités

Le CDC décrit le comportement attendu. `docs/contracts.md` décrit les échanges.
Les tests automatisés vérifient les règles et leur raccordement ; ils ne remplacent
pas la recette MQTT/Ollama réelle de B9. Les résultats historiques datés dans le
plan sont conservés comme preuves, pas comme description du dernier code.

| Entité ou responsabilité | Implémentation de référence | Relations et invariants |
|---|---|---|
| Identités des plantes, bacs, arroseurs et profils | `greenhouse_config.py`, `config/greenhouse.yaml` | Trois identités univoques ; le profil détermine les seuils et gains |
| Calculs de dessèchement et arrosage | `domain/simulation.py`, `domain/greenhouse.py`, `domain/arrosage.py` | Calculs purs ; aucune écriture ni réseau |
| Temps, cycle et sol courant | `simulator/engine.py` | Même session entre cycles, sol conservé, météo fixe, révision croissante |
| Règles partagées | `simulation_rules.py` | Actions REST/MQTT communes, 24 h/cycle, présence 10 s, limites distinctes journal/mesures |
| Contrôles et arrosages du moteur | `simulator/controls.py`, `simulator/arrosage.py` | Idempotence, expiration, session et révision ; un seul thread de mutation |
| Contrats MQTT | `schemas.py` | Validation des identités, champs, origines, cycle et dates ; seuls les messages v3 sont admis |
| Transport MQTT | `simulator/mqtt_service.py`, `ingestion/handler.py` | Contrôles non retained ; télémétrie et événements corrélés ; arrêt explicite sur perte de transport |
| Session persistée | `db/models.py`, `db/readings.py` | Une session regroupe mesures et événements ; anciennes mesures conservées ; état courant selon révision |
| Mesure et historique | `TelemetryV3` → `GreenhouseReading` → `MeasurementItem` | Cycle conservé ; heures cumulées = (cycle − 1) × 24 + pas ; jusqu’à 1 000 mesures/bac |
| Alerte et journal | `domain/alerts.py`, `db/readings.py` | Une alerte active par bac/session ; seuil bas et réarmement distincts ; journal limité à 100 événements |
| Proposition, commande et acquittement | `db/arrosage.py`, `api/arrosage.py` | Proposition sans effet, confirmation explicite, intention persistée avant MQTT ; PUBACK ≠ effet exécuté |
| REST supervision et contrôle | `api/routes.py`, `api/schemas.py` | Contrôles de simulation désactivés par défaut ; refus avant écriture métier si mode désactivé |
| Faits et explication IA | `api/assistant.py`, `rag/assistant.py` | Faits SQL séparés du texte ; sources vérifiées ; aucune commande accessible à l’assistant |
| Corpus et index | `rag/corpus.py`, `rag/index.py` | Fiches par plante, empreintes et manifeste ; modèle local ; aucune référence inventée |
| Front | `dashboard/app.py`, `views.py`, `client.py`, `charts.py`, `style.py` | Navigation/fragments, présentation, REST, graphique et apparence séparés ; aucune écriture SQL directe |
| Gestion de la démo | `scripts/demo.py`, `scripts/reset_database.py` | Reset conserve historique/compteurs ; from-scratch les efface après confirmation et arrêt vérifié |

## Refactorisation réalisée

Le point d’entrée Streamlit se limite à la configuration, la navigation et
l’assemblage des fragments. `client.py` contient l’accès REST et la réservation
des identifiants de contrôle ; `views.py` contient les composants de présentation.
Le formulaire assistant reste en dehors du fragment de supervision périodique.
La configuration et les données métier ne sont pas dupliquées dans ces composants.

Le type d’action de simulation est commun aux schémas REST et MQTT. Le moteur,
l’API, le stockage et les courbes importent les règles communes pertinentes.
La séparation préexistante entre domaine, transport, persistance et présentation
est conservée ; une réécriture des calculs validés n’est pas nécessaire pour la
rendre plus claire.

## Incohérences corrigées et limites explicites

La limite de lecture des mesures restait à 100 alors que le front en demandait
1 000 ; la limite du journal avait été portée par erreur à 1 000. Les deux règles
sont maintenant nommées séparément et vérifiées par un test dépassant 100 lignes.

Le CDC doit citer `jour_suivant` dans sa table REST et distinguer `create_all`
de la migration additive explicite de `cycle`. Une base v3 compatible reçoit
cette colonne avec valeur 1 pour les anciennes mesures, sans effacement.
Les reconstructions de base incompatibles restent des opérations explicites.

Le contrôle de santé IA est un constat daté, pas une garantie qu’une génération
future réussira. Les courbes montrent une fenêtre récente bornée, pas tout un
historique illimité. La présence du simulateur dépend d’un signal récent, pas de
la seule existence d’une session SQL. Les nouvelles sessions ne reprennent pas
l’état mémoire d’un processus arrêté ; seul Jour suivant conserve les bacs dans
la même session. B9 et les recettes avec services réels restent distinctes de la
validation automatisée d’une refactorisation.
