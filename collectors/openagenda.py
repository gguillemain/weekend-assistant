"""
Module de collecte des événements via l'API OpenAgenda.
Agenda mutualisé pour les événements locaux en Alsace et régions voisines.
"""

import requests
from datetime import date, datetime
from typing import Dict, List, Optional

import config

# Configuration API
BASE_URL = "https://api.openagenda.com/v2"

# Agendas à suivre (IDs OpenAgenda)
AGENDAS = {
    # France - Alsace
    "Haut-Rhin": 5882837,        # Haut-Rhin Tourisme
    "Alsace": 26674538,          # Visit Alsace
    "Mulhouse": 73920981,        # Ville de Mulhouse
    "Colmar": 41839567,          # Ville de Colmar
}

# Distances depuis Guebwiller
CITY_DISTANCES = getattr(config, "CITY_DISTANCES", {})


def _get_distance(city: str) -> float:
    """Retourne la distance depuis Guebwiller pour une ville."""
    if not city:
        return 100.0
    city_lower = city.lower().strip()
    for known_city, dist in CITY_DISTANCES.items():
        if known_city.lower() in city_lower or city_lower in known_city.lower():
            return float(dist)
    # Estimations
    estimates = {
        "guebwiller": 0, "mulhouse": 25, "colmar": 25, "strasbourg": 100,
        "basel": 45, "bâle": 45, "freiburg": 50, "belfort": 55,
    }
    for name, dist in estimates.items():
        if name in city_lower:
            return float(dist)
    return 80.0


def _detect_category(title: str, tags: List[str]) -> str:
    """Détecte la catégorie d'un événement."""
    text = f"{title} {' '.join(tags)}".lower()

    categories = {
        "concert": ["concert", "musique", "live", "jazz", "rock", "classique", "orchestre"],
        "expo": ["exposition", "expo", "galerie", "musée", "vernissage", "art"],
        "spectacle": ["spectacle", "théâtre", "danse", "cirque", "humour", "comédie"],
        "festival": ["festival", "fête", "fest", "carnaval"],
        "marché": ["marché", "brocante", "vide-grenier", "artisanat"],
        "patrimoine": ["patrimoine", "visite", "château", "église", "historique", "journées"],
        "nature": ["nature", "balade", "randonnée", "jardin", "parc"],
        "gastronomie": ["gastronomie", "vin", "dégustation", "cuisine", "food"],
        "sport": ["sport", "course", "vélo", "trail", "marathon"],
        "enfants": ["enfants", "famille", "jeune public", "atelier créatif"],
    }

    for category, keywords in categories.items():
        for kw in keywords:
            if kw in text:
                return category

    return "autre"


def _calculate_surprise_score(
    category: str,
    distance_km: float,
    price: str,
    tags: List[str],
    period_start: date,
    period_end: date,
    event_start: Optional[date],
    event_end: Optional[date]
) -> float:
    """Calcule le score de surprise pour un événement."""
    score = 0.0

    # Catégorie NON habituelle (+0.4)
    usual = ["cinema", "expo", "concert", "rando"]
    if category not in usual:
        score += 0.4

    # Distance entre 30 et 150km (+0.2)
    if 30 <= distance_km <= 150:
        score += 0.2

    # Prix gratuit (+0.2)
    if price == "Gratuit":
        score += 0.2

    # Tags intéressants (+0.1)
    interesting_tags = ["insolite", "découverte", "secret", "original", "unique"]
    if any(tag.lower() in interesting_tags for tag in tags):
        score += 0.1

    # Dates couvertes (+0.1)
    if event_start and event_end:
        if event_start <= period_end and event_end >= period_start:
            score += 0.1
    elif event_start:
        if period_start <= event_start <= period_end:
            score += 0.1

    return min(score, 1.0)


