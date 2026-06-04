"""
Module de collecte d'itinéraires vélo — Scraping alsaceavelo.fr
VAE sur voies sécurisées, distance idéale 45-60km.
"""

import re
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional

import config
from engine.cache import cache_get, cache_set, CACHE_TTL


# =============================================================================
# CONFIGURATION
# =============================================================================

# URL avec filtre boucles locales (itinéraires jour)
ALSACEAVELO_URL = "https://www.alsaceavelo.fr/itineraires/?fwp_types=boucles-locales"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# Types d'itinéraires acceptés
ACCEPTED_TYPES = [
    "boucle régionale",
    "boucle locale",
    "véloroute du vignoble",
    "eurovelo 15",
    "eurovelo",
    "véloroute",
]

# Mots-clés à exclure (VTT, Gravel)
EXCLUDED_KEYWORDS = ["vtt", "gravel", "mountainbike", "mountain bike"]


# =============================================================================
# LISTE STATIQUE — ITINÉRAIRES LOCAUX CONNUS
# =============================================================================

LOCAL_BIKE_ROUTES = [
    {
        "title": "Voie verte Vallée de la Doller",
        "start_city": "Burnhaupt-le-Bas",
        "end_city": "Sentheim",
        "distance_km": 18,      # aller-retour ~36km
        "elevation_gain": 40,
        "terrain": "vallée",
        "surface": "voie verte",
        "loop": False,
        "difficulty": "Familial",
        "url": "https://www.alsaceavelo.fr"
    },
    {
        "title": "Véloroute du vignoble — Guebwiller à Colmar",
        "start_city": "Guebwiller",
        "end_city": "Colmar",
        "distance_km": 25,      # aller-retour ~50km
        "elevation_gain": 80,
        "terrain": "vignoble",
        "surface": "cyclable",
        "loop": False,
        "difficulty": "Familial",
        "url": "https://www.alsaceavelo.fr/itineraires/velo-route-du-vignoble"
    },
    {
        "title": "EuroVelo 15 — Neuf-Brisach à Bâle",
        "start_city": "Neuf-Brisach",
        "distance_km": 62,
        "elevation_gain": 30,
        "terrain": "rhin",
        "surface": "cyclable",
        "loop": False,
        "difficulty": "Familial",
        "url": "https://www.alsaceavelo.fr/itineraires/eurovelo-15"
    },
    {
        "title": "Boucle des Trois Châteaux — Eguisheim",
        "start_city": "Eguisheim",
        "distance_km": 35,
        "elevation_gain": 150,
        "terrain": "vignoble",
        "surface": "mixte",
        "loop": True,
        "difficulty": "Intermédiaire",
        "url": "https://www.alsaceavelo.fr"
    },
    {
        "title": "Canal du Rhône au Rhin — Mulhouse à Niffer",
        "start_city": "Mulhouse",
        "distance_km": 40,
        "elevation_gain": 20,
        "terrain": "rhin",
        "surface": "voie verte",
        "loop": False,
        "difficulty": "Familial",
        "url": "https://www.alsaceavelo.fr"
    }
]


# =============================================================================
# CONVERSION LISTE STATIQUE
# =============================================================================

def _convert_local_route(route: Dict) -> Dict:
    """Convertit une entrée LOCAL_BIKE_ROUTES au format complet."""
    title = route["title"]
    distance_km = route["distance_km"]

    # Pour les aller-retours, doubler la distance
    if not route.get("loop", False) and "aller" not in title.lower():
        # Aller-retour implicite
        distance_km = distance_km * 2 if distance_km < 30 else distance_km

    # Ville de départ
    start_city = route.get("start_city", "Alsace")
    distance_from_home = _get_distance_from_home(start_city)

    # Durée estimée (15 km/h VAE)
    duration_h = round(distance_km / 15, 1)

    return {
        "title": title,
        "distance_km": distance_km,
        "elevation_gain": route.get("elevation_gain", 0),
        "duration_h": duration_h,
        "difficulty": route.get("difficulty", "Familial"),
        "start_city": start_city,
        "distance_from_home": distance_from_home,
        "terrain": route.get("terrain", "mixte"),
        "surface": route.get("surface", "cyclable"),
        "loop": route.get("loop", False),
        "url": route.get("url", "https://www.alsaceavelo.fr"),
        "ride_type": "Local connu",
        "weather_score": 0.0,
        "bike_score": 0.0,
        "source": "local",
    }


