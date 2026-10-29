# Configuration Mosquitto — GreenMind

`docker-compose.yml` et `docker/mosquitto.conf` configurent le broker MQTT local lié à `127.0.0.1:1883`.

1. Vérifier la configuration avec `docker compose config`.
2. Démarrer le broker avec `docker compose up -d mosquitto` (également lancé automatiquement par `.venv/bin/python scripts/demo.py start`).
3. Les échanges applicatifs utilisent le schéma MQTT v3 sur les topics `greenmind/v3/...`.

`allow_anonymous true` n'est admis que pour cette exécution locale **liée au loopback de l'hôte**. Ne pas utiliser telle quelle la configuration pour un broker accessible au LAN ou à Internet.
