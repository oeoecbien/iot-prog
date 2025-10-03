import paho.mqtt.client as mqtt
import requests
import time
import json
import random
import sys
import threading
from collections import defaultdict
import numpy as np

# Forcer l'encodage UTF-8 pour la sortie console
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


class GenerateurTemperatureEspion:
    """
    Générateur de températures aberrantes utilisant la loi de Poisson.
    
    Principe :
    - Utilise une distribution de Poisson pour créer des températures irréalistes
    - Lambda élevé pour générer des valeurs aberrantes
    - Transformation pour obtenir des températures dans une plage aberrante
    """

    def __init__(self, lambda_poisson=15, offset=-10, scale=3.5):
        """
        Initialise le générateur avec les paramètres de la loi de Poisson.
        
        Args:
            lambda_poisson: Paramètre lambda de la distribution de Poisson (moyenne)
            offset: Décalage de base pour les températures
            scale: Facteur d'échelle pour l'amplitude des variations
        """
        self.lambda_poisson = lambda_poisson
        self.offset = offset
        self.scale = scale
        
        print(f"[ESPION] Générateur de Poisson initialisé")
        print(f"[ESPION] Paramètres : lambda={lambda_poisson}, offset={offset}, scale={scale}")

    def generer_temperature_aberrante(self):
        """
        Génère une température aberrante selon une loi de Poisson.
        
        Formule : T = offset + scale * Poisson(lambda)
        
        Cette méthode génère des valeurs qui :
        - Sont mathématiquement cohérentes (suivent une distribution)
        - Restent aberrantes par rapport aux températures réelles
        - Varient de manière imprévisible mais structurée
        
        Returns:
            float: Température aberrante en degrés Celsius
        """
        # Tirer une valeur selon la loi de Poisson
        valeur_poisson = np.random.poisson(self.lambda_poisson)
        
        # Transformer en température aberrante
        temperature = self.offset + (self.scale * valeur_poisson)
        
        # Arrondir à 1 décimale
        temperature = round(temperature, 1)
        
        # S'assurer que la température reste dans une plage aberrante mais plausible
        # (éviter des valeurs physiquement impossibles comme -273°C)
        temperature = max(-50.0, min(60.0, temperature))
        
        return temperature

    def generer_temperature_avec_perturbation(self, temperature_base=None):
        """
        Génère une température aberrante avec une composante de perturbation.
        
        Si une température de base est fournie, ajoute une perturbation issue
        de la loi de Poisson pour créer des variations crédibles mais suspectes.
        
        Args:
            temperature_base: Température de référence (optionnelle)
            
        Returns:
            float: Température aberrante
        """
        if temperature_base is None:
            return self.generer_temperature_aberrante()
        
        # Générer une perturbation selon Poisson
        perturbation = np.random.poisson(self.lambda_poisson)
        
        # Appliquer la perturbation (positif ou négatif aléatoirement)
        signe = random.choice([-1, 1])
        temperature = temperature_base + (signe * self.scale * perturbation)
        
        temperature = round(temperature, 1)
        temperature = max(-50.0, min(60.0, temperature))
        
        return temperature

    def afficher_statistiques(self, nb_echantillons=1000):
        """
        Affiche les statistiques de la distribution générée (pour debug).
        
        Args:
            nb_echantillons: Nombre d'échantillons à générer pour l'analyse
        """
        echantillons = [self.generer_temperature_aberrante() for _ in range(nb_echantillons)]
        
        moyenne = np.mean(echantillons)
        ecart_type = np.std(echantillons)
        minimum = np.min(echantillons)
        maximum = np.max(echantillons)
        
        print(f"[ESPION] Statistiques de la distribution (n={nb_echantillons}) :")
        print(f"[ESPION]   Moyenne : {moyenne:.2f}°C")
        print(f"[ESPION]   Écart-type : {ecart_type:.2f}°C")
        print(f"[ESPION]   Min : {minimum:.1f}°C, Max : {maximum:.1f}°C")