# =============================================================================
# SCRAPING ALSACEAVELO.FR
# =============================================================================

def _scrape_alsaceavelo() -> List[Dict]:
    """
    Scrape les itinéraires vélo depuis alsaceavelo.fr.
    Filtre les VTT/Gravel, garde uniquement les parcours route/cyclable.
    """
    print("  Vélo : scraping alsaceavelo.fr...")

    try:
        response = requests.get(ALSACEAVELO_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  ⚠ Erreur requête alsaceavelo.fr : {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    rides = []

    # Sélecteur spécifique pour les cartes d'itinéraires alsaceavelo
    cards = soup.select("a.bloc-card-lei-itineraire")

    if not cards:
        # Fallback : chercher tous les liens vers itinéraires
        cards = soup.select("a[href*='/itineraire'], a[href*='403']")

    for card in cards:
        ride = _parse_ride_card(card)
        if ride:
            rides.append(ride)

    print(f"  Vélo : {len(rides)} itinéraires trouvés")
    return rides


def _parse_ride_card(card) -> Optional[Dict]:
    """Parse une carte d'itinéraire alsaceavelo."""
    try:
        text = card.get_text()

        # Titre - extraire des lignes de texte (2ème ligne typiquement)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        title = lines[1] if len(lines) > 1 else lines[0] if lines else ""

        if not title or len(title) < 5:
            return None

        # Vérifier exclusions VTT/Gravel
        title_lower = title.lower()
        if any(kw in title_lower for kw in EXCLUDED_KEYWORDS):
            print(f"  [SKIP] VTT/Gravel exclu : {title}")
            return None

        # URL
        url = card.get("href", "")
        if url and not url.startswith("http"):
            url = f"https://www.alsaceavelo.fr{url}"

        # Distance (chercher NNN km)
        distance_km = _extract_distance(card)

        # Dénivelé (chercher NNN m mais pas NNN km)
        elevation_gain = _extract_elevation(card)

        # Filtrer les itinéraires trop longs ou courts
        if distance_km < 20 or distance_km > 100:
            return None

        # Ville de départ (dernière partie du titre souvent)
        start_city = _extract_start_city(card, title)

        # Calculer distance depuis Guebwiller
        distance_from_home = _get_distance_from_home(start_city)

        # Déterminer le terrain
        terrain = _determine_terrain(title)

        # Déterminer la surface
        surface = "cyclable" if "eurovelo" in title_lower or "véloroute" in title_lower else "mixte"

        # Boucle ? (la plupart des "boucles locales" sont des boucles)
        loop = "boucle" in title_lower or "tour" in title_lower or "circuit" in title_lower or "BR" in title

        # Difficulté estimée
        if elevation_gain > 500:
            difficulty = "Sportif"
        elif elevation_gain > 250:
            difficulty = "Intermédiaire"
        else:
            difficulty = "Familial"

        # Durée estimée (15 km/h en moyenne VAE)
        duration_h = round(distance_km / 15, 1) if distance_km > 0 else 0

        return {
            "title": title.strip(),
            "distance_km": distance_km,
            "elevation_gain": elevation_gain,
            "duration_h": duration_h,
            "difficulty": difficulty,
            "start_city": start_city,
            "distance_from_home": distance_from_home,
            "terrain": terrain,
            "surface": surface,
            "loop": loop,
            "url": url,
            "ride_type": "Boucle locale",
            "weather_score": 0.0,
            "bike_score": 0.0,
        }

    except Exception:
        return None


def _extract_distance(card) -> float:
    """Extrait la distance en km."""
    text = card.get_text()

    # Pattern : "45 km", "45km", "45,5 km"
    match = re.search(r'(\d+[,.]?\d*)\s*km', text, re.I)
    if match:
        dist = match.group(1).replace(",", ".")
        return float(dist)
    return 0.0


def _extract_elevation(card) -> int:
    """Extrait le dénivelé en mètres."""
    text = card.get_text()

    # Pattern : "150 m" (mais pas "150 km")
    # Chercher tous les nombres suivis de "m" mais pas "km"
    matches = re.findall(r'(\d+)\s*m(?!\s*[ik])', text)

    if matches:
        # Prendre le plus grand (probablement le dénivelé total)
        elevations = [int(m) for m in matches]
        # Filtrer les valeurs aberrantes (> 3000m peu probable)
        valid = [e for e in elevations if e < 3000]
        if valid:
            return max(valid)
    return 0


def _extract_start_city(card, title: str) -> str:
    """Extrait la ville de départ du titre ou du texte."""
    text = card.get_text().lower()
    title_lower = title.lower()

    # Chercher dans les villes favorites
    for city in config.BIKE_PREFS.get("favorite_starts", []):
        if city.lower() in text or city.lower() in title_lower:
            return city

    # Chercher dans CITY_DISTANCES
    for city in config.CITY_DISTANCES:
        if city.lower() in text or city.lower() in title_lower:
            return city

    # Extraire le dernier mot du titre (souvent la ville)
    # Ex: "Autour du Glaserberg Oltingue" -> "Oltingue"
    words = title.split()
    if words:
        last_word = words[-1].strip(".,;:")
        # Vérifier que c'est un nom propre (commence par majuscule)
        if last_word and last_word[0].isupper() and len(last_word) > 3:
            return last_word

    # Pattern "de Ville" dans le titre
    match = re.search(r'\bde\s+([A-ZÀ-Ü][a-zà-ü]+(?:-[A-Za-zà-ü]+)*)', title)
    if match:
        return match.group(1)

    return "Alsace"


def _extract_ride_type(card) -> str:
    """Extrait le type d'itinéraire."""
    # Chercher dans les tags/badges
    tags = card.select(".tag, .badge, .category, .type")
    for tag in tags:
        text = tag.get_text(strip=True).lower()
        if any(t in text for t in ACCEPTED_TYPES):
            return tag.get_text(strip=True)

    # Chercher dans le texte
    text = card.get_text().lower()
    for ride_type in ACCEPTED_TYPES:
        if ride_type in text:
            return ride_type.title()

    return ""


def _get_distance_from_home(city: str) -> float:
    """Retourne la distance depuis Guebwiller."""
    if not city:
        return 50.0

    # Chercher dans CITY_DISTANCES
    if city in config.CITY_DISTANCES:
        return float(config.CITY_DISTANCES[city])

    # Chercher avec variations
    city_lower = city.lower()
    for known_city, dist in config.CITY_DISTANCES.items():
        if known_city.lower() == city_lower:
            return float(dist)

    return 50.0  # Défaut


def _determine_terrain(title: str) -> str:
    """Détermine le type de terrain à partir du titre."""
    title_lower = title.lower()

    for terrain, keywords in config.BIKE_TERRAIN_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return terrain

    return "mixte"


# =============================================================================
# SCORING
# =============================================================================

def _calculate_bike_score(ride: Dict, weather_data: Dict = None) -> float:
    """
    Calcule le score d'un itinéraire vélo.
    Plus le score est élevé, plus l'itinéraire est recommandé.
    """
    score = 0.0

    # Weather score (30%)
    if weather_data:
        # Utiliser le meilleur jour météo
        best_day = weather_data.get("best_day_data", {})
        if best_day.get("suitable_outdoor", False):
            score += 0.30
        elif weather_data.get("days"):
            # Moyenne des jours favorables
            favorable_days = sum(1 for d in weather_data["days"] if d.get("suitable_outdoor"))
            score += (favorable_days / len(weather_data["days"])) * 0.30

    # Boucle (25%)
    if ride.get("loop", False):
        score += 0.25

    # Distance idéale 45-60km (25%)
    distance = ride.get("distance_km", 0)
    if 45 <= distance <= 60:
        score += 0.25
    elif 40 <= distance <= 65:
        score += 0.15

    # Proximité du départ (15%)
    distance_from_home = ride.get("distance_from_home", 50)
    if distance_from_home < 15:
        score += 0.15
    elif distance_from_home < 30:
        score += 0.10
    elif distance_from_home < 50:
        score += 0.05

    # Terrain vignoble bonus (10%)
    if ride.get("terrain") == "vignoble":
        score += 0.10
    elif ride.get("terrain") == "rhin":
        score += 0.05

    return round(score, 2)


def _calculate_weather_score(ride: Dict, weather_data: Dict) -> float:
    """Calcule le score météo pour une sortie vélo."""
    if not weather_data or not weather_data.get("days"):
        return 0.5

    # Le vélo nécessite du beau temps
    favorable_days = []
    for day in weather_data["days"]:
        if day.get("suitable_outdoor") and day.get("rain_mm", 0) < 1:
            # Bonus si température agréable (15-25°C)
            temp_max = day.get("temp_max", 20)
            if 15 <= temp_max <= 28:
                favorable_days.append(1.0)
            elif 10 <= temp_max <= 30:
                favorable_days.append(0.7)
            else:
                favorable_days.append(0.3)

    if favorable_days:
        return round(max(favorable_days), 2)
    return 0.0


# =============================================================================
# FONCTION PRINCIPALE
# =============================================================================

def get_cycling_suggestions(period: Dict, weather_data: Dict = None) -> List[Dict]:
    """
    Récupère les suggestions de sorties vélo pour une période donnée.

    Args:
        period: Dict avec start, end
        weather_data: Données météo (optionnel)

    Returns:
        Liste de 3 itinéraires vélo triés par bike_score
    """
    period_start = period.get("start", "")
    cache_key = "cycling_alsaceavelo"

    # Vérifier le cache (48h pour les itinéraires)
    cached = cache_get(cache_key)
    if cached:
        print("  Vélo : CACHE HIT")
        rides = cached
    else:
        print("  Vélo : CACHE MISS → scraping")
        rides = _scrape_alsaceavelo()

        if rides:
            # Cache 48h
            cache_set(cache_key, rides, CACHE_TTL.get("cycling", 2880))

    # Fusionner avec LOCAL_BIKE_ROUTES
    local_rides = [_convert_local_route(r) for r in LOCAL_BIKE_ROUTES]

    # Éviter les doublons (même titre normalisé)
    existing_titles = {r["title"].lower().strip() for r in rides}
    for local in local_rides:
        if local["title"].lower().strip() not in existing_titles:
            rides.append(local)

    print(f"  Vélo : {len(rides)} itinéraires (scraping + {len(local_rides)} locaux)")

    if not rides:
        print("  ⚠ Aucun itinéraire vélo trouvé")
        return []

    # Filtrer selon les préférences
    prefs = config.BIKE_PREFS
    filtered = []

    for ride in rides:
        # Vérifier distance
        if ride["distance_km"] < prefs.get("min_distance_km", 40):
            continue
        if ride["distance_km"] > prefs.get("max_distance_km", 65):
            continue

        # Vérifier dénivelé
        if ride["elevation_gain"] > prefs.get("max_elevation_gain_hard", 600):
            continue

        # Vérifier distance depuis domicile
        if ride["distance_from_home"] > prefs.get("max_drive_km", 80):
            continue

        filtered.append(ride)

    if not filtered:
        # Relâcher les contraintes si rien ne passe
        filtered = [r for r in rides if r["distance_km"] >= 30]

    # Calculer les scores
    for ride in filtered:
        ride["weather_score"] = _calculate_weather_score(ride, weather_data)
        ride["bike_score"] = _calculate_bike_score(ride, weather_data)

    # Déduplication avec historique utilisateur
    from engine.profile import get_seen_items_normalized, normalize_for_matching

    seen_rides = get_seen_items_normalized('cycling', days=90)

    def is_ride_seen(title: str) -> bool:
        """Vérifie si un itinéraire a été fait (matching partiel)."""
        normalized = normalize_for_matching(title)
        if normalized in seen_rides:
            return True
        for seen in seen_rides:
            if seen in normalized or normalized in seen:
                return True
        return False

    available = []
    for ride in filtered:
        if not is_ride_seen(ride["title"]):
            available.append(ride)
        else:
            print(f"  [SKIP] Vélo déjà fait : {ride['title']}")

    if not available:
        available = filtered  # Fallback si tous faits

    # Trier par bike_score décroissant
    available.sort(key=lambda r: r["bike_score"], reverse=True)

    # Sélectionner les 3 meilleurs
    selected = available[:3]

    print(f"  Vélo : {len(selected)} sélectionnés sur {len(rides)} disponibles")

    # Afficher le top 3 pour debug
    if selected:
        print("  [VÉLO] Top 3 par bike_score :")
        for i, r in enumerate(selected[:3], 1):
            print(f"    {i}. {r['title']} — {r['distance_km']}km, {r['elevation_gain']}m D+ — terrain={r['terrain']} — score={r['bike_score']}")

    return selected


def format_cycling_context(rides: List[Dict]) -> str:
    """Formate les itinéraires vélo pour le contexte Claude."""
    if not rides:
        return "Sorties vélo : aucun itinéraire disponible."

    lines = ["Sorties vélo disponibles (VAE, voies sécurisées) :"]

    for ride in rides:
        lines.append(f"- {ride['title']} — {ride['distance_km']}km, {ride['elevation_gain']}m D+")
        lines.append(f"  Départ {ride['start_city']} ({ride['distance_from_home']:.0f}km de Guebwiller)")
        lines.append(f"  Terrain : {ride['terrain']} | Durée : {ride['duration_h']}h | Score : {ride['bike_score']}")

    return "\n".join(lines)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TEST COLLECTOR CYCLING")
    print("=" * 60)

    # Test scraping
    rides = _scrape_alsaceavelo()

    print(f"\n1. Statut scraping : {'OK' if rides else 'ÉCHEC'}")
    print(f"2. Nombre d'itinéraires : {len(rides)}")

    # Vérifier exclusion VTT/Gravel
    vtt_gravel = [r for r in rides if any(kw in r["title"].lower() for kw in EXCLUDED_KEYWORDS)]
    print(f"4. VTT/Gravel exclus : {'OUI' if not vtt_gravel else 'NON - ' + str(len(vtt_gravel)) + ' trouvés'}")

    if rides:
        # Calculer les scores
        for ride in rides:
            ride["bike_score"] = _calculate_bike_score(ride)

        # Trier et afficher top 3
        rides.sort(key=lambda r: r["bike_score"], reverse=True)
        print("\n3. Top 3 par bike_score :")
        for i, r in enumerate(rides[:3], 1):
            print(f"   {i}. {r['title']}")
            print(f"      Distance : {r['distance_km']}km | Dénivelé : {r['elevation_gain']}m D+")
            print(f"      Terrain : {r['terrain']} | Score : {r['bike_score']}")
            print(f"      Départ : {r['start_city']} ({r['distance_from_home']}km)")
