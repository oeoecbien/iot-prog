import paho.mqtt.client as mqtt
import time

def nettoyer_broker(broker_address="10.109.150.133"):
    """Nettoie tous les messages retained du broker MQTT"""
    print("[CLEANUP] Nettoyage du broker MQTT...")
    
    client = mqtt.Client("cleanup_client")
    client.connect(broker_address, 1883, 60)
    
    # Nettoyer tous les topics utilisés
    topics_a_nettoyer = [
        "iot/config",
        "iot/role/rpi1",
        "iot/role/rpi2",
        "iot/role/rpi3",
        "iot/role/rpi4",
        "iot/capteurs/rpi1/temperature",
        "iot/capteurs/rpi2/temperature",
        "iot/capteurs/rpi3/temperature",
        "iot/capteurs/rpi4/temperature",
        "iot/votes/rpi1",
        "iot/votes/rpi2",
        "iot/votes/rpi3",
        "iot/votes/rpi4"
    ]
    
    for topic in topics_a_nettoyer:
        client.publish(topic, "", qos=1, retain=True)
        print(f"[CLEANUP] Topic nettoyé : {topic}")
        time.sleep(0.1)
    
    client.disconnect()
    print("[CLEANUP] Nettoyage terminé\n")

if __name__ == "__main__":
    nettoyer_broker()
