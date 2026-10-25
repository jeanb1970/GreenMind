# Configuration Mosquitto — GreenMind v1.3

Ces fichiers sont des **exemples de configuration** correspondant au cahier des charges ; ils ne constituent pas une application GreenMind. Aucun essai Docker n'a été réalisé dans l'environnement Mac cible.

1. Placer `docker-compose.yml` à la racine du projet et `docker/mosquitto.conf` au chemin attendu.
2. Télécharger et figer une version/digest de l'image Mosquitto 2.x après test sur le Mac.
3. Lancer `docker compose config` puis `docker compose up -d mosquitto`.
4. Tester MQTT via `mosquitto_sub` et `mosquitto_pub` contre `127.0.0.1:1883`.

`allow_anonymous true` n'est admis que pour cette expérimentation **liée au loopback de l'hôte**. Ne pas utiliser telle quelle la configuration pour un broker accessible au LAN ou à Internet.
