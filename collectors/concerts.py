"""
Module de collecte des concerts via Ticketmaster API et RSS des salles locales.
"""

import requests
from datetime import date, datetime
from typing import Dict, List, Optional
from math import radians, sin, cos, sqrt, atan2

import config
from collectors import rss_reader
from engine.cache import cache_get, cache_set, CACHE_TTL

# Session HTTP réutilisable (connection pooling)
_session = requests.Session()


# Coordonnées de base (Guebwiller)
BASE_LAT = config.BASE_LOCATION["lat"]
BASE_LON = config.BASE_LOCATION["lon"]

# API Ticketmaster
TICKETMASTER_BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"

# RSS des salles locales (complément Ticketmaster)
VENUE_RSS = {
    "La Laiterie": "https://laiterie.artefact.org/agenda/feed",
    "La Poudrière": "https://www.la-poudriere.com/agenda/feed",
    "La Filature": "https://www.lafilature.org/feed/",
    "Kaserne Basel": "https://kaserne-basel.ch/de/feed",
}

# Coordonnées des salles connues (pour calcul distance)
VENUE_COORDS = {
    "La Laiterie": (48.5734, 7.7521),  # Strasbourg
    "La Poudrière": (47.6333, 6.8500),  # Belfort
    "La Filature": (47.7508, 7.3359),  # Mulhouse
    "Kaserne Basel": (47.5596, 7.5886),  # Bâle
    "Parc Expo Mulhouse": (47.7508, 7.3359),  # Mulhouse
}


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcule la distance en km entre deux points GPS."""
    R = 6371  # Rayon de la Terre en km

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c


def _calculate_profile_match(
    artist: str,
    genre: str,
    venue: str,
    profile: Dict
) -> float:
    """
    Calcule le score de correspondance avec le profil utilisateur.

    Args:
        artist: Nom de l'artiste
        genre: Genre musical
        venue: Nom de la salle
        profile: Dict du profil utilisateur

    Returns:
        Score entre 0 et 1
    """
    score = 0.0

    artist_lower = artist.lower() if artist else ""
    genre_lower = genre.lower() if genre else ""
    venue_lower = venue.lower() if venue else ""

    # Match artiste favori (+0.5)
    favorite_artists = profile.get("music_artists", [])
    for fav in favorite_artists:
        if fav.lower() in artist_lower or artist_lower in fav.lower():
            score += 0.5
            break

    # Match genre (+0.3)
    favorite_genres = profile.get("music_genres", [])
    for fav_genre in favorite_genres:
        if fav_genre.lower() in genre_lower:
            score += 0.3
            break

    # Match salle connue (+0.2)
    favorite_venues = profile.get("music_venues", [])
    for fav_venue in favorite_venues:
        if fav_venue.lower() in venue_lower or venue_lower in fav_venue.lower():
            score += 0.2
            break

    return min(score, 1.0)


def _fetch_ticketmaster(
    period: Dict,
    country_code: str
) -> List[Dict]:
    """
    Récupère les concerts depuis Ticketmaster pour un pays.

    Args:
        period: Dict avec start, end
        country_code: FR, CH ou DE

    Returns:
        Liste de concerts bruts
    """
    if not config.TICKETMASTER_API_KEY:
        return []

    start_date = period.get("start")
    end_date = period.get("end")

    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    params = {
        "apikey": config.TICKETMASTER_API_KEY,
        "countryCode": country_code,
        "latlong": f"{BASE_LAT},{BASE_LON}",
        "radius": 180,
        "unit": "km",
        "classificationName": "music",
        "startDateTime": f"{start_date.isoformat()}T00:00:00Z",
        "endDateTime": f"{end_date.isoformat()}T23:59:59Z",
        "size": 50,
        "locale": "fr-fr,fr-ch,de-de",
    }

    try:
        response = _session.get(
            TICKETMASTER_BASE_URL,
            params=params,
            timeout=15
        )
        response.raise_for_status()
        data = response.json()

        events = data.get("_embedded", {}).get("events", [])
        return events

    except requests.exceptions.RequestException as e:
        print(f"  Erreur Ticketmaster {country_code}: {e}")
        return []


def _parse_ticketmaster_event(event: Dict) -> Optional[Dict]:
    """Parse un événement Ticketmaster en format standard."""
    try:
        # Titre et artiste
        title = event.get("name", "")
        artist = title  # Par défaut, le titre est l'artiste

        # Extraire l'artiste des attractions si disponible
        attractions = event.get("_embedded", {}).get("attractions", [])
        if attractions:
            artist = attractions[0].get("name", title)

        # Venue
        venues = event.get("_embedded", {}).get("venues", [])
        venue_data = venues[0] if venues else {}
        venue_name = venue_data.get("name", "")
        city = venue_data.get("city", {}).get("name", "")
        country = venue_data.get("country", {}).get("name", "")

        # Coordonnées et distance
        location = venue_data.get("location", {})
        lat = float(location.get("latitude", 0))
        lon = float(location.get("longitude", 0))
        distance_km = _haversine(BASE_LAT, BASE_LON, lat, lon) if lat and lon else 0

        # Date et heure
        dates = event.get("dates", {})
        start = dates.get("start", {})
        date_str = start.get("localDate", "")
        time_str = start.get("localTime", "")

        event_date = None
        if date_str:
            event_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        event_time = "NC"
        if time_str:
            event_time = time_str[:5]  # "20:30:00" -> "20:30"

        # Prix
        price_ranges = event.get("priceRanges", [])
        price_min = None
        price_max = None
        if price_ranges:
            price_min = price_ranges[0].get("min")
            price_max = price_ranges[0].get("max")

        # Genre
        classifications = event.get("classifications", [])
        genre = ""
        if classifications:
            genre = classifications[0].get("genre", {}).get("name", "")
            if not genre:
                genre = classifications[0].get("segment", {}).get("name", "")

        # URL
        url = event.get("url", "")

        return {
            "title": title,
            "artist": artist,
            "venue": venue_name,
            "city": city,
            "country": country,
            "date": event_date,
            "time": event_time,
            "distance_km": round(distance_km, 1),
            "price_min": price_min,
            "price_max": price_max,
            "url": url,
            "genre": genre,
            "source": "ticketmaster",
            "profile_match": 0.0,
        }

    except Exception as e:
        return None


def _fetch_rss_concerts(period: Dict, verbose: bool = False) -> List[Dict]:
    """
    Récupère les concerts depuis les flux RSS des salles locales.

    Args:
        period: Dict avec start, end
        verbose: Si True, affiche les status HTTP

    Returns:
        Liste de concerts
    """
    start_date = period.get("start")
    end_date = period.get("end")

    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    concerts = []

    for venue_name, rss_url in VENUE_RSS.items():
        # Log HTTP status si verbose
        if verbose:
            try:
                resp = requests.head(rss_url, timeout=5, allow_redirects=True)
                print(f"  RSS {venue_name}: HTTP {resp.status_code} — {rss_url}")
            except requests.exceptions.RequestException as e:
                print(f"  RSS {venue_name}: ERREUR — {e}")

        items = rss_reader.fetch_rss(rss_url)

        for item in items:
            # Filtrer par date si disponible
            pub_date = item.get("published")
            if pub_date:
                item_date = pub_date.date() if isinstance(pub_date, datetime) else pub_date
                # Les RSS de salles publient souvent la date de l'événement
                # On garde les items récents
                if item_date < start_date:
                    continue

            # Essayer d'extraire l'artiste du titre
            title = item.get("title", "")
            artist = title  # Par défaut

            # Coordonnées de la salle
            coords = VENUE_COORDS.get(venue_name, (BASE_LAT, BASE_LON))
            distance_km = _haversine(BASE_LAT, BASE_LON, coords[0], coords[1])

            # Extraire la ville du nom de la salle
            city = ""
            if "Strasbourg" in venue_name or "Laiterie" in venue_name:
                city = "Strasbourg"
            elif "Belfort" in venue_name or "Poudrière" in venue_name:
                city = "Belfort"
            elif "Mulhouse" in venue_name or "Filature" in venue_name:
                city = "Mulhouse"
            elif "Basel" in venue_name or "Kaserne" in venue_name:
                city = "Bâle"

            concerts.append({
                "title": title,
                "artist": artist,
                "venue": venue_name,
                "city": city,
                "country": "France" if city != "Bâle" else "Suisse",
                "date": pub_date.date() if isinstance(pub_date, datetime) else None,
                "time": "NC",
                "distance_km": round(distance_km, 1),
                "price_min": None,
                "price_max": None,
                "url": item.get("link", ""),
                "genre": "",
                "source": "rss",
                "profile_match": 0.0,
            })

    return concerts


def get_concerts(period: Dict, profile: Dict, verbose: bool = False) -> List[Dict]:
    """
    Récupère tous les concerts pour une période.

    Args:
        period: Dict avec start, end
        profile: Dict du profil utilisateur
        verbose: Si True, affiche les détails HTTP

    Returns:
        Liste de concerts triée par profile_match
    """
    start_date = period.get("start")
    end_date = period.get("end")

    # Clé de cache
    cache_key = f"concerts_{start_date}_{end_date}"

    # Vérifier le cache
    cached = cache_get(cache_key)
    if cached:
        print("  Concerts : CACHE HIT")
        # Recalculer profile_match avec le profil actuel
        for concert in cached:
            concert["profile_match"] = _calculate_profile_match(
                concert["artist"],
                concert["genre"],
                concert["venue"],
                profile
            )
        cached.sort(key=lambda x: (-x["profile_match"], x["distance_km"]))
        return cached

    print("  Concerts : CACHE MISS → appel API")

    all_concerts = []
    stats = {"ticketmaster_fr": 0, "ticketmaster_ch": 0, "ticketmaster_de": 0, "rss": 0}

    # Ticketmaster France
    events_fr = _fetch_ticketmaster(period, "FR")
    for event in events_fr:
        concert = _parse_ticketmaster_event(event)
        if concert:
            all_concerts.append(concert)
            stats["ticketmaster_fr"] += 1

    # Ticketmaster Suisse
    events_ch = _fetch_ticketmaster(period, "CH")
    for event in events_ch:
        concert = _parse_ticketmaster_event(event)
        if concert:
            all_concerts.append(concert)
            stats["ticketmaster_ch"] += 1

    # Ticketmaster Allemagne
    events_de = _fetch_ticketmaster(period, "DE")
    for event in events_de:
        concert = _parse_ticketmaster_event(event)
        if concert:
            all_concerts.append(concert)
            stats["ticketmaster_de"] += 1

    # RSS salles locales
    rss_concerts = _fetch_rss_concerts(period, verbose=verbose)
    all_concerts.extend(rss_concerts)
    stats["rss"] = len(rss_concerts)

    # Déduplication : même titre (normalisé) + venue → garder celui avec heure définie
    # Normaliser le titre : prendre la partie avant " | " (ignore variantes billets)
    def normalize_title(title: str) -> str:
        return title.split(" | ")[0].lower().strip()

    # Trier pour que les entrées avec heure passent avant "NC"
    all_concerts.sort(key=lambda c: (normalize_title(c["title"]), c["venue"].lower(), c["time"] == "NC"))

    seen = set()
    unique_concerts = []
    for concert in all_concerts:
        key = (normalize_title(concert["title"]), concert["venue"].lower())
        if key not in seen:
            seen.add(key)
            unique_concerts.append(concert)

    # Filtrer les concerts déjà vus (1 an)
    from engine.profile import get_seen_items_normalized, normalize_for_matching

    seen_concerts = get_seen_items_normalized('concerts', days=365)

    history_filtered = []
    for concert in unique_concerts:
        concert_normalized = normalize_for_matching(concert["artist"])
        concert_venue_key = f"{concert_normalized} {normalize_for_matching(concert['venue'])}"

        if concert_normalized not in seen_concerts and concert_venue_key not in seen_concerts:
            history_filtered.append(concert)
        elif verbose:
            print(f"  [SKIP] Concert déjà vu : {concert['artist']} @ {concert['venue']}")

    unique_concerts = history_filtered

    # Calculer profile_match pour chaque concert
    for concert in unique_concerts:
        concert["profile_match"] = _calculate_profile_match(
            concert["artist"],
            concert["genre"],
            concert["venue"],
            profile
        )

    # Trier par profile_match décroissant
    unique_concerts.sort(key=lambda x: (-x["profile_match"], x["distance_km"]))

    # Mettre en cache
    cache_set(cache_key, unique_concerts, CACHE_TTL.get("concerts", 360))

    return unique_concerts


def format_concerts_context(concerts: List[Dict]) -> str:
    """Formate les concerts pour le contexte Claude."""
    if not concerts:
        return "Concerts : aucun concert trouvé pour cette période."

    top_concerts = concerts[:5]
    lines = ["Concerts à venir sur la période :"]

    for concert in top_concerts:
        # Gérer date qui peut être date, str (depuis cache JSON) ou None
        concert_date = concert["date"]
        if concert_date:
            if isinstance(concert_date, str):
                try:
                    date_obj = datetime.strptime(concert_date, "%Y-%m-%d").date()
                    date_str = date_obj.strftime("%d/%m")
                except ValueError:
                    date_str = "Date NC"
            elif isinstance(concert_date, date):
                date_str = concert_date.strftime("%d/%m")
            else:
                date_str = "Date NC"
        else:
            date_str = "Date NC"

        price_str = ""
        if concert["price_min"]:
            price_str = f" | à partir de {concert['price_min']:.0f}€"

        match_str = f"Match profil : {concert['profile_match']:.1f}"

        lines.append(f"- {concert['artist']} — {concert['venue']} ({concert['city']}, {concert['distance_km']}km)")
        lines.append(f"  {date_str} à {concert['time']}{price_str}")
        lines.append(f"  {match_str}")

    return "\n".join(lines)


def display_concerts(concerts: List[Dict]) -> None:
    """Affiche les concerts dans le terminal (pour debug)."""
    print(f"\n{'='*50}")
    print("CONCERTS")
    print(f"{'='*50}")

    if not concerts:
        print("Aucun concert trouvé")
        return

    # Stats par source
    sources = {}
    for c in concerts:
        src = c.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1

    print(f"\nSources : {sources}")
    print(f"Total : {len(concerts)} concerts")

    # Top 5 par profile_match
    print(f"\n{'—'*50}")
    print("TOP 5 par correspondance profil")
    print(f"{'—'*50}")

    for i, concert in enumerate(concerts[:5], 1):
        # Gérer date qui peut être date, str (depuis cache JSON) ou None
        concert_date = concert["date"]
        if concert_date:
            if isinstance(concert_date, str):
                try:
                    date_obj = datetime.strptime(concert_date, "%Y-%m-%d").date()
                    date_str = date_obj.strftime("%d/%m/%Y")
                except ValueError:
                    date_str = "Date NC"
            elif isinstance(concert_date, date):
                date_str = concert_date.strftime("%d/%m/%Y")
            else:
                date_str = "Date NC"
        else:
            date_str = "Date NC"

        print(f"\n{i}. {concert['artist']}")
        print(f"   Salle : {concert['venue']} ({concert['city']})")
        print(f"   Date : {date_str} à {concert['time']}")
        print(f"   Distance : {concert['distance_km']} km")
        print(f"   Match profil : {concert['profile_match']:.2f}")

    # Exemple avec profile_match > 0
    matches = [c for c in concerts if c["profile_match"] > 0]
    if matches:
        print(f"\n{'—'*50}")
        print(f"Concerts avec correspondance profil > 0 : {len(matches)}")
        print(f"{'—'*50}")
        for c in matches[:3]:
            print(f"  - {c['artist']} (match: {c['profile_match']:.2f})")

    print(f"\n{'='*50}\n")
