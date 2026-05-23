import requests
from datetime import datetime, date
from typing import Dict, List, Optional
import config


WEEKDAY_LABELS = {
    0: "Lundi",
    1: "Mardi",
    2: "Mercredi",
    3: "Jeudi",
    4: "Vendredi",
    5: "Samedi",
    6: "Dimanche"
}


def get_weather_forecast(period: Dict) -> Dict:
    """
    Récupère les prévisions météo pour une période donnée.

    Args:
        period: Dictionnaire issu de get_next_periods() avec start, end, mode, label

    Returns:
        Dict avec location, period_label, days, summary, best_day
    """
    api_key = config.OPENWEATHER_API_KEY
    lat = config.BASE_LOCATION["lat"]
    lon = config.BASE_LOCATION["lon"]
    city = config.BASE_LOCATION["city"]

    # Résultat par défaut en cas d'erreur
    error_result = {
        "location": city,
        "period_label": period.get("label", ""),
        "days": [],
        "summary": "Impossible de récupérer la météo",
        "best_day": None,
        "error": None
    }

    if not api_key:
        error_result["error"] = "Clé API OpenWeatherMap non configurée"
        return error_result

    # Appel API OpenWeatherMap forecast
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": "metric",
        "lang": "fr"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.Timeout:
        error_result["error"] = "Timeout lors de l'appel API"
        return error_result
    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            error_result["error"] = "Clé API invalide"
        elif response.status_code == 429:
            error_result["error"] = "Limite d'appels API atteinte"
        else:
            error_result["error"] = f"Erreur HTTP {response.status_code}"
        return error_result
    except requests.exceptions.RequestException as e:
        error_result["error"] = f"Erreur réseau: {str(e)}"
        return error_result

    # Extraire les prévisions pour la période
    period_start = period["start"]
    period_end = period["end"]

    # Grouper les prévisions par jour
    daily_forecasts = _group_forecasts_by_day(data["list"], period_start, period_end)

    if not daily_forecasts:
        error_result["error"] = "Aucune prévision disponible pour cette période"
        return error_result

    # Construire les données par jour
    days = []
    best_day = None
    best_score = -1

    for day_date, forecasts in sorted(daily_forecasts.items()):
        day_data = _process_day_forecasts(day_date, forecasts)
        days.append(day_data)

        # Calculer le meilleur jour
        score = _calculate_day_score(day_data)
        if score > best_score:
            best_score = score
            best_day = day_data["label"]

    # Déterminer si tous les jours sont équivalents
    if len(days) > 1:
        scores = [_calculate_day_score(d) for d in days]
        if max(scores) - min(scores) < 10:
            best_day = "Tous"

    # Générer le résumé
    summary = _generate_summary(days)

    return {
        "location": city,
        "period_label": period.get("label", ""),
        "days": days,
        "summary": summary,
        "best_day": best_day
    }


def _group_forecasts_by_day(forecasts: List[Dict], start: date, end: date) -> Dict[date, List[Dict]]:
    """Groupe les prévisions par jour pour la période donnée."""
    daily = {}

    for forecast in forecasts:
        dt = datetime.fromtimestamp(forecast["dt"])
        forecast_date = dt.date()

        if start <= forecast_date <= end:
            if forecast_date not in daily:
                daily[forecast_date] = []
            daily[forecast_date].append(forecast)

    return daily


def _process_day_forecasts(day_date: date, forecasts: List[Dict]) -> Dict:
    """Traite les prévisions d'une journée pour extraire les données agrégées."""
    temps = [f["main"]["temp"] for f in forecasts]
    temp_min = min(temps)
    temp_max = max(temps)

    # Précipitations cumulées
    rain_mm = 0.0
    for f in forecasts:
        if "rain" in f and "3h" in f["rain"]:
            rain_mm += f["rain"]["3h"]

    # Description et icône du milieu de journée (ou premier disponible)
    midday_forecast = None
    for f in forecasts:
        dt = datetime.fromtimestamp(f["dt"])
        if 11 <= dt.hour <= 15:
            midday_forecast = f
            break
    if not midday_forecast:
        midday_forecast = forecasts[0]

    description = midday_forecast["weather"][0]["description"].capitalize()
    icon = midday_forecast["weather"][0]["icon"]

    # Conditions favorables pour sortir : pas de pluie forte et > 12°C
    suitable_outdoor = rain_mm < 5.0 and temp_max > 12.0

    return {
        "date": day_date.isoformat(),
        "label": WEEKDAY_LABELS[day_date.weekday()],
        "temp_min": round(temp_min, 1),
        "temp_max": round(temp_max, 1),
        "description": description,
        "icon": icon,
        "rain_mm": round(rain_mm, 1),
        "suitable_outdoor": suitable_outdoor
    }


def _calculate_day_score(day_data: Dict) -> float:
    """Calcule un score de qualité pour un jour (plus élevé = meilleur)."""
    score = 50.0

    # Température idéale autour de 20-22°C
    temp_avg = (day_data["temp_min"] + day_data["temp_max"]) / 2
    score += max(0, 30 - abs(temp_avg - 21) * 2)

    # Pénalité pour la pluie
    score -= day_data["rain_mm"] * 5

    # Bonus si suitable_outdoor
    if day_data["suitable_outdoor"]:
        score += 20

    return score


def _generate_summary(days: List[Dict]) -> str:
    """Génère un résumé en une phrase de la météo."""
    if not days:
        return "Aucune donnée disponible"

    all_suitable = all(d["suitable_outdoor"] for d in days)
    any_suitable = any(d["suitable_outdoor"] for d in days)
    total_rain = sum(d["rain_mm"] for d in days)
    avg_temp = sum((d["temp_min"] + d["temp_max"]) / 2 for d in days) / len(days)

    if all_suitable and total_rain < 2:
        if avg_temp > 20:
            return "Excellent temps prévu, idéal pour les activités en plein air"
        elif avg_temp > 15:
            return "Beau temps, conditions agréables pour sortir"
        else:
            return "Temps sec mais frais, prévoir une veste"
    elif any_suitable:
        suitable_days = [d["label"] for d in days if d["suitable_outdoor"]]
        return f"Météo mitigée, privilégier {', '.join(suitable_days)}"
    else:
        if total_rain > 10:
            return "Temps pluvieux prévu, activités intérieures recommandées"
        elif avg_temp < 10:
            return "Temps froid, prévoir des activités adaptées"
        else:
            return "Conditions peu favorables aux sorties"
