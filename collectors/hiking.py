import requests
from bs4 import BeautifulSoup
from datetime import date
from typing import Dict, List, Optional
import re

import config


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Distances depuis Guebwiller (km par la route)
CITY_DISTANCES = {
    "guebwiller": 0, "soultz": 5, "cernay": 10, "thann": 12,
    "mulhouse": 22, "colmar": 25, "freiburg": 45, "fribourg": 45,
    "strasbourg": 70, "bâle": 35, "bale": 35, "basel": 35,
    "belfort": 45, "munster": 20, "rouffach": 8, "ensisheim": 15,
    "wittelsheim": 18, "turckheim": 23, "kaysersberg": 28,
    "ribeauvillé": 30, "ribeauville": 30, "eguisheim": 22,
    "murbach": 3, "lautenbach": 5, "buhl": 4, "orschwihr": 6,
    "westhalten": 7, "soultzmatt": 8, "osenbach": 10,
    "linthal": 8, "rimbach": 10, "jungholtz": 2,
    "hartmannswiller": 6, "wuenheim": 5, "wattwiller": 8,
    "uffholtz": 9, "steinbach": 11, "vieux-thann": 13,
    "husseren-wesserling": 18, "kruth": 22, "wildenstein": 25,
    "fellering": 20, "oderen": 19, "moosch": 16,
    "le markstein": 15, "grand ballon": 12, "petit ballon": 18,
    "lac de kruth": 23, "lac du ballon": 14,
    # Villes randonnée Visorando
    "orbey": 35, "lapoutroie": 32, "le bonhomme": 40,
    "sewen": 30, "masevaux": 25, "rimbach-près-masevaux": 28,
    "burnhaupt-le-bas": 18, "burnhaupt-le-haut": 17,
    "labaroche": 38, "ammerschwihr": 28, "katzenthal": 27,
    "trois-épis": 30, "le hohwald": 50, "barr": 45,
    "thannenkirch": 35, "bergheim": 32, "hunawihr": 30,
    "stosswihr": 22, "sondernach": 18, "metzeral": 16,
    "mittlach": 20, "luttenbach": 15, "breitenbach": 12,
}

# Mots-clés pour détecter le terrain
TERRAIN_KEYWORDS = {
    "forêt": ["forêt", "bois", "arbres", "sous-bois", "forestier", "chêne", "hêtre", "sapin"],
    "vignes": ["vignes", "vignoble", "viticole", "raisin", "coteaux", "route des vins"],
    "crête": ["crête", "crêtes", "sommet", "ballon", "markstein", "panorama", "vue"],
    "lac": ["lac", "étang", "eau", "cascade", "rivière", "ruisseau"],
    "château": ["château", "ruine", "fort", "donjon", "remparts"],
}


def _estimate_distance_from_home(city: str) -> float:
    """Estime la distance depuis Guebwiller."""
    if not city:
        return 50.0

    normalized = city.lower().strip()
    normalized = re.sub(r'[àâ]', 'a', normalized)
    normalized = re.sub(r'[éèêë]', 'e', normalized)

    if normalized in CITY_DISTANCES:
        return CITY_DISTANCES[normalized]

    for known_city, distance in CITY_DISTANCES.items():
        if known_city in normalized or normalized in known_city:
            return distance

    return 50.0


def _detect_terrain(text: str) -> str:
    """Détecte le type de terrain depuis la description."""
    text_lower = text.lower()
    scores = {terrain: 0 for terrain in TERRAIN_KEYWORDS}

    for terrain, keywords in TERRAIN_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                scores[terrain] += 1

    # Retourne le terrain dominant ou "mixte"
    max_score = max(scores.values())
    if max_score == 0:
        return "mixte"

    dominant = [t for t, s in scores.items() if s == max_score]
    if len(dominant) > 1:
        return "mixte"

    return dominant[0]


def _calculate_weather_score(hike: Dict, weather_day: Optional[Dict] = None) -> float:
    """Calcule le score météo pour une randonnée."""
    score = 0.0

    if not weather_day:
        return 0.5  # Score neutre si pas de météo

    # suitable_outdoor = True : +0.4
    if weather_day.get("suitable_outdoor", False):
        score += 0.4

    # Température entre 15 et 25°C : +0.3
    temp_min = weather_day.get("temp_min", 10)
    temp_max = weather_day.get("temp_max", 20)
    avg_temp = (temp_min + temp_max) / 2
    if 15 <= avg_temp <= 25:
        score += 0.3
    elif 10 <= avg_temp <= 30:
        score += 0.15

    # Pluie < 1mm : +0.2
    rain = weather_day.get("rain_mm", 0)
    if rain < 1:
        score += 0.2
    elif rain < 5:
        score += 0.1

    # Bonus terrain vignes au printemps/automne
    today = date.today()
    if hike.get("terrain") == "vignes" and today.month in [3, 4, 5, 9, 10, 11]:
        score += 0.1

    return min(score, 1.0)