class AnalyseurIA:
    """
    Agent d'analyse utilisant Ollama pour détecter l'espion.
    Toute la logique d'analyse est déléguée au LLM.
    """

    def __init__(self, ollama_url="http://10.103.1.12:11434"):
        self.ollama_url = ollama_url
        self.modele = "gemma3:4b"
        self.timeout_requete = 60

        # Test de connectivité au démarrage
        self.ollama_disponible = self._tester_connexion()

    def _tester_connexion(self):
        """Teste la connectivité au serveur Ollama."""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                print("[IA] Connexion à Ollama établie avec succès")
                return True
            return False
        except Exception as e:
            print(f"[IA] Ollama indisponible : {e}")
            return False

    def _appeler_ollama(self, prompt, timeout=60):
        """Appelle l'API Ollama pour obtenir une analyse complète."""
        try:
            payload = {
                "model": self.modele,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,  # Plus déterministe
                    "top_p": 0.85,
                    "num_predict": 512   # Permettre une réponse détaillée
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
        except Exception as e:
            print(f"[IA] Erreur lors de l'appel Ollama : {e}")
            return None

    def _construire_prompt_detective(self, mon_id, mes_temps, autres_temps, capteurs_ips):
        """
        Construit un prompt détaillé pour que le LLM joue le rôle de détective.
        Le LLM reçoit TOUTES les données brutes et doit tout analyser lui-même.
        """
        prompt = f"""Tu es un DÉTECTIVE EXPERT en cybersécurité IoT. Tu dois identifier un espion parmi des capteurs de température.

CONTEXTE DU SYSTÈME :
- Réseau de 4 capteurs IoT (rpi1, rpi2, rpi3, rpi4) surveillant la météo
- Chaque capteur mesure la température dans une ville proche (climat similaire)
- UN SEUL capteur est un ESPION qui transmet des données FALSIFIÉES
- Les capteurs normaux publient des températures COHÉRENTES entre elles
- L'espion utilise une LOI DE POISSON pour générer des valeurs ABERRANTES
- Distribution de Poisson : génère des valeurs qui suivent un pattern mathématique spécifique

TA MISSION :
Analyse les données de température ci-dessous et identifie l'espion avec certitude.

DONNÉES COLLECTÉES :

"""

        # Ajouter les données de TOUS les capteurs (moi + les autres)
        prompt += f"Capteur {mon_id} (IP: {capteurs_ips.get(mon_id, 'inconnue')}) - MOI\n"
        prompt += f"  Températures publiées : {mes_temps}\n\n"

        for capteur_id in sorted(autres_temps.keys()):
            temps = autres_temps[capteur_id]
            ip = capteurs_ips.get(capteur_id, 'inconnue')
            prompt += f"Capteur {capteur_id} (IP: {ip})\n"
            prompt += f"  Températures reçues : {temps}\n\n"

        prompt += """
MÉTHODOLOGIE D'ANALYSE ATTENDUE :

1. Cohérence géographique : Les capteurs sont dans des villes proches
   -> Leurs températures doivent être SIMILAIRES (écart max environ 5 degrés C)

2. Stabilité temporelle : Une vraie température évolue PROGRESSIVEMENT
   -> Variations brusques = SUSPECT

3. Plage de valeurs : Températures réalistes en Europe
   -> Valeurs aberrantes (-20 degrés C, 35 degrés C en hiver) = ESPION

4. Pattern de distribution de Poisson : L'espion utilise une loi mathématique
   -> Chercher des patterns inhabituels, des variations trop régulières ou trop extrêmes
   -> La loi de Poisson peut créer des clusters de valeurs élevées ou faibles

5. Analyse comparative : Compare TOUS les capteurs entre eux
   -> L'espion sera celui qui DIVERGE systématiquement des autres

6. Analyse statistique : Examine la distribution des valeurs
   -> Écart-type anormal, moyenne décalée, outliers récurrents

INDICES SPÉCIFIQUES POUR DÉTECTER LA LOI DE POISSON :
- Valeurs qui varient de manière imprévisible mais avec une structure sous-jacente
- Températures qui ne suivent pas la progression logique jour/nuit
- Écarts importants entre valeurs successives
- Présence de valeurs extrêmes (très chaudes ou très froides)

CONTRAINTES IMPORTANTES :
- Tu DOIS analyser TOUS les capteurs (y compris {mon_id})
- Tu DOIS justifier ton choix avec des PREUVES CHIFFRÉES
- Si les données sont ambiguës, choisis le capteur le PLUS SUSPECT

FORMAT DE RÉPONSE OBLIGATOIRE (JSON strict) :
{{
  "suspect": "rpiX",
  "confiance": 0.XX,
  "preuves": [
    "Preuve 1 avec chiffres",
    "Preuve 2 avec chiffres",
    "Preuve 3 avec chiffres"
  ],
  "analyse_comparative": "Résumé de la comparaison entre tous les capteurs"
}}

RÈGLES :
- "suspect" doit être : rpi1, rpi2, rpi3 ou rpi4
- "confiance" doit être entre 0.0 et 1.0 (ex: 0.85)
- "preuves" doit contenir 2 à 4 arguments factuels avec chiffres
- Réponds UNIQUEMENT avec le JSON, rien d'autre

Commence ton analyse maintenant :"""

        return prompt

    def analyser_espion(self, mon_id, mes_temperatures, temperatures_autres, capteurs_ips, je_suis_espion=False):
        """
        Délègue l'analyse complète au LLM.

        Args:
            mon_id: Identifiant du capteur effectuant l'analyse
            mes_temperatures: Liste des températures publiées par ce capteur
            temperatures_autres: Dict {capteur_id: [températures]}
            capteurs_ips: Mapping des IPs des capteurs
            je_suis_espion: Si True, vote stratégique au hasard

        Returns:
            dict: {"suspect": "rpiX", "confiance": 0.XX, "preuves": [...]}
        """
        # Si ce capteur est l'espion, il accuse un autre capteur au hasard
        if je_suis_espion:
            return self._vote_espion(mon_id, list(temperatures_autres.keys()))

        # Vérifier la disponibilité d'Ollama
        if not self.ollama_disponible:
            print(f"[{mon_id}] ATTENTION : Ollama indisponible, vote aléatoire")
            return self._vote_aleatoire(mon_id, list(temperatures_autres.keys()))

        print(f"[{mon_id}] Consultation du détective IA...")
        print(f"[{mon_id}] Données à analyser :")
        print(f"[{mon_id}]    - Mes températures : {mes_temperatures}")
        for cid, temps in sorted(temperatures_autres.items()):
            print(f"[{mon_id}]    - {cid} : {temps}")

        # Construire le prompt pour le LLM
        prompt = self._construire_prompt_detective(
            mon_id, mes_temperatures, temperatures_autres, capteurs_ips
        )

        try:
            # Appel au LLM
            print(f"[{mon_id}] Analyse en cours (timeout: {self.timeout_requete}s)...")
            reponse_brute = self._appeler_ollama(prompt, timeout=self.timeout_requete)

            if not reponse_brute:
                print(f"[{mon_id}] Pas de réponse du LLM, vote aléatoire")
                return self._vote_aleatoire(mon_id, list(temperatures_autres.keys()))

            print(f"[{mon_id}] Réponse reçue du LLM\n")

            # Extraire et valider le JSON
            analyse = self._extraire_json(reponse_brute)

            if analyse and self._valider_analyse(analyse):
                # Normaliser la confiance
                analyse["confiance"] = self._normaliser_confiance(analyse["confiance"])
                
                print(f"[{mon_id}] Analyse validée par le LLM")
                return analyse
            else:
                print(f"[{mon_id}] ATTENTION : Réponse invalide du LLM, vote aléatoire")
                print(f"[{mon_id}] Réponse brute : {reponse_brute[:200]}...")
                return self._vote_aleatoire(mon_id, list(temperatures_autres.keys()))

        except Exception as e:
            print(f"[{mon_id}] ERREUR critique : {type(e).__name__} - {e}")
            return self._vote_aleatoire(mon_id, list(temperatures_autres.keys()))

    def _vote_espion(self, mon_id, autres_capteurs_ids):
        """Vote stratégique de l'espion : accuser un autre capteur au hasard."""
        if not autres_capteurs_ids:
            return {
                "suspect": "rpi1",
                "confiance": 0.6,
                "preuves": ["Vote stratégique de l'espion"],
                "analyse_comparative": "Tentative de brouillage"
            }

        suspect = random.choice(autres_capteurs_ids)

        print(f"[{mon_id}] [ESPION] Accusation stratégique : {suspect}")

        return {
            "suspect": suspect,
            "confiance": 0.65,
            "preuves": [
                f"Détection d'incohérences dans les données de {suspect}",
                "Écarts significatifs observés"
            ],
            "analyse_comparative": "Vote de perturbation stratégique"
        }

    def _vote_aleatoire(self, mon_id, autres_capteurs_ids):
        """Vote de secours aléatoire si le LLM ne répond pas."""
        if not autres_capteurs_ids:
            return {
                "suspect": "rpi1",
                "confiance": 0.25,
                "preuves": ["Analyse par défaut (LLM indisponible)"],
                "analyse_comparative": "Vote aléatoire de secours"
            }

        suspect = random.choice(autres_capteurs_ids)

        return {
            "suspect": suspect,
            "confiance": 0.25,
            "preuves": ["Vote aléatoire (LLM indisponible)"],
            "analyse_comparative": "Analyse de secours"
        }

    def _extraire_json(self, texte):
        """Extrait le JSON de la réponse du LLM."""
        import re

        # Méthode 1 : Chercher un bloc JSON complet
        match = re.search(r'\{[^{}]*"suspect"[^{}]*\}', texte, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass

        # Méthode 2 : Chercher entre accolades les plus externes
        debut = texte.find('{')
        fin = texte.rfind('}')
        if debut != -1 and fin != -1 and debut < fin:
            try:
                return json.loads(texte[debut:fin+1])
            except:
                pass

        return None

    def _valider_analyse(self, analyse):
        """Valide qu'une analyse contient tous les champs requis."""
        if not isinstance(analyse, dict):
            return False

        # Vérifier les champs obligatoires
        champs_requis = ["suspect", "confiance"]
        if not all(k in analyse for k in champs_requis):
            return False

        # Vérifier que le suspect est valide
        if not isinstance(analyse["suspect"], str) or not analyse["suspect"].startswith("rpi"):
            return False

        # Ajouter les champs manquants si nécessaire
        if "preuves" not in analyse:
            analyse["preuves"] = ["Analyse du LLM"]
        if "analyse_comparative" not in analyse:
            analyse["analyse_comparative"] = "Analyse effectuée"

        return True

    def _normaliser_confiance(self, confiance):
        """Normalise la valeur de confiance entre 0.0 et 1.0."""
        if isinstance(confiance, str):
            try:
                # Retirer les symboles % et convertir
                conf_str = confiance.replace('%', '').replace(',', '.').strip()
                confiance = float(conf_str)
                
                # Si > 1, considérer comme pourcentage
                if confiance > 1:
                    confiance = confiance / 100
            except:
                return 0.5

        # Limiter entre 0 et 1
        return max(0.0, min(1.0, float(confiance)))


class CapteurTemperature:
    """
    Capteur de température IoT avec détection d'espion par IA.
    Toute l'analyse est déléguée au LLM via Ollama.
    L'espion utilise une distribution de Poisson pour générer des températures aberrantes.
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

        # Générateur de températures pour l'espion (loi de Poisson)
        self.generateur_espion = GenerateurTemperatureEspion(
            lambda_poisson=15,  # Paramètre lambda de la distribution
            offset=-10,         # Température de base
            scale=3.5           # Facteur d'échelle
        )

        # Agent IA pour l'analyse (délégation complète)
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

            # Signaler la présence
            presence_msg = json.dumps({"ip": self.mon_ip, "timestamp": time.time()})
            client.publish(f"iot/capteurs/{self.capteur_id}/presence", presence_msg, qos=1, retain=True)

            print(f"[{self.capteur_id}] En attente de la configuration...")
        else:
            print(f"[{self.capteur_id}] ERREUR de connexion (code: {rc})")

    def on_message(self, client, userdata, msg):
        """Callback appelé lors de la réception d'un message MQTT."""
        try:
            # Ignorer les messages vides (nettoyage)
            if len(msg.payload) == 0:
                return

            topic_parts = msg.topic.split('/')

            # Configuration du système
            if msg.topic == "iot/config":
                self.traiter_configuration(msg.payload)

            # Attribution du rôle
            elif topic_parts[1] == "role" and topic_parts[2] == self.capteur_id:
                self.traiter_role(msg.payload)

            # Réception des températures des autres capteurs
            elif topic_parts[1] == "capteurs" and topic_parts[3] == "temperature":
                capteur_source = topic_parts[2]
                if capteur_source != self.capteur_id:
                    self.traiter_temperature_recue(capteur_source, msg.payload)

        except Exception as e:
            print(f"[{self.capteur_id}] Erreur traitement message : {e}")

    def traiter_configuration(self, payload):
        """Traite le message de configuration envoyé par le serveur."""
        try:
            config = json.loads(payload.decode())
            
            with self.lock:
                self.tous_capteurs = config["capteurs"]
                self.villes_coords = {k: tuple(v) for k, v in config["villes_coords"].items()}
                self.capteurs_ips = config["capteurs_ips"]
                
                # Récupérer mes coordonnées
                if self.capteur_id in self.villes_coords:
                    self.ma_latitude, self.ma_longitude = self.villes_coords[self.capteur_id]
                
                self.config_recue = True

            print(f"[{self.capteur_id}] Configuration reçue")
            print(f"[{self.capteur_id}] Ma position : ({self.ma_latitude}, {self.ma_longitude})")
            
            self.demarrer_si_pret()

        except Exception as e:
            print(f"[{self.capteur_id}] Erreur configuration : {e}")

    def traiter_role(self, payload):
        """Traite l'attribution du rôle par le serveur."""
        try:
            role_data = json.loads(payload.decode())
            
            with self.lock:
                self.role = role_data["role"]
                self.role_recu = True

            if self.role == "espion":
                print(f"[{self.capteur_id}] ========================================")
                print(f"[{self.capteur_id}] RÔLE ASSIGNÉ : ESPION")
                print(f"[{self.capteur_id}] Mission : Publier des températures aberrantes")
                print(f"[{self.capteur_id}] Méthode : Distribution de Poisson")
                print(f"[{self.capteur_id}] ========================================")
                
                # Afficher les statistiques du générateur (optionnel)
                # self.generateur_espion.afficher_statistiques()
            else:
                print(f"[{self.capteur_id}] Rôle assigné : Capteur normal")
                print(f"[{self.capteur_id}] Mission : Détecter l'espion")

            self.demarrer_si_pret()

        except Exception as e:
            print(f"[{self.capteur_id}] Erreur traitement rôle : {e}")

    def traiter_temperature_recue(self, capteur_source, payload):
        """Enregistre une température reçue d'un autre capteur."""
        try:
            data = json.loads(payload.decode())
            temperature = data["temperature"]

            with self.lock:
                self.temperatures_recues[capteur_source].append(temperature)

        except Exception as e:
            print(f"[{self.capteur_id}] Erreur réception température : {e}")

    def demarrer_si_pret(self):
        """Démarre la publication si configuration et rôle sont reçus."""
        with self.lock:
            if self.config_recue and self.role_recu and self.nb_publications == 0:
                print(f"[{self.capteur_id}] Démarrage de la phase de publication")
                threading.Thread(target=self.publier_temperatures, daemon=True).start()

    def obtenir_temperature(self):
        """
        Récupère une température selon le rôle du capteur.
        
        Returns:
            float: Température en degrés Celsius
        """
        if self.role == "espion":
            # Utiliser la loi de Poisson pour générer une température aberrante
            temp = self.generateur_espion.generer_temperature_aberrante()
            return temp
        else:
            # Température réaliste via API Open-Meteo
            try:
                url = f"https://api.open-meteo.com/v1/forecast"
                params = {
                    "latitude": self.ma_latitude,
                    "longitude": self.ma_longitude,
                    "current_weather": "true"
                }
                
                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    temp = data["current_weather"]["temperature"]
                    return round(temp, 1)
                else:
                    # Fallback : température par défaut
                    return 10.0
            except Exception as e:
                print(f"[{self.capteur_id}] Erreur API météo : {e}")
                return 10.0

    def publier_temperatures(self):
        """Publie 5 températures espacées de 5 secondes."""
        print(f"[{self.capteur_id}] {'='*60}")
        print(f"[{self.capteur_id}] PHASE DE PUBLICATION")
        print(f"[{self.capteur_id}] {'='*60}\n")

        for i in range(self.MAX_PUBLICATIONS):
            temperature = self.obtenir_temperature()

            # Enregistrer ma température
            with self.lock:
                self.mes_temperatures_publiees.append(temperature)
                self.nb_publications += 1

            # Publier sur MQTT
            message = json.dumps({
                "temperature": temperature,
                "timestamp": time.time(),
                "publication_num": i + 1
            })

            topic = f"iot/capteurs/{self.capteur_id}/temperature"
            self.client.publish(topic, message, qos=1, retain=False)

            if self.role == "espion":
                print(f"[{self.capteur_id}] [ESPION] Publication {i+1}/5 : {temperature}°C (Poisson)")
            else:
                print(f"[{self.capteur_id}] Publication {i+1}/5 : {temperature}°C")

            if i < self.MAX_PUBLICATIONS - 1:
                time.sleep(5)

        # Marquer la fin de la publication
        with self.lock:
            self.publication_terminee = True

        print(f"\n[{self.capteur_id}] Publications terminées")
        print(f"[{self.capteur_id}] Attente de réception des données des autres capteurs...\n")

        # Attendre un peu pour recevoir toutes les données
        time.sleep(3)

        # Lancer l'analyse
        self.analyser_et_voter()

    def analyser_et_voter(self):
        """
        Analyse les températures collectées en déléguant au LLM.
        Si espion : vote aléatoire pour brouiller les pistes.
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
            self.capteurs_ips,
            je_suis_espion=je_suis_espion
        )

        # Affichage selon le statut (espion ou normal)
        if je_suis_espion:
            print(f"[{self.capteur_id}] [ESPION] Accusation stratégique : {analyse['suspect']}")
            print(f"[{self.capteur_id}] [ESPION] Tentative de brouiller les pistes\n")
        else:
            print(f"[{self.capteur_id}] Suspect identifié : {analyse['suspect']}")
            print(f"[{self.capteur_id}] Confiance : {analyse['confiance']:.0%}")
            print(f"[{self.capteur_id}] Justification :")
            for preuve in analyse.get('preuves', []):
                print(f"[{self.capteur_id}]   - {preuve}")
            print()

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
