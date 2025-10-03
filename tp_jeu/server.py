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
            "iot/config",
            "iot/debat/arguments"
        ]
        
        # Topics des rôles
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
            print(f"[SERVEUR] Erreur lors du traitement du message : {e}")

    def traiter_presence(self, capteur_id, payload):
        """
        Traite un message de présence d'un capteur.
        Démarre la partie lorsque tous les capteurs sont connectés.
        """
        if capteur_id not in self.capteurs_ids:
            return

        if capteur_id in self.capteurs_connectes:
            return  # Capteur déjà enregistré

        self.capteurs_connectes.add(capteur_id)
        capteur_ip = self.capteurs_ips[capteur_id]
        print(f"[SERVEUR] {capteur_id} ({capteur_ip}) connecté "
              f"[{len(self.capteurs_connectes)}/{len(self.capteurs_ids)}]")

        # Démarrage de la partie si tous les capteurs sont connectés
        if len(self.capteurs_connectes) == len(self.capteurs_ids) and not self.partie_en_cours:
            print(f"[SERVEUR] Tous les capteurs sont connectés, démarrage dans 3 secondes...\n")
            time.sleep(3)
            self.demarrer_jeu()

    def traiter_vote(self, capteur_id, payload):
        """
        Traite un vote reçu d'un capteur.
        Détermine le gagnant lorsque tous les votes sont reçus.
        """
        if capteur_id not in self.capteurs_ids:
            return

        if capteur_id in self.votes:
            return  # Vote déjà enregistré

        try:
            vote_data = json.loads(payload.decode())
            suspect_id = vote_data.get("suspect")

            if not suspect_id or suspect_id not in self.capteurs_ids:
                print(f"[SERVEUR] Vote invalide de {capteur_id} : suspect={suspect_id}")
                return

            capteur_ip = self.capteurs_ips.get(capteur_id, "IP inconnue")
            suspect_ip = self.capteurs_ips.get(suspect_id, "IP inconnue")

            print(f"[SERVEUR] Vote reçu de {capteur_id} ({capteur_ip}) : accuse {suspect_id} ({suspect_ip})")
            
            self.votes[capteur_id] = suspect_id
            self.nb_votes_recus += 1

            # Analyse des résultats lorsque tous les votes sont reçus
            if self.nb_votes_recus >= len(self.capteurs_ids):
                self.determiner_gagnant()

        except Exception as e:
            print(f"[SERVEUR] Erreur lors du traitement du vote de {capteur_id} : {e}")

    def demarrer_jeu(self):
        """
        Initialise une nouvelle partie du jeu :
        - Sélectionne un espion aléatoirement
        - Envoie la configuration aux capteurs
        - Attribue les rôles
        """
        self.partie_en_cours = True
        
        print("\n" + "="*70)
        print("[SERVEUR] DÉMARRAGE D'UNE NOUVELLE PARTIE")
        print("="*70)

        # Sélection aléatoire de l'espion
        self.espion_id = random.choice(self.capteurs_ids)
        espion_ip = self.capteurs_ips[self.espion_id]
        print(f"[SERVEUR] Espion désigné secrètement : {self.espion_id} ({espion_ip})")

        # Envoi de la configuration du jeu à tous les capteurs
        config_jeu = {
            "capteurs": self.capteurs_ids,
            "villes_coords": self.villes_coords,
            "capteurs_ips": self.capteurs_ips,
            "timestamp": time.time()
        }
        self.client.publish("iot/config", json.dumps(config_jeu), qos=1, retain=False)
        print(f"[SERVEUR] Configuration du jeu envoyée")

        # Pause pour s'assurer que la configuration est reçue
        time.sleep(2)

        # Attribution des rôles individuels
        print("\n[SERVEUR] Attribution des rôles :")
        for capteur_id in self.capteurs_ids:
            role = "espion" if capteur_id == self.espion_id else "normal"
            coords = self.villes_coords[capteur_id]
            ip = self.capteurs_ips[capteur_id]

            message = json.dumps({
                "role": role,
                "latitude": coords[0],
                "longitude": coords[1],
                "timestamp": time.time()
            })

            topic = f"iot/role/{capteur_id}"
            self.client.publish(topic, message, qos=1, retain=False)

            role_display = "ESPION" if role == "espion" else "Normal"
            print(f"  {capteur_id} ({ip:15s}) -> Rôle: {role_display}, Coordonnées: {coords}")
            time.sleep(0.3)

        print("\n[SERVEUR] Phase de publication des températures en cours...")
        print("[SERVEUR] Attente des votes (après 5 publications)...\n")

    def determiner_gagnant(self):
        """
        Analyse les votes et détermine le gagnant de la partie.
        Affiche les résultats détaillés.
        """
        print("\n" + "="*70)
        print("[SERVEUR] ANALYSE DES RÉSULTATS")
        print("="*70)

        # Comptage des votes pour chaque suspect
        comptage = {}
        for capteur_id, suspect_id in self.votes.items():
            comptage[suspect_id] = comptage.get(suspect_id, 0) + 1

        # Affichage de la répartition des votes
        print(f"[SERVEUR] Répartition des votes :")
        for suspect_id, nb_votes in sorted(comptage.items(), key=lambda x: x[1], reverse=True):
            suspect_ip = self.capteurs_ips.get(suspect_id, "IP inconnue")
            marqueur = " <-- ESPION RÉEL" if suspect_id == self.espion_id else ""
            print(f"           {suspect_id} ({suspect_ip:15s}): {nb_votes} vote(s){marqueur}")

        # Identification du suspect le plus accusé
        suspect_designe = max(comptage, key=comptage.get)
        suspect_ip = self.capteurs_ips[suspect_designe]
        espion_ip = self.capteurs_ips[self.espion_id]

        print(f"\n[SERVEUR] Suspect désigné par la majorité : {suspect_designe} ({suspect_ip})")
        print(f"[SERVEUR] Espion réel : {self.espion_id} ({espion_ip})")

        # Détermination du vainqueur
        print("\n" + "="*70)
        if suspect_designe == self.espion_id:
            print("[SERVEUR] ✓ VICTOIRE DES CAPTEURS !")
            print("[SERVEUR] L'espion a été correctement identifié.")
        else:
            print("[SERVEUR] ✗ VICTOIRE DE L'ESPION !")
            print("[SERVEUR] Les capteurs ont accusé le mauvais suspect.")
        print("="*70 + "\n")

        # Réinitialisation pour une nouvelle partie
        self.reinitialiser_partie()

    def reinitialiser_partie(self):
        """
        Réinitialise l'état du serveur pour permettre une nouvelle partie.
        """
        self.votes = {}
        self.nb_votes_recus = 0
        self.espion_id = None
        self.capteurs_connectes = set()
        self.partie_en_cours = False
        
        print("[SERVEUR] Système réinitialisé, en attente de nouveaux capteurs...\n")

    def executer(self):
        """Lance le serveur arbitre"""
        print("="*70)
        print(f"[SERVEUR] Démarrage du serveur arbitre sur {self.broker_address}")
        print("="*70)
        
        try:
            self.client.connect(self.broker_address, self.broker_port, 60)
            self.client.loop_forever()
        except KeyboardInterrupt:
            print("\n[SERVEUR] Arrêt du serveur arbitre")
            self.client.disconnect()
        except Exception as e:
            print(f"[SERVEUR] Erreur fatale : {e}")
            self.client.disconnect()


if __name__ == "__main__":
    serveur = ServeurArbitre(broker_address="10.109.150.133")
    serveur.executer()