def get_openagenda_events(period: Dict, verbose: bool = False) -> List[Dict]:
    """
    Récupère les événements OpenAgenda pour une période.

    Args:
        period: Dict avec start, end (date ou str YYYY-MM-DD)
        verbose: Si True, affiche les détails

    Returns:
        Liste d'événements triée par surprise_score
    """
    start_date = period.get("start")
    end_date = period.get("end")

    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    all_events = []
    stats = {}

    # Formatage des dates pour l'API
    from_date = start_date.strftime("%Y-%m-%d")
    to_date = end_date.strftime("%Y-%m-%d")

    for agenda_name, agenda_uid in AGENDAS.items():
        try:
            # Appel API OpenAgenda (sans clé API pour la lecture)
            url = f"{BASE_URL}/agendas/{agenda_uid}/events"
            params = {
                "from": from_date,
                "to": to_date,
                "size": 50,
                "sort": "timings.asc",
            }

            resp = requests.get(url, params=params, timeout=15)

            if resp.status_code == 200:
                data = resp.json()
                events = data.get("events", [])
                stats[agenda_name] = len(events)

                if verbose:
                    print(f"  OpenAgenda {agenda_name}: {len(events)} events")

                for event_data in events:
                    # Extraire les infos
                    title = event_data.get("title", {})
                    title = title.get("fr") or title.get("en") or str(title) if isinstance(title, dict) else str(title)

                    description = event_data.get("description", {})
                    description = description.get("fr") or description.get("en") or "" if isinstance(description, dict) else str(description)

                    location = event_data.get("location", {})
                    city = location.get("city", "")
                    address = location.get("address", "")

                    # Tags
                    keywords = event_data.get("keywords", {})
                    tags = keywords.get("fr", []) if isinstance(keywords, dict) else []

                    # Dates
                    timings = event_data.get("timings", [])
                    event_start = None
                    event_end = None
                    if timings:
                        first_timing = timings[0]
                        event_start_str = first_timing.get("begin", "")[:10]
                        if event_start_str:
                            event_start = datetime.strptime(event_start_str, "%Y-%m-%d").date()
                        last_timing = timings[-1]
                        event_end_str = last_timing.get("end", "")[:10]
                        if event_end_str:
                            event_end = datetime.strptime(event_end_str, "%Y-%m-%d").date()

                    # Prix
                    conditions = event_data.get("conditions", {})
                    price_info = conditions.get("fr") or conditions.get("en") or ""
                    if isinstance(conditions, dict):
                        price_info = conditions.get("fr", "") or conditions.get("en", "")
                    else:
                        price_info = str(conditions) if conditions else ""

                    if "gratuit" in price_info.lower() or event_data.get("registration", []):
                        price = "Gratuit"
                    elif price_info:
                        price = price_info[:50]
                    else:
                        price = "NC"

                    # Catégorie
                    category = _detect_category(title, tags)

                    # Distance
                    distance_km = _get_distance(city)

                    # URL
                    slug = event_data.get("slug", "")
                    event_url = f"https://openagenda.com/agendas/{agenda_uid}/events/{slug}" if slug else ""

                    event = {
                        "title": title,
                        "category": category,
                        "date_start": event_start,
                        "date_end": event_end,
                        "city": city,
                        "address": address,
                        "distance_km": distance_km,
                        "price": price,
                        "description": description[:300] if description else "",
                        "tags": tags,
                        "url": event_url,
                        "source": f"OpenAgenda {agenda_name}",
                        "surprise_score": 0.0
                    }

                    all_events.append(event)

            else:
                if verbose:
                    print(f"  OpenAgenda {agenda_name}: HTTP {resp.status_code}")
                stats[agenda_name] = 0

        except Exception as e:
            if verbose:
                print(f"  OpenAgenda {agenda_name}: ERREUR — {e}")
            stats[agenda_name] = 0

    # Déduplication par titre
    seen = set()
    unique_events = []
    for event in all_events:
        key = event["title"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique_events.append(event)

    # Calculer surprise_score
    for event in unique_events:
        event["surprise_score"] = _calculate_surprise_score(
            event["category"],
            event["distance_km"],
            event["price"],
            event.get("tags", []),
            start_date,
            end_date,
            event["date_start"],
            event["date_end"]
        )

    # Trier par surprise_score décroissant
    unique_events.sort(key=lambda x: -x["surprise_score"])

    if verbose:
        print(f"\n  OpenAgenda total: {len(unique_events)} événements uniques")
        print(f"  Stats: {stats}")

    return unique_events


def format_openagenda_context(events: List[Dict]) -> str:
    """Formate les événements OpenAgenda pour le contexte Claude."""
    if not events:
        return ""

    top_events = events[:3]
    lines = ["Événements OpenAgenda :"]

    for event in top_events:
        # Gérer date_start qui peut être date, str (depuis cache JSON) ou None
        date_start = event["date_start"]
        if date_start:
            if isinstance(date_start, str):
                try:
                    from datetime import datetime, date
                    date_obj = datetime.strptime(date_start, "%Y-%m-%d").date()
                    date_str = date_obj.strftime("%d/%m")
                except ValueError:
                    date_str = "Date NC"
            elif isinstance(date_start, date):
                date_str = date_start.strftime("%d/%m")
            else:
                date_str = "Date NC"
        else:
            date_str = "Date NC"

        price_str = f" | {event['price']}" if event["price"] != "NC" else ""

        lines.append(f"- [{event['category'].upper()}] {event['title']}")
        lines.append(f"  {event['city']} ({event['distance_km']:.0f}km) | {date_str}{price_str}")

    return "\n".join(lines)
