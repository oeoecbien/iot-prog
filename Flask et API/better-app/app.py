from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import secrets
import os
from datetime import datetime
import openmeteo_requests
import requests_cache
from retry_requests import retry
import requests
import pandas as pd

# ------------------------------------------------------
# Configuration Flask
# ------------------------------------------------------
app = Flask(__name__)

# $env:SUPABASE_DB_URL="postgresql://postgres.fbhvpmszrzgjmnxxnhkl:32.Melih.32@aws-1-eu-west-3.pooler.supabase.com:5432/postgres"
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("SUPABASE_DB_URL", "postgresql://postgres.fbhvpmszrzgjmnxxnhkl:32.Melih.32@aws-1-eu-west-3.pooler.supabase.com:5432/postgres")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# Open-Meteo client
cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

GOOGLE_GEOCODING_API_KEY = os.environ.get('GOOGLE_GEOCODING_API_KEY')

# ------------------------------------------------------
# Modèle utilisateur
# ------------------------------------------------------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    token = db.Column(db.String(128), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, username, email, password):
        self.username = username
        self.email = email
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
        self.token = secrets.token_urlsafe(32)

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {"username": self.username, "email": self.email, "token": self.token}

# ------------------------------------------------------
# Authentification
# ------------------------------------------------------
def require_token(func):
    """Décorateur pour sécuriser les routes avec un token"""
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token:
            return jsonify({"error": "Token manquant"}), 401
        user = User.query.filter_by(token=token).first()
        if not user:
            return jsonify({"error": "Token invalide"}), 403
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

# ------------------------------------------------------
# Géocodage
# ------------------------------------------------------
def get_coordinates_google(address):
    if not GOOGLE_GEOCODING_API_KEY:
        return None, None, None
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_GEOCODING_API_KEY}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data["status"] == "OK" and data["results"]:
            res = data["results"][0]
            loc = res["geometry"]["location"]
            return loc["lat"], loc["lng"], res["formatted_address"]
    except:
        return None, None, None
    return None, None, None

def get_coordinates_openmeteo(address):
    url = "https://geocoding-api.open-meteo.com/v1/search"
    try:
        r = requests.get(url, params={"name": address}, timeout=10)
        data = r.json()
        if "results" in data and data["results"]:
            res = data["results"][0]
            return res["latitude"], res["longitude"], res["name"]
    except:
        return None, None, None
    return None, None, None

def get_coordinates(address):
    lat, lon, name = get_coordinates_google(address)
    if lat is None:
        lat, lon, name = get_coordinates_openmeteo(address)
    return lat, lon, name

# ------------------------------------------------------
# Données météo
# ------------------------------------------------------
def get_weather_data(lat, lon, start_date=None, end_date=None):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,rain",
        "daily": "temperature_2m_max,temperature_2m_min,rain_sum",
        "timezone": "Europe/Paris",
    }
    if start_date: params["start_date"] = start_date
    if end_date: params["end_date"] = end_date
    try:
        responses = openmeteo.weather_api(url, params=params)
        r = responses[0]
        hourly = r.Hourly()
        daily = r.Daily()
        hourly_data = {
            "date": pd.date_range(
                start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
                end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
                freq=pd.Timedelta(seconds=hourly.Interval()),
                inclusive="left",
            ),
            "temperature": hourly.Variables(0).ValuesAsNumpy(),
            "rain": hourly.Variables(1).ValuesAsNumpy(),
        }
        daily_data = {
            "date": pd.date_range(
                start=pd.to_datetime(daily.Time(), unit="s", utc=True),
                end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
                freq=pd.Timedelta(seconds=daily.Interval()),
                inclusive="left",
            ),
            "temperature_max": daily.Variables(0).ValuesAsNumpy(),
            "temperature_min": daily.Variables(1).ValuesAsNumpy(),
            "rain_sum": daily.Variables(2).ValuesAsNumpy(),
        }
        return pd.DataFrame(hourly_data), pd.DataFrame(daily_data)
    except Exception as e:
        print("Erreur météo :", e)
        return None, None

# ------------------------------------------------------
# Routes API
# ------------------------------------------------------

@app.route("/api/register", methods=["POST"])
def register():
    """Créer un compte utilisateur avec un token"""
    data = request.json
    if not data or not all(k in data for k in ("username", "email", "password")):
        return jsonify({"error": "username, email et password requis"}), 400
    if User.query.filter((User.username == data["username"]) | (User.email == data["email"])).first():
        return jsonify({"error": "Utilisateur déjà existant"}), 409
    user = User(data["username"], data["email"], data["password"])
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "Utilisateur créé", "user": user.to_dict()}), 201

@app.route("/api/login", methods=["POST"])
def login():
    """Connexion : renvoie le token"""
    data = request.json
    if not data or "username" not in data or "password" not in data:
        return jsonify({"error": "username et password requis"}), 400
    user = User.query.filter_by(username=data["username"]).first()
    if not user or not user.check_password(data["password"]):
        return jsonify({"error": "Identifiants invalides"}), 401
    return jsonify({"message": "Connexion réussie", "token": user.token}), 200

@app.route("/api/weather/rain", methods=["GET"])
@require_token
def rain():
    """Précipitations totales prévues pour une adresse"""
    address = request.args.get("address")
    date = request.args.get("date")
    if not address:
        return jsonify({"error": "Paramètre address requis"}), 400
    lat, lon, name = get_coordinates(address)
    if lat is None:
        return jsonify({"error": "Adresse introuvable"}), 404
    hourly_df, daily_df = get_weather_data(lat, lon, date, date)
    if hourly_df is None:
        return jsonify({"error": "Impossible de récupérer les données"}), 500
    total_rain = float(hourly_df["rain"].sum())
    return jsonify({
        "address": address,
        "location": name,
        "date": date,
        "rain_total_mm": total_rain
    })

@app.route("/api/weather/temperature", methods=["GET"])
@require_token
def temperature():
    """Températures prévues pour une adresse"""
    address = request.args.get("address")
    date = request.args.get("date")
    if not address:
        return jsonify({"error": "Paramètre address requis"}), 400
    lat, lon, name = get_coordinates(address)
    if lat is None:
        return jsonify({"error": "Adresse introuvable"}), 404
    hourly_df, _ = get_weather_data(lat, lon, date, date)
    if hourly_df is None:
        return jsonify({"error": "Impossible de récupérer les données"}), 500
    temps = hourly_df["temperature"]
    return jsonify({
        "address": address,
        "location": name,
        "date": date,
        "temperature": {
            "min": float(temps.min()),
            "max": float(temps.max()),
            "avg": float(temps.mean())
        }
    })

# ------------------------------------------------------
# Init DB
# ------------------------------------------------------
def init_db():
    with app.app_context():
        db.create_all()

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
