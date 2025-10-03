# capteur.py (version où l'espion ne vote pas contre lui-même)
import paho.mqtt.client as mqtt
import requests
import time
import json
import random
import sys
import threading
from collections import defaultdict
from statistics import mean, variance

# Forcer l'encodage UTF-8 pour la sortie console
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


class AnalyseurIA:
    """
    Agent d'analyse utilisant Ollama pour détecter l'espion
    en analysant les données de température collectées.
    """

    def __init__(self, ollama_url="http://10.103.1.12:11434"):
        self.ollama_url = ollama_url
        self.modele = "gemma3:4b"
        self.timeout_requete = 45
        
        # Test de connectivité au démarrage
        self.ollama_disponible = self._tester_connexion()

    def _tester_connexion(self):
        """Teste la connectivité au serveur Ollama."""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False

    def _appeler_ollama(self, prompt, timeout=45):
        """Appelle l'API Ollama pour obtenir une réponse."""
        try:
            payload = {
                "model": self.modele,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "top_p": 0.9
                }
            }
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=timeout
            )
            
            if response.status_code == 200:
                return response.json().get("response", "")
            return None
        except:
            return None

    def _construire_contexte_statistique(self, mon_id, mes_temps, autres_temps):
        """Construit un contexte statistique clair pour le LLM."""
        # Calculer la moyenne globale
        toutes_valeurs = list(mes_temps)
        for capteur_id, temps in autres_temps.items():
            if capteur_id != mon_id and temps:
                toutes_valeurs.extend(temps)

        moyenne_globale = mean(toutes_valeurs) if toutes_valeurs else 0

        contexte = f"MOYENNE GLOBALE : {moyenne_globale:.1f}°C\n\n"
        contexte += "DONNÉES PAR CAPTEUR :\n"

        # Analyser tous les capteurs
        tous_capteurs = {mon_id: mes_temps}
        tous_capteurs.update(autres_temps)

        for capteur_id in sorted(tous_capteurs.keys()):
            temps = tous_capteurs[capteur_id]
            if temps and len(temps) > 0:
                moy = mean(temps)
                var = variance(temps) if len(temps) > 1 else 0
                ecart_global = abs(moy - moyenne_globale)
                
                contexte += f"  • {capteur_id} : "
                contexte += f"Moy={moy:.1f}°C, Variance={var:.1f}, Écart={ecart_global:.1f}°C\n"
                contexte += f"    Valeurs : {[round(t, 1) for t in temps]}\n"

        return contexte

    def analyser_espion(self, mon_id, mes_temperatures, temperatures_autres, je_suis_espion=False):
        """
        Analyse toutes les données collectées et désigne l'espion.
        
        Args:
            mon_id: Identifiant du capteur effectuant l'analyse
            mes_temperatures: Liste des températures publiées par ce capteur
            temperatures_autres: Dict {capteur_id: [températures]}
            je_suis_espion: Booléen indiquant si ce capteur est l'espion
        
        Returns:
            dict: {"suspect": "rpiX", "confiance": 0.0-1.0, "justification": "..."}
        """
        # Si ce capteur est l'espion, il désigne un autre capteur au hasard
        if je_suis_espion:
            return self._vote_espion(mon_id, list(temperatures_autres.keys()))
        
        if not self.ollama_disponible:
            print(f"[{mon_id}] Ollama indisponible, utilisation de l'analyse statistique")
            return self._analyse_fallback(mon_id, temperatures_autres)

        # Construire le contexte
        contexte_stats = self._construire_contexte_statistique(
            mon_id, mes_temperatures, temperatures_autres
        )

        # Construire le prompt
        prompt = f"""Tu es un système expert en détection d'anomalies pour capteurs IoT.

    CONTEXTE :
    - 4 capteurs (rpi1, rpi2, rpi3, rpi4) mesurent la température dans des villes proches
    - L'un des capteurs est un ESPION qui transmet des données falsifiées
    - Les températures normales devraient être cohérentes entre elles

    {contexte_stats}

    MISSION :
    Identifie quel capteur est l'espion en analysant :
    1. Les écarts par rapport à la moyenne globale
    2. La variance des mesures (espion = plus irrégulier)
    3. Les valeurs aberrantes

    IMPORTANT :
    - Réponds UNIQUEMENT avec un JSON valide
    - Format EXACT : {{"suspect": "rpiX", "confiance": 0.85, "justification": "raison claire"}}
    - La confiance doit être entre 0.0 et 1.0
    - Le suspect doit être rpi1, rpi2, rpi3 ou rpi4

    Analyse :"""

        try:
            print(f"[{mon_id}] Analyse en cours avec Ollama...")
            
            # Appel à Ollama
            reponse_brute = self._appeler_ollama(prompt, timeout=self.timeout_requete)
            
            if not reponse_brute:
                print(f"[{mon_id}] Pas de réponse d'Ollama, utilisation de l'analyse statistique")
                return self._analyse_fallback(mon_id, temperatures_autres)
            
            # Extraction du JSON
            analyse = self._extraire_json(reponse_brute)
            
            if analyse and self._valider_analyse(analyse):
                # Normaliser la confiance
                if isinstance(analyse["confiance"], str):
                    try:
                        conf_str = analyse["confiance"].replace('%', '').replace(',', '.')
                        analyse["confiance"] = float(conf_str) / 100 if float(conf_str) > 1 else float(conf_str)
                    except:
                        analyse["confiance"] = 0.5
                
                analyse["confiance"] = max(0.0, min(1.0, float(analyse["confiance"])))
                
                return analyse
            else:
                print(f"[{mon_id}] Analyse invalide, utilisation de l'analyse statistique")
                return self._analyse_fallback(mon_id, temperatures_autres)
                
        except Exception as e:
            print(f"[{mon_id}] Erreur d'analyse : {type(e).__name__}, utilisation de l'analyse statistique")
            return self._analyse_fallback(mon_id, temperatures_autres)

    def _vote_espion(self, mon_id, autres_capteurs_ids):
        """
        Stratégie de vote de l'espion : accuser un autre capteur au hasard
        pour essayer de brouiller les pistes.
        
        Args:
            mon_id: ID du capteur espion
            autres_capteurs_ids: Liste des IDs des autres capteurs
        
        Returns:
            dict: Vote de l'espion contre un autre capteur
        """
        if not autres_capteurs_ids:
            # Au cas où (ne devrait pas arriver)
            return {
                "suspect": "rpi1",
                "confiance": 0.5,
                "justification": "Vote stratégique de l'espion"
            }
        
        # Choisir un autre capteur au hasard
        suspect = random.choice(autres_capteurs_ids)
        
        print(f"[{mon_id}] [ESPION] Stratégie : accuser un autre capteur")
        print(f"[{mon_id}] [ESPION] Cible choisie : {suspect}")
        
        return {
            "suspect": suspect,
            "confiance": 0.7,  # Confiance modérée pour paraître crédible
            "justification": "Données incohérentes détectées (vote stratégique)"
        }

    def _extraire_json(self, texte):
        """Extrait le JSON de la réponse d'Ollama."""
        import re
        
        # Chercher un bloc JSON
        match = re.search(r'\{[^{}]*"suspect"[^{}]*\}', texte)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass
        return None

    def _valider_analyse(self, analyse):
        """Valide qu'une analyse contient tous les champs requis."""
        if not isinstance(analyse, dict):
            return False
        
        champs_requis = ["suspect", "confiance", "justification"]
        if not all(k in analyse for k in champs_requis):
            return False
        
        # Vérifier que le suspect est valide
        if not isinstance(analyse["suspect"], str) or not analyse["suspect"].startswith("rpi"):
            return False
        
        return True

    def _analyse_fallback(self, mon_id, temperatures_autres):
        """
        Analyse de secours basée sur des statistiques simples.
        Identifie le capteur avec le plus grand écart à la moyenne.
        
        Args:
            mon_id: ID du capteur effectuant l'analyse
            temperatures_autres: Dict des températures des autres capteurs
        """
        if not temperatures_autres:
            # Choisir un capteur au hasard parmi les autres
            capteurs_possibles = [f"rpi{i}" for i in range(1, 5) if f"rpi{i}" != mon_id]
            return {
                "suspect": random.choice(capteurs_possibles) if capteurs_possibles else "rpi1",
                "confiance": 0.3,
                "justification": "Analyse par défaut (aucune donnée)"
            }

        # Calculer la moyenne globale
        toutes_valeurs = []
        for temps in temperatures_autres.values():
            toutes_valeurs.extend(temps)
        
        moyenne_globale = mean(toutes_valeurs) if toutes_valeurs else 0

        # Trouver le capteur avec le plus grand écart
        ecarts = {}
        for capteur_id, temps in temperatures_autres.items():
            if temps:
                moy_capteur = mean(temps)
                ecarts[capteur_id] = abs(moy_capteur - moyenne_globale)

        if ecarts:
            suspect = max(ecarts, key=ecarts.get)
            ecart_max = ecarts[suspect]
            confiance = min(0.9, ecart_max / 10)  # Confiance basée sur l'écart
            
            return {
                "suspect": suspect,
                "confiance": confiance,
                "justification": f"Écart maximal à la moyenne : {ecart_max:.1f}°C"
            }
        else:
            # Choisir un capteur au hasard parmi les autres
            capteurs_possibles = [f"rpi{i}" for i in range(1, 5) if f"rpi{i}" != mon_id]
            return {
                "suspect": random.choice(capteurs_possibles) if capteurs_possibles else "rpi1",
                "confiance": 0.3,
                "justification": "Analyse statistique par défaut"
            }


class CapteurTemperature:
    """
    Capteur de température IoT avec capacité de détection d'anomalies.
    Peut jouer le rôle de capteur normal ou d'espion selon l'attribution du serveur.
    Utilise l'IA pour analyser les données et identifier l'espion.
    """

    def __init__(self, capteur_id, broker_address="10.109.150.133", broker_port=1883):
        self.capteur_id = capteur_id
        self.broker_address = broker_address
        self.broker_port = broker_port
        self.client = mqtt.Client(capteur_id)

        # Configuration réseau
        self.mon_ip = self.obtenir_ip_locale()

        # Données du jeu
        self.role = None
        self.ma_latitude = None
        self.ma_longitude = None
        self.tous_capteurs = []
        self.villes_coords = {}
        self.capteurs_ips = {}
        self.config_recue = False
        self.role_recu = False

        # Collecte des données
        self.temperatures_recues = defaultdict(list)
        self.mes_temperatures_publiees = []
        self.nb_publications = 0
        self.MAX_PUBLICATIONS = 5

        # Agent IA pour l'analyse
        self.analyseur = AnalyseurIA(ollama_url="http://10.103.1.12:11434")

        # Synchronisation
        self.lock = threading.Lock()
        self.publication_terminee = False

        # Configuration des callbacks
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def obtenir_ip_locale(self):
        """Récupère l'adresse IP locale du Raspberry Pi."""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "IP inconnue"

    def on_connect(self, client, userdata, flags, rc):
        """Callback appelé lors de la connexion au broker MQTT."""
        if rc == 0:
            print(f"[{self.capteur_id}] Connecté au broker MQTT {self.broker_address}:{self.broker_port}")
            print(f"[{self.capteur_id}] Adresse IP locale : {self.mon_ip}")

            # Souscription aux topics
            client.subscribe("iot/config")
            client.subscribe(f"iot/role/{self.capteur_id}")
            client.subscribe("iot/capteurs/+/temperature")

            # Signaler sa présence au serveur
            presence_message = json.dumps({
                "capteur_id": self.capteur_id,
                "ip": self.mon_ip,
                "timestamp": time.time()
            })
            client.publish(f"iot/capteurs/{self.capteur_id}/presence", presence_message, qos=1)
        else:
            print(f"[{self.capteur_id}] Échec de connexion, code : {rc}")

    def on_message(self, client, userdata, msg):
        """Callback appelé lors de la réception d'un message MQTT."""
        try:
            payload = msg.payload.decode('utf-8')
            topic_parts = msg.topic.split('/')

            # Réception de la configuration du jeu
            if msg.topic == "iot/config":
                config = json.loads(payload)
                self.tous_capteurs = config.get("capteurs", [])
                self.villes_coords = config.get("villes_coords", {})
                self.capteurs_ips = config.get("capteurs_ips", {})
                self.config_recue = True

                print(f"[{self.capteur_id}] Configuration reçue : {len(self.tous_capteurs)} capteurs")

            # Réception du rôle attribué
            elif topic_parts[1] == "role" and topic_parts[2] == self.capteur_id:
                role_data = json.loads(payload)
                self.role = role_data.get("role")
                self.ma_latitude = role_data.get("latitude")
                self.ma_longitude = role_data.get("longitude")
                self.role_recu = True

                role_display = "ESPION" if self.role == "espion" else "Normal"
                print(f"\n{'='*60}")
                print(f"[{self.capteur_id}] Rôle attribué : {role_display}")
                print(f"[{self.capteur_id}] Coordonnées : ({self.ma_latitude}, {self.ma_longitude})")
                print(f"{'='*60}\n")

                # Démarrer la publication des températures
                threading.Thread(target=self.publier_temperatures, daemon=True).start()

            # Réception d'une température d'un autre capteur
            elif topic_parts[1] == "capteurs" and topic_parts[3] == "temperature":
                autre_capteur_id = topic_parts[2]

                if autre_capteur_id != self.capteur_id:
                    temp_data = json.loads(payload)
                    temperature = temp_data.get("temperature")

                    with self.lock:
                        self.temperatures_recues[autre_capteur_id].append(temperature)

                    autre_ip = self.capteurs_ips.get(autre_capteur_id, "IP inconnue")
                    print(f"[{self.capteur_id}] Reçu de {autre_capteur_id} ({autre_ip}) : {temperature}°C")

        except json.JSONDecodeError as e:
            print(f"[{self.capteur_id}] Erreur JSON sur {msg.topic}: {e}")
        except Exception as e:
            print(f"[{self.capteur_id}] Erreur traitement message : {e}")

    def obtenir_temperature_api(self, latitude, longitude):
        """Récupère la température actuelle depuis l'API Open-Meteo."""
        try:
            url = (f"https://api.open-meteo.com/v1/forecast?"
                   f"latitude={latitude}&longitude={longitude}&current_weather=true")
            response = requests.get(url, timeout=10)
            data = response.json()
            temperature = data["current_weather"]["temperature"]
            return round(temperature, 1)
        except Exception as e:
            print(f"[{self.capteur_id}] Erreur API Open-Meteo : {e}")
            return 15.0

    def generer_temperature_espion(self):
        """
        Génère une température falsifiée suivant une loi normale.
        Utilise la température réelle comme moyenne avec un écart-type de 3°C.
        """
        temp_reelle = self.obtenir_temperature_api(self.ma_latitude, self.ma_longitude)
        ecart_type = 3.0
        temp_falsifiee = random.gauss(temp_reelle, ecart_type)
        return round(temp_falsifiee, 1)

    def publier_temperatures(self):
        """
        Publie une température toutes les 5 secondes.
        Température réelle si rôle normal, falsifiée si espion.
        """
        time.sleep(1)
        print(f"[{self.capteur_id}] Début de la publication des températures\n")

        while self.nb_publications < self.MAX_PUBLICATIONS:
            # Générer la température selon le rôle
            if self.role == "espion":
                temperature = self.generer_temperature_espion()
            else:
                temperature = self.obtenir_temperature_api(self.ma_latitude, self.ma_longitude)

            # Publier la température
            message = json.dumps({
                "temperature": temperature,
                "timestamp": time.time()
            })
            topic = f"iot/capteurs/{self.capteur_id}/temperature"
            self.client.publish(topic, message, qos=1)

            with self.lock:
                self.mes_temperatures_publiees.append(temperature)
                self.nb_publications += 1

            print(f"[{self.capteur_id}] Publié : {temperature}°C "
                  f"[{self.nb_publications}/{self.MAX_PUBLICATIONS}]")

            time.sleep(5)

        self.publication_terminee = True
        print(f"\n[{self.capteur_id}] Publication terminée\n")

        # Attendre les données des autres capteurs
        self.attendre_toutes_temperatures()

        # Analyser avec l'IA et voter
        self.phase_analyse_ia()

    def attendre_toutes_temperatures(self):
        """Attend que toutes les températures des autres capteurs soient reçues."""
        nb_capteurs_attendus = len(self.tous_capteurs) - 1
        print(f"[{self.capteur_id}] Attente des températures des autres capteurs...")

        temps_attente = 0
        temps_max = 30

        while temps_attente < temps_max:
            with self.lock:
                nb_recus = len([c for c in self.temperatures_recues.keys() 
                               if len(self.temperatures_recues[c]) >= self.MAX_PUBLICATIONS])

            if nb_recus >= nb_capteurs_attendus:
                print(f"[{self.capteur_id}] Toutes les températures reçues ({nb_recus}/{nb_capteurs_attendus})")
                return

            time.sleep(1)
            temps_attente += 1

        with self.lock:
            nb_recus = len([c for c in self.temperatures_recues.keys() 
                           if len(self.temperatures_recues[c]) >= self.MAX_PUBLICATIONS])
        print(f"[{self.capteur_id}] Timeout : {nb_recus}/{nb_capteurs_attendus} températures reçues")

    def phase_analyse_ia(self):
        """
        Phase d'analyse avec IA pour identifier l'espion et voter.
        L'espion accusera un autre capteur pour brouiller les pistes.
        """
        print(f"\n[{self.capteur_id}] {'='*60}")
        print(f"[{self.capteur_id}] PHASE D'ANALYSE AVEC IA")
        print(f"[{self.capteur_id}] {'='*60}\n")

        # Récupérer les données collectées
        with self.lock:
            mes_temperatures = self.mes_temperatures_publiees.copy()
            temperatures_autres = {k: v.copy() for k, v in self.temperatures_recues.items()}

        # Déterminer si ce capteur est l'espion
        je_suis_espion = (self.role == "espion")

        # Analyser avec Ollama (ou stratégie espion)
        analyse = self.analyseur.analyser_espion(
            self.capteur_id,
            mes_temperatures,
            temperatures_autres,
            je_suis_espion=je_suis_espion
        )

        # Affichage selon le statut (espion ou normal)
        if je_suis_espion:
            print(f"[{self.capteur_id}] [ESPION] Accusation stratégique : {analyse['suspect']}")
            print(f"[{self.capteur_id}] [ESPION] Tentative de brouiller les pistes\n")
        else:
            print(f"[{self.capteur_id}] Suspect identifié : {analyse['suspect']}")
            print(f"[{self.capteur_id}] Confiance : {analyse['confiance']:.0%}")
            print(f"[{self.capteur_id}] Justification : {analyse['justification']}\n")

        # Voter pour le suspect identifié
        self.voter(analyse['suspect'])

    def voter(self, suspect_id):
        """Envoie un vote au serveur pour désigner le capteur suspect."""
        vote_message = json.dumps({
            "suspect": suspect_id,
            "timestamp": time.time()
        })
        topic = f"iot/votes/{self.capteur_id}"
        self.client.publish(topic, vote_message, qos=1)

        print(f"[{self.capteur_id}] Vote envoyé : {suspect_id}")
        print(f"[{self.capteur_id}] En attente des résultats...\n")

    def executer(self):
        """Lance l'exécution du capteur."""
        print(f"[{self.capteur_id}] Démarrage du capteur")
        print(f"[{self.capteur_id}] Adresse IP : {self.mon_ip}\n")

        try:
            self.client.connect(self.broker_address, self.broker_port, 60)
            self.client.loop_forever()
        except KeyboardInterrupt:
            print(f"\n[{self.capteur_id}] Arrêt du capteur")
            self.client.disconnect()
        except Exception as e:
            print(f"[{self.capteur_id}] Erreur : {e}")
            self.client.disconnect()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage : python3 capteur.py <id_capteur>")
        print("Exemple : python3 capteur.py rpi1")
        sys.exit(1)

    capteur_id = sys.argv[1]
    
    ids_valides = ["rpi1", "rpi2", "rpi3", "rpi4"]
    if capteur_id not in ids_valides:
        print(f"ID invalide. Utilisez : {', '.join(ids_valides)}")
        sys.exit(1)

    capteur = CapteurTemperature(capteur_id, broker_address="10.109.150.133")
    capteur.executer()