def _parse_duration(text: str) -> float:
    """Parse une durée en heures depuis un texte."""
    # Format "3h30" ou "3h 30min" ou "3 heures 30 minutes"
    hours = 0.0

    h_match = re.search(r'(\d+)\s*h', text, re.IGNORECASE)
    if h_match:
        hours = float(h_match.group(1))

    min_match = re.search(r'(\d+)\s*(?:min|mn)', text, re.IGNORECASE)
    if min_match:
        hours += float(min_match.group(1)) / 60

    # Si format "X heures"
    if hours == 0:
        heures_match = re.search(r'(\d+(?:[.,]\d+)?)\s*heures?', text, re.IGNORECASE)
        if heures_match:
            hours = float(heures_match.group(1).replace(',', '.'))

    return hours if hours > 0 else 2.0  # Défaut 2h


def _parse_distance(text: str) -> float:
    """Parse une distance en km depuis un texte."""
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*km', text, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(',', '.'))
    return 0.0


def _parse_elevation(text: str) -> int:
    """Parse un dénivelé en mètres depuis un texte."""
    match = re.search(r'(\d+)\s*m', text)
    if match:
        return int(match.group(1))
    return 0


def _parse_rating(card: BeautifulSoup) -> float:
    """Extrait la note Visorando."""
    # Cherche les étoiles ou la note numérique
    rating_elem = card.select_one(".rating, .note, [class*='star'], [class*='rating']")
    if rating_elem:
        # Chercher une note numérique
        text = rating_elem.get_text(strip=True)
        match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:/\s*5)?', text)
        if match:
            rating = float(match.group(1).replace(',', '.'))
            if rating <= 5:
                return rating

        # Compter les étoiles pleines
        full_stars = len(rating_elem.select("[class*='full'], [class*='active']"))
        if full_stars > 0:
            return float(full_stars)

    # Chercher dans les attributs data
    for elem in card.select("[data-rating], [data-note]"):
        rating = elem.get("data-rating") or elem.get("data-note")
        if rating:
            try:
                return float(rating)
            except ValueError:
                pass

    return 0.0


def _scrape_visorando() -> List[Dict]:
    """Scrape les randonnées depuis Visorando."""
    prefs = config.HIKING_PREFS

    url = "https://www.visorando.com/randonnee-haut-rhin.html"

    hikes = []

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")

        # Les cartes de randonnée ont la classe card--link
        cards = soup.select("a.card--link[href*='/randonnee-']")

        for card in cards[:20]:  # Limiter à 20 résultats
            try:
                hike = _parse_visorando_card(card)
                if hike and hike.get("title"):
                    # Filtrer selon les préférences
                    if hike["elevation_gain"] <= prefs.get("max_elevation_gain", 300):
                        if hike["distance_from_home"] <= prefs.get("max_drive_km", 80):
                            hikes.append(hike)
            except Exception:
                continue

    except requests.exceptions.RequestException as e:
        print(f"  ⚠ Erreur Visorando: {e}")

    return hikes


def _parse_visorando_card(card: BeautifulSoup) -> Optional[Dict]:
    """Parse une carte de randonnée Visorando (structure 2024+)."""
    # URL
    url = card.get("href", "")
    if not url.startswith("http"):
        url = f"https://www.visorando.com{url}"

    # Extraire le texte brut de la carte
    card_text = card.get_text(" ", strip=True)

    # Titre - chercher dans un élément spécifique ou extraire du texte
    title = ""
    title_elem = card.select_one("h2, h3, .card__title, [class*='title']")
    if title_elem:
        title = title_elem.get_text(strip=True)
    else:
        # Le titre est généralement au début, avant les métadonnées
        # Pattern: texte avant "km" ou "Visorandonneur"
        title_match = re.search(r'^(.+?)(?:Visorandonneur|Club|\d+[,.]?\d*\s*km)', card_text)
        if title_match:
            title = title_match.group(1).strip()

    if not title or len(title) < 3:
        return None

    # Distance - format "XX,XX km"
    distance_match = re.search(r'(\d+[,.]?\d*)\s*km', card_text)
    distance_km = float(distance_match.group(1).replace(',', '.')) if distance_match else 0.0

    # Dénivelé positif - format "+XXX m"
    elevation_match = re.search(r'\+(\d+)\s*m', card_text)
    elevation_gain = int(elevation_match.group(1)) if elevation_match else 0

    # Durée - format "Xh XX" ou "X h XX"
    duration_match = re.search(r'(\d+)\s*h\s*(\d+)?', card_text)
    if duration_match:
        hours = int(duration_match.group(1))
        minutes = int(duration_match.group(2) or 0)
        duration_h = hours + minutes / 60
    else:
        duration_h = 2.0

    # Difficulté
    difficulty = "Moyen"
    if "Facile" in card_text:
        difficulty = "Facile"
    elif "Difficile" in card_text:
        difficulty = "Difficile"
    elif "Moyenne" in card_text:
        difficulty = "Moyen"

    # Ville de départ - format "Départ à [Ville]"
    start_city = ""
    city_match = re.search(r'Départ\s+à\s+([A-Za-zÀ-ÿ\-]+(?:\s+[A-Za-zÀ-ÿ\-]+)?)', card_text)
    if city_match:
        start_city = city_match.group(1).strip()

    # Distance depuis Guebwiller
    distance_from_home = _estimate_distance_from_home(start_city)

    # Circuit en boucle (dénivelé + et - similaires)
    loop = False
    neg_match = re.search(r'-(\d+)\s*m', card_text)
    if neg_match and elevation_match:
        neg_elev = int(neg_match.group(1))
        pos_elev = int(elevation_match.group(1))
        loop = abs(pos_elev - neg_elev) < 50  # Tolérance de 50m

    # Terrain (basé sur le titre et l'URL)
    terrain = _detect_terrain(title + " " + url)

    return {
        "title": title,
        "distance_km": distance_km,
        "duration_h": duration_h,
        "elevation_gain": elevation_gain,
        "difficulty": difficulty,
        "start_city": start_city,
        "distance_from_home": distance_from_home,
        "rating": 0.0,  # Pas de note visible dans les cartes
        "terrain": terrain,
        "loop": loop,
        "description": "",
        "url": url,
        "weather_score": 0.5
    }


