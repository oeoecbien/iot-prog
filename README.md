# iot-prog

## Description

Ce projet propose un jeu distribué de détection d'espion entre plusieurs capteurs IoT (Raspberry Pi). Chaque capteur publie des mesures de température sur un broker MQTT. L'un des capteurs joue le rôle d'espion et falsifie ses données. Les autres capteurs, aidés par une IA (Ollama), tentent d'identifier l'espion. Un serveur arbitre centralise les rôles, collecte les votes et annonce le résultat.

## Structure

- `tp_jeu/server.py` : Serveur arbitre du jeu. Il attribue les rôles, collecte les votes et détermine le gagnant.
- `tp_jeu/capteur.py` : Script à lancer sur chaque capteur. Il publie les températures et vote pour désigner l'espion.
- `tp_jeu/cleanup_mqtt.py` : Utilitaire pour nettoyer les topics MQTT (messages retained) avant une nouvelle partie.
- `tp_jeu/requirements.txt` : Dépendances Python nécessaires (paho-mqtt, requests).

## Installation

1. Installe Python 3.x sur chaque machine.
2. Installe les dépendances :
   ```sh
   pip install -r tp_jeu/requirements.txt
   ```

## Utilisation

### 1. Nettoyage du broker MQTT (optionnel mais recommandé)

Avant chaque partie, lance le nettoyage :
```sh
python tp_jeu/cleanup_mqtt.py
```

### 2. Démarrage du serveur arbitre

Sur la machine centrale (arbitre) :
```sh
python tp_jeu/server.py
```

### 3. Démarrage des capteurs

Sur chaque Raspberry Pi (ou machine simulant un capteur), lance :
```sh
python tp_jeu/capteur.py <id_capteur>
```
où `<id_capteur>` est l'un des identifiants suivants : `rpi1`, `rpi2`, `rpi3`, `rpi4`.

Exemple :
```sh
python tp_jeu/capteur.py rpi1
```

### 4. Déroulement du jeu

- Les capteurs se connectent au broker MQTT et publient leurs températures (réelles ou falsifiées).
- Après 5 publications, chaque capteur analyse les données reçues (via IA ou statistiques) et vote pour désigner l'espion.
- Le serveur arbitre collecte les votes et affiche le résultat (victoire des capteurs ou de l'espion).

## Configuration

- Adresse du broker MQTT : `10.109.150.133` (modifiable dans les scripts).
- Les coordonnées géographiques et IP des capteurs sont définies dans le serveur.

## IA utilisée

- L'analyse des données pour détecter l'espion utilise le serveur Ollama (`http://10.103.1.12:11434`) avec le modèle `gemma3:4b`.
- Si Ollama n'est pas disponible, une analyse statistique simple est utilisée.

## Remarques

- Le projet est conçu pour fonctionner sur un réseau local avec 4 capteurs.
- Les scripts affichent des logs détaillés pour suivre le déroulement de la partie.

## Auteur

Projet pédagogique IoT