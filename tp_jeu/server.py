import paho.mqtt.client as mqtt
import random
import json
import time
import sys

# Forcer l'encodage UTF-8 pour la sortie console
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


class ServeurArbitre:
    """
    Serveur arbitre du jeu distribué de détection d'espion.

    Responsabilités :
    - Gestion de la connexion des capteurs
    - Attribution aléatoire des rôles (normal/espion)
    - Collecte et analyse des votes
    - Détermination du gagnant

    Hébergé sur : 10.109.150.133
    """

    def __init__(self, broker_address="10.109.150.133", broker_port=1883):
        self.broker_address = broker_address
        self.broker_port = broker_port
        self.client = mqtt.Client("ServeurArbitre")

        # Configuration des capteurs participants
        self.capteurs_ids = ["rpi1", "rpi2", "rpi3", "rpi4"]
        self.capteurs_ips = {
            "rpi1": "10.109.150.75",
            "rpi2": "10.109.150.192",
            "rpi3": "10.109.150.1",
            "rpi4": "10.109.150.133"
        }

        # Mapping des capteurs vers leurs coordonnées géographiques (latitude, longitude)
        self.villes_coords = {
            "rpi1": (45.899, 6.129),   # Annecy
            "rpi2": (45.764, 4.836),   # Lyon
            "rpi3": (45.188, 5.724),   # Grenoble
            "rpi4": (46.204, 6.143)    # Genève
        }

        # État de la partie
        self.espion_id = None
        self.votes = {}
        self.nb_votes_recus = 0
        self.capteurs_connectes = set()
        self.partie_en_cours = False

        # Configuration des callbacks MQTT
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        """Callback appelé lors de la connexion au broker MQTT"""
        if rc == 0:
            print(f"[SERVEUR] Connecté au broker MQTT sur {self.broker_address}:{self.broker_port}")

            # Nettoyer tous les anciens messages retained
            self.nettoyer_topics()

            # Souscriptions aux topics nécessaires
            client.subscribe("iot/capteurs/+/presence")
            client.subscribe("iot/votes/#")

            print("[SERVEUR] En attente de la connexion de tous les capteurs...")
            print(f"[SERVEUR] Capteurs attendus : {', '.join(self.capteurs_ids)}")
        else:
            print(f"[SERVEUR] Échec de connexion au broker (code: {rc})")

    def nettoyer_topics(self):
        """
        Nettoie tous les topics retained avant de démarrer une nouvelle partie.
        Évite les conflits avec d'anciennes données.
        """
        topics_a_nettoyer = [
            "iot/config"
        ]

        # Topics des rôles et données
        for capteur_id in self.capteurs_ids:
            topics_a_nettoyer.append(f"iot/role/{capteur_id}")
            topics_a_nettoyer.append(f"iot/capteurs/{capteur_id}/temperature")
            topics_a_nettoyer.append(f"iot/votes/{capteur_id}")

        for topic in topics_a_nettoyer:
            self.client.publish(topic, "", qos=1, retain=True)

        time.sleep(0.5)

    def on_message(self, client, userdata, msg):
        """Callback appelé lors de la réception d'un message MQTT"""
        try:
            # Ignorer les messages vides
            if len(msg.payload) == 0:
                return

            topic_parts = msg.topic.split('/')

            # Traitement des messages de présence
            if topic_parts[1] == "capteurs" and topic_parts[3] == "presence":
                self.traiter_presence(topic_parts[2], msg.payload)

            # Traitement des votes
            elif topic_parts[1] == "votes" and len(topic_parts) == 3:
                self.traiter_vote(topic_parts[2], msg.payload)

        except json.JSONDecodeError as e:
            print(f"[SERVEUR] Erreur de décodage JSON : {e}")
        except Exception as e:
            print(f"[SERVEUR] Erreur traitement message : {e}")

    def traiter_presence(self, capteur_id, payload):
        """Enregistre la connexion d'un capteur"""
        try:
            data = json.loads(payload.decode())
            ip = data.get("ip", "inconnue")

            if capteur_id in self.capteurs_ids and capteur_id not in self.capteurs_connectes:
                self.capteurs_connectes.add(capteur_id)
                print(f"[SERVEUR] Capteur connecté : {capteur_id} (IP: {ip})")
                print(f"[SERVEUR] Capteurs connectés : {len(self.capteurs_connectes)}/{len(self.capteurs_ids)}")

                # Démarrer la partie si tous les capteurs sont connectés
                if len(self.capteurs_connectes) == len(self.capteurs_ids) and not self.partie_en_cours:
                    self.demarrer_partie()

        except Exception as e:
            print(f"[SERVEUR] Erreur traitement présence : {e}")

    def demarrer_partie(self):
        """Démarre une nouvelle partie du jeu"""
        self.partie_en_cours = True
        
        print("\n" + "="*70)
        print("[SERVEUR] DÉMARRAGE DE LA PARTIE")
        print("="*70)

        # Sélectionner un espion aléatoire
        self.espion_id = random.choice(self.capteurs_ids)
        print(f"[SERVEUR] Espion désigné : {self.espion_id}")
        print(f"[SERVEUR] (Cette information est secrète)")

        # Envoyer la configuration à tous les capteurs
        config_message = json.dumps({
            "capteurs": self.capteurs_ids,
            "villes_coords": self.villes_coords,
            "capteurs_ips": self.capteurs_ips
        })
        self.client.publish("iot/config", config_message, qos=1, retain=True)
        print("[SERVEUR] Configuration envoyée")

        # Attendre un peu pour s'assurer que tous les capteurs ont reçu la config
        time.sleep(1)

        # Attribuer les rôles
        for capteur_id in self.capteurs_ids:
            role = "espion" if capteur_id == self.espion_id else "normal"
            role_message = json.dumps({
                "role": role,
                "timestamp": time.time()
            })
            topic = f"iot/role/{capteur_id}"
            self.client.publish(topic, role_message, qos=1, retain=True)

        print("[SERVEUR] Rôles attribués")
        print("[SERVEUR] Phase de publication des températures en cours...")
        print("="*70 + "\n")

    def traiter_vote(self, capteur_id, payload):
        """Enregistre un vote reçu d'un capteur"""
        try:
            data = json.loads(payload.decode())
            suspect = data["suspect"]

            if capteur_id not in self.votes:
                self.votes[capteur_id] = suspect
                self.nb_votes_recus += 1

                print(f"[SERVEUR] Vote reçu de {capteur_id} : {suspect}")
                print(f"[SERVEUR] Votes reçus : {self.nb_votes_recus}/{len(self.capteurs_ids)}")

                # Si tous les votes sont reçus, calculer le résultat
                if self.nb_votes_recus == len(self.capteurs_ids):
                    self.calculer_resultat()

        except Exception as e:
            print(f"[SERVEUR] Erreur traitement vote : {e}")

    def calculer_resultat(self):
        """Analyse les votes et détermine le gagnant"""
        print("\n" + "="*70)
        print("[SERVEUR] RÉSULTATS DE LA PARTIE")
        print("="*70)

        # Compter les votes
        compteur_votes = {}
        for capteur_id, suspect in self.votes.items():
            compteur_votes[suspect] = compteur_votes.get(suspect, 0) + 1

        print("\n[SERVEUR] Décompte des votes :")
        for suspect, nb_votes in sorted(compteur_votes.items(), key=lambda x: x[1], reverse=True):
            marqueur = " <-- ESPION" if suspect == self.espion_id else ""
            print(f"[SERVEUR]   {suspect} : {nb_votes} vote(s){marqueur}")

        # Déterminer le suspect le plus voté
        suspect_designe = max(compteur_votes, key=compteur_votes.get)
        nb_votes_max = compteur_votes[suspect_designe]

        print(f"\n[SERVEUR] Capteur le plus suspecté : {suspect_designe} ({nb_votes_max} votes)")
        print(f"[SERVEUR] Espion réel : {self.espion_id}")

        # Déterminer le gagnant
        if suspect_designe == self.espion_id:
            print("\n[SERVEUR] RÉSULTAT : Les capteurs ont gagné !")
            print("[SERVEUR] L'espion a été correctement identifié.")
        else:
            print("\n[SERVEUR] RÉSULTAT : L'espion a gagné !")
            print("[SERVEUR] Les capteurs n'ont pas réussi à l'identifier.")

        print("="*70)

        # Réinitialiser pour une nouvelle partie
        self.reinitialiser()

    def reinitialiser(self):
        """Réinitialise l'état du serveur pour une nouvelle partie"""
        self.espion_id = None
        self.votes = {}
        self.nb_votes_recus = 0
        self.capteurs_connectes = set()
        self.partie_en_cours = False

        print("\n[SERVEUR] Système réinitialisé")
        print("[SERVEUR] Prêt pour une nouvelle partie\n")

    def executer(self):
        """Lance l'exécution du serveur arbitre"""
        print("[SERVEUR] Démarrage du serveur arbitre")
        print(f"[SERVEUR] Broker MQTT : {self.broker_address}:{self.broker_port}\n")

        try:
            self.client.connect(self.broker_address, self.broker_port, 60)
            self.client.loop_forever()
        except KeyboardInterrupt:
            print("\n[SERVEUR] Arrêt du serveur")
            self.client.disconnect()
        except Exception as e:
            print(f"[SERVEUR] Erreur : {e}")
            self.client.disconnect()


if __name__ == "__main__":
    serveur = ServeurArbitre(broker_address="10.109.150.133")
    serveur.executer()
