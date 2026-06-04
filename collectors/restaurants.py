"""
Module de collecte de restaurants via scraping.
Sources : Visit Alsace (principale), compléments locaux.
Aucune API tierce - uniquement requests + BeautifulSoup.
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, List
import re
from engine.cache import cache_get, cache_set, CACHE_TTL


# Coordonnées de Guebwiller
GUEBWILLER_LAT = 47.9069
GUEBWILLER_LON = 7.2147

# User-Agent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# Villes alsaciennes (Haut-Rhin et Bas-Rhin)
ALSACE_CITIES = [
    "Strasbourg", "Colmar", "Mulhouse", "Ribeauvillé", "Riquewihr", "Obernai",
    "Sélestat", "Haguenau", "Saverne", "Wissembourg", "Kaysersberg", "Guebwiller",
    "Thann", "Rouffach", "Soultz", "Munster", "Barr", "Molsheim", "Illkirch",
    "Schiltigheim", "Bischheim", "Lingolsheim", "Hoenheim", "Ostwald", "Illzach",
    "Wittenheim", "Kingersheim", "Rixheim", "Riedisheim", "Pfastatt", "Cernay",
    "Ensisheim", "Altkirch", "Saint-Louis", "Huningue", "Wintzenheim", "Turckheim",
    "Ammerschwihr", "Eguisheim", "Bergheim", "Marlenheim", "Wasselonne", "Brumath",
    "Lauterbourg", "Murbach", "Wattwiller", "Bollwiller", "Issenheim", "Buhl",
    "Soultzbach", "Soultzmatt", "Westhalten", "Orschwihr", "Pfaffenheim", "Hattstatt",
    "Husseren", "Voegtlinshoffen", "Obermorschwihr", "Herrlisheim", "Niederhergheim",
    "Andolsheim", "Sundhoffen", "Ingersheim", "Katzenthal", "Niedermorschwihr",
    "Ammerschwihr", "Kientzheim", "Sigolsheim", "Bennwihr", "Mittelwihr", "Beblenheim"
]

# Codes postaux Alsace (67xxx et 68xxx)
ALSACE_POSTCODES = ["67", "68"]


def _is_alsace_location(text: str) -> bool:
    """Vérifie si le texte contient une localisation alsacienne."""
    if not text:
        return False
    text_lower = text.lower()

    # Vérifier les villes
    for city in ALSACE_CITIES:
        if city.lower() in text_lower:
            return True

    # Vérifier les codes postaux (67xxx ou 68xxx)
    postcode_match = re.search(r'\b(67\d{3}|68\d{3})\b', text)
    if postcode_match:
        return True

    # Vérifier mentions explicites
    if any(x in text_lower for x in ["alsace", "haut-rhin", "bas-rhin"]):
        return True

    return False


def _extract_city(text: str) -> str:
    """Extrait une ville alsacienne depuis un texte."""
    if not text:
        return "Alsace"
    text_lower = text.lower()
    for city in ALSACE_CITIES:
        if city.lower() in text_lower:
            return city
    return "Alsace"


def _fetch_visitalsace_restaurants() -> List[Dict]:
    """
    Scrape les restaurants depuis Visit Alsace (tourisme officiel).
    Source principale et fiable.
    """
    url = "https://www.visit.alsace/gastronomie/restaurants/"
    restaurants = []

    print(f"\n  [VISITALSACE] Scraping {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  [VISITALSACE] Status HTTP: {response.status_code}")

        if response.status_code != 200:
            print(f"  [VISITALSACE] Erreur HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        print(f"  [VISITALSACE] HTML (300 premiers chars):\n{response.text[:300]}\n")

        # Visit Alsace utilise des cartes SIT
        cards = soup.select("article, .card, .item, [class*='card'], [class*='result'], .sit-item, .poi")
        print(f"  [VISITALSACE] Cartes trouvées: {len(cards)}")

        seen = set()

        for card in cards[:30]:
            try:
                name_el = card.select_one("h2, h3, .title, .name, a[href*='restaurant'], a[href*='gastronomie']")
                name = name_el.get_text(strip=True) if name_el else None

                if not name or len(name) < 3:
                    continue

                # Filtrer les noms génériques
                if name.lower() in ['voir plus', 'découvrir', 'restaurants', 'en savoir plus', 'alsace', 'gastronomie']:
                    continue

                # Nettoyer le nom (enlever préfixes comme "Maître restaurateur")
                name = re.sub(r'^(Maître restaurateur|Restaurant)\s*', '', name).strip()

                if name.lower() in seen or len(name) < 3:
                    continue
                seen.add(name.lower())

                city = _extract_city(card.get_text())

                link_el = card.select_one("a[href]")
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://www.visit.alsace{href}"

                restaurants.append({
                    "title": name,
                    "city": city,
                    "cuisine": "Alsacien",
                    "source": "Visit Alsace",
                    "url": full_url,
                    "reason": "Recommandé par Visit Alsace"
                })
                print(f"  [VISITALSACE] Trouvé: {name} ({city})")

            except Exception as e:
                continue

    except requests.exceptions.RequestException as e:
        print(f"  [VISITALSACE] Erreur requête: {e}")

    print(f"  [VISITALSACE] Total: {len(restaurants)} restaurants")
    return restaurants


def _fetch_jds_restaurants() -> List[Dict]:
    """
    Scrape les restaurants depuis JDS (Journal Des Spectacles) Alsace.
    """
    url = "https://www.jds.fr/gastronomie/restaurants/restaurants-gastronomiques-alsace-13255_L"
    restaurants = []

    print(f"\n  [JDS] Scraping {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  [JDS] Status HTTP: {response.status_code}")
        print(f"  [JDS] HTML (300 premiers chars):\n{response.text[:300]}\n")

        if response.status_code != 200:
            print(f"  [JDS] Erreur HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        # JDS utilise des cartes avec classe spécifique
        cards = soup.select("article, .card, .item, .poi, [class*='listing'], [class*='result']")
        print(f"  [JDS] Cartes trouvées: {len(cards)}")

        # Aussi chercher les liens
        links = soup.select("a[href*='restaurant'], a[href*='gastronomie']")
        print(f"  [JDS] Liens restaurants: {len(links)}")

        seen = set()

        for card in cards[:20]:
            try:
                name_el = card.select_one("h2, h3, .title, .name, a")
                name = name_el.get_text(strip=True) if name_el else None

                if not name or len(name) < 3 or name.lower() in seen:
                    continue

                if name.lower() in ['voir plus', 'en savoir plus', 'restaurants']:
                    continue

                seen.add(name.lower())
                city = _extract_city(card.get_text())

                link_el = card.select_one("a[href]")
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://www.jds.fr{href}"

                restaurants.append({
                    "title": name,
                    "city": city,
                    "cuisine": "Gastronomique",
                    "source": "JDS",
                    "url": full_url,
                    "reason": "Sélection JDS Alsace"
                })
                print(f"  [JDS] Trouvé: {name} ({city})")

            except Exception:
                continue

    except requests.exceptions.RequestException as e:
        print(f"  [JDS] Erreur requête: {e}")

    print(f"  [JDS] Total: {len(restaurants)} restaurants")
    return restaurants


def _fetch_tourisme68_restaurants() -> List[Dict]:
    """
    Scrape les restaurants depuis Tourisme68 (ADT Haut-Rhin).
    """
    url = "https://www.tourisme68.com/restaurants-gastronomiques/"
    restaurants = []

    print(f"\n  [TOURISME68] Scraping {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  [TOURISME68] Status HTTP: {response.status_code}")
        print(f"  [TOURISME68] HTML (300 premiers chars):\n{response.text[:300]}\n")

        if response.status_code != 200:
            # Essayer URL alternative
            alt_url = "https://www.tourisme68.com/ou-manger/"
            print(f"  [TOURISME68] Essai URL alt: {alt_url}")
            response = requests.get(alt_url, headers=HEADERS, timeout=15)
            print(f"  [TOURISME68] Status alt: {response.status_code}")
            if response.status_code != 200:
                return []

        soup = BeautifulSoup(response.text, "html.parser")

        cards = soup.select("article, .card, .item, [class*='card'], [class*='result']")
        print(f"  [TOURISME68] Cartes trouvées: {len(cards)}")

        seen = set()

        for card in cards[:20]:
            try:
                name_el = card.select_one("h2, h3, .title, .name, a")
                name = name_el.get_text(strip=True) if name_el else None

                if not name or len(name) < 3 or name.lower() in seen:
                    continue

                if name.lower() in ['voir plus', 'en savoir plus', 'restaurants', 'découvrir']:
                    continue

                seen.add(name.lower())
                city = _extract_city(card.get_text())

                link_el = card.select_one("a[href]")
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://www.tourisme68.com{href}"

                restaurants.append({
                    "title": name,
                    "city": city,
                    "cuisine": "Gastronomique",
                    "source": "Tourisme68",
                    "url": full_url,
                    "reason": "Recommandé Haut-Rhin Tourisme"
                })
                print(f"  [TOURISME68] Trouvé: {name} ({city})")

            except Exception:
                continue

    except requests.exceptions.RequestException as e:
        print(f"  [TOURISME68] Erreur requête: {e}")

    print(f"  [TOURISME68] Total: {len(restaurants)} restaurants")
    return restaurants


def _fetch_strasbourg_restaurants() -> List[Dict]:
    """
    Scrape les restaurants depuis Visit Strasbourg.
    """
    url = "https://www.visitstrasbourg.fr/decouvrir-strasbourg/gastronomie/restaurants-gastronomiques/"
    restaurants = []

    print(f"\n  [STRASBOURG] Scraping {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  [STRASBOURG] Status HTTP: {response.status_code}")
        print(f"  [STRASBOURG] HTML (300 premiers chars):\n{response.text[:300]}\n")

        if response.status_code != 200:
            # URL alternative
            alt_url = "https://www.visitstrasbourg.fr/decouvrir-strasbourg/gastronomie/"
            print(f"  [STRASBOURG] Essai URL alt: {alt_url}")
            response = requests.get(alt_url, headers=HEADERS, timeout=15)
            print(f"  [STRASBOURG] Status alt: {response.status_code}")
            if response.status_code != 200:
                return []

        soup = BeautifulSoup(response.text, "html.parser")

        cards = soup.select("article, .card, .item, [class*='card'], [class*='result'], .poi")
        print(f"  [STRASBOURG] Cartes trouvées: {len(cards)}")

        seen = set()

        for card in cards[:15]:
            try:
                name_el = card.select_one("h2, h3, .title, .name, a")
                name = name_el.get_text(strip=True) if name_el else None

                if not name or len(name) < 3 or name.lower() in seen:
                    continue

                if name.lower() in ['voir plus', 'en savoir plus', 'restaurants', 'découvrir']:
                    continue

                seen.add(name.lower())

                link_el = card.select_one("a[href]")
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://www.visitstrasbourg.fr{href}"

                restaurants.append({
                    "title": name,
                    "city": "Strasbourg",
                    "cuisine": "Gastronomique",
                    "source": "Visit Strasbourg",
                    "url": full_url,
                    "reason": "Gastronomie strasbourgeoise"
                })
                print(f"  [STRASBOURG] Trouvé: {name}")

            except Exception:
                continue

    except requests.exceptions.RequestException as e:
        print(f"  [STRASBOURG] Erreur requête: {e}")

    print(f"  [STRASBOURG] Total: {len(restaurants)} restaurants")
    return restaurants


def _deduplicate_restaurants(restaurants: List[Dict]) -> List[Dict]:
    """Supprime les doublons par nom de restaurant (normalisation)."""
    seen = set()
    unique = []
    for r in restaurants:
        # Normaliser le nom
        name_normalized = re.sub(r'[^a-z0-9]', '', r["title"].lower())
        if name_normalized not in seen and len(name_normalized) > 2:
            seen.add(name_normalized)
            unique.append(r)
    return unique


def get_restaurant_suggestions(period: Dict) -> List[Dict]:
    """
    Récupère les suggestions de restaurants pour une période donnée.
    Scrape Visit Alsace, JDS, Tourisme68, Visit Strasbourg.
    """
    period_start = period.get("start", "")
    cache_key = f"restaurants_{period_start}"

    # Vérifier le cache
    cached = cache_get(cache_key)
    if cached:
        print("  Restaurants : CACHE HIT")
        return cached

    print("  Restaurants : CACHE MISS → scraping sites tourisme Alsace")

    all_restaurants = []

    # Scraper les sources (ordre de priorité)
    visitalsace = _fetch_visitalsace_restaurants()
    all_restaurants.extend(visitalsace)

    jds = _fetch_jds_restaurants()
    all_restaurants.extend(jds)

    tourisme68 = _fetch_tourisme68_restaurants()
    all_restaurants.extend(tourisme68)

    strasbourg = _fetch_strasbourg_restaurants()
    all_restaurants.extend(strasbourg)

    # Dédupliquer
    all_restaurants = _deduplicate_restaurants(all_restaurants)

    print(f"\n  [TOTAL] {len(all_restaurants)} restaurants uniques trouvés")

    if not all_restaurants:
        print("  ⚠ Aucun restaurant trouvé via scraping")
        return []

    # Déduplication avec historique utilisateur
    from engine.profile import get_seen_items_normalized
    seen_restaurants = get_seen_items_normalized('restaurants', days=90)
    available = [r for r in all_restaurants if r["title"].lower() not in seen_restaurants]

    if not available:
        available = all_restaurants

    # Sélectionner 3 restaurants avec priorité aux sources locales
    selected = []
    priority_sources = ["Visit Alsace", "JDS", "Tourisme68", "Visit Strasbourg"]

    for source in priority_sources:
        for r in available:
            if r["source"] == source and r not in selected and len(selected) < 3:
                selected.append(r)
                break

    # Compléter si moins de 3
    for r in available:
        if r not in selected and len(selected) < 3:
            selected.append(r)

    print(f"  Restaurants : {len(selected)} sélectionnés sur {len(all_restaurants)} trouvés")

    # Ajouter champs pour compatibilité template
    for r in selected:
        r.setdefault("distance_km", 0)
        r.setdefault("rating", 0)
        r.setdefault("reviews_count", 0)
        r.setdefault("price_level", "€€€")

    # Mettre en cache
    cache_set(cache_key, selected, CACHE_TTL.get("restaurants", 480))

    return selected


def format_restaurants_context(restaurants: List[Dict]) -> str:
    """Formate les restaurants pour le contexte Claude."""
    if not restaurants:
        return "Restaurants : aucune suggestion disponible."

    lines = ["Restaurants recommandés (guides locaux Alsace) :"]

    for i, resto in enumerate(restaurants, 1):
        lines.append(f"{i}. {resto['title']} ({resto.get('cuisine', 'Gastronomique')})")
        lines.append(f"   Lieu : {resto.get('city', 'Alsace')}")
        lines.append(f"   Source : {resto.get('source', 'Guide')}")
        lines.append(f"   → {resto.get('reason', 'Recommandé')}")
        lines.append("")

    return "\n".join(lines)
