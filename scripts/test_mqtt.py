import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
PORT = 1883
TOPIC = "greenmind/test/python"
MESSAGE = "Bonjour depuis GreenMind Python !"


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"Connexion refusée : {reason_code}")
        client.disconnect()
        return

    print("Connexion MQTT réussie")
    client.subscribe(TOPIC, qos=1)


def on_subscribe(client, userdata, mid, reason_codes, properties):
    print("Abonnement confirmé")
    client.publish(TOPIC, MESSAGE, qos=1, retain=False)


def on_message(client, userdata, msg):
    print(f"Message reçu sur {msg.topic}")
    print(f"Contenu : {msg.payload.decode('utf-8')}")
    client.disconnect()


client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id="greenmind-test-python"
)

client.on_connect = on_connect
client.on_subscribe = on_subscribe
client.on_message = on_message

print("Connexion à Mosquitto...")
client.connect(BROKER, PORT, 60)
client.loop_forever()