def get_hiking_suggestions(period: Dict, weather_data: Optional[Dict] = None) -> List[Dict]:
    """
    Récupère les suggestions de randonnée pour une période donnée.
    """
    print("  Scraping randonnées Visorando...")

    hikes = _scrape_visorando()

    if not hikes:
        print("  ⚠ Aucune randonnée trouvée sur Visorando")
        return []

    # Calculer le weather_score pour chaque randonnée
    best_weather_day = None
    if weather_data and weather_data.get("days"):
        # Trouver le meilleur jour météo
        days = weather_data["days"]
        suitable_days = [d for d in days if d.get("suitable_outdoor", False)]
        if suitable_days:
            best_weather_day = suitable_days[0]
        elif days:
            best_weather_day = days[0]

    for hike in hikes:
        hike["weather_score"] = _calculate_weather_score(hike, best_weather_day)

    # Trier par score combiné (note + weather_score + bonus boucle)
    def sort_key(h):
        score = (h.get("rating", 0) or 0) * 0.4
        score += h.get("weather_score", 0) * 0.3
        score += 0.2 if h.get("loop", False) else 0
        score -= h.get("distance_from_home", 50) * 0.005  # Pénalité distance
        return -score

    hikes.sort(key=sort_key)

    print(f"  Randonnées : {len(hikes)} trouvées")

    return hikes


def get_hiking_summary(hikes: List[Dict]) -> Dict:
    """Génère un résumé des randonnées."""
    if not hikes:
        return {"total": 0, "top_hikes": []}

    return {
        "total": len(hikes),
        "top_hikes": hikes[:3],
        "by_difficulty": {
            "Facile": len([h for h in hikes if h["difficulty"] == "Facile"]),
            "Moyen": len([h for h in hikes if h["difficulty"] == "Moyen"]),
            "Difficile": len([h for h in hikes if h["difficulty"] == "Difficile"]),
        },
        "by_terrain": {
            terrain: len([h for h in hikes if h["terrain"] == terrain])
            for terrain in set(h["terrain"] for h in hikes)
        }
    }


def display_hiking_suggestions(hikes: List[Dict]) -> None:
    """Affiche les randonnées dans le terminal."""
    print(f"\n{'='*50}")
    print("RANDONNÉES - Visorando")
    print(f"{'='*50}")

    if not hikes:
        print("Aucune randonnée trouvée")
        return

    summary = get_hiking_summary(hikes)
    print(f"\nTotal : {summary['total']} randonnées")

    # Par difficulté
    diff_parts = [f"{d}: {c}" for d, c in summary["by_difficulty"].items() if c > 0]
    print(f"Difficulté : {', '.join(diff_parts)}")

    print(f"\n{'—'*50}")
    print("TOP 3 RANDONNÉES")
    print(f"{'—'*50}")

    for i, hike in enumerate(summary["top_hikes"], 1):
        loop_str = "boucle" if hike["loop"] else "aller-retour"
        rating_str = f"{hike['rating']:.1f}/5" if hike["rating"] > 0 else "N/A"

        print(f"\n{i}. {hike['title']}")
        print(f"   Distance    : {hike['distance_km']:.1f} km ({loop_str})")
        print(f"   Durée       : {hike['duration_h']:.1f}h")
        print(f"   Dénivelé    : {hike['elevation_gain']} m")
        print(f"   Difficulté  : {hike['difficulty']}")
        print(f"   Départ      : {hike['start_city'] or 'NC'} ({hike['distance_from_home']:.0f} km)")
        print(f"   Terrain     : {hike['terrain']} | Note : {rating_str}")

    print(f"\n{'='*50}\n")
