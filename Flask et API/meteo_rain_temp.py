import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry
import requests
import matplotlib.pyplot as plt
import sys

def print_section(title):
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")

print_section("Géocodage de l'adresse")
address = input("Entrez une adresse ou un lieu : ").strip()

def get_coordinates(address):
    geocode_url = "https://geocoding-api.open-meteo.com/v1/search"
    response = requests.get(geocode_url, params={"name": address})
    data = response.json()
    if "results" in data and len(data["results"]) > 0:
        result = data["results"][0]
        return result["latitude"], result["longitude"], result["name"]
    else:
        raise ValueError("Adresse non trouvée.")

try:
    latitude, longitude, location_name = get_coordinates(address)
    print(f"Localisation trouvée : {location_name} ({latitude}, {longitude})")
except ValueError as e:
    print(e)
    sys.exit(1)

print_section("Initialisation du client Open-Meteo")
cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)
print("Client initialisé.")

print_section("Téléchargement des données météo horaires")
url = "https://api.open-meteo.com/v1/forecast"
params = {
    "latitude": latitude,
    "longitude": longitude,
    "hourly": "temperature_2m,rain",
    "timezone": "auto"
}

responses = openmeteo.weather_api(url, params=params)
response = responses[0]
hourly = response.Hourly()

hourly_data = {
    "date": pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
        end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=hourly.Interval()),
        inclusive="left"
    ),
    "Température (°C)": hourly.Variables(0).ValuesAsNumpy(),
    "Pluie (mm)": hourly.Variables(1).ValuesAsNumpy()
}

df = pd.DataFrame(data=hourly_data)

print_section("Aperçu des données météo")
pd.set_option("display.width", 1000)
df_display = df.copy()
df_display["date"] = df_display["date"].dt.strftime('%Y-%m-%d %H:%M')
print(df_display.head(10).to_string(index=False))

print_section("Visualisation graphique")
df.set_index("date", inplace=True)
fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(12, 6), sharex=True)

df["Température (°C)"].plot(ax=axes[0], color='tomato', lw=1.5)
axes[0].set_title(f"Température à {location_name}")
axes[0].set_ylabel("°C")
axes[0].grid(True)

df["Pluie (mm)"].plot(ax=axes[1], color='dodgerblue', lw=1.5)
axes[1].set_title(f"Précipitations à {location_name}")
axes[1].set_ylabel("mm")
axes[1].grid(True)

axes[1].tick_params(labelbottom=False, bottom=False)

plt.tight_layout()
plt.show()