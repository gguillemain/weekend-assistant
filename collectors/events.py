import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import re
import time
import math

from collectors.rss_reader import fetch_rss, try_rss_urls
import config


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Distances approximatives depuis Guebwiller (en km)
CITY_DISTANCES = {
    "guebwiller": 0, "soultz": 5, "cernay": 10, "thann": 12,
    "mulhouse": 22, "colmar": 25, "freiburg": 45, "fribourg": 45,
    "strasbourg": 70, "bâle": 35, "bale": 35, "basel": 35,
    "belfort": 45, "troyes": 220, "dijon": 180,
    "nancy": 160, "besançon": 130, "besancon": 130,
    "sélestat": 40, "selestat": 40, "obernai": 50,
    "ribeauvillé": 30, "ribeauville": 30, "kaysersberg": 28,
    "riquewihr": 30, "eguisheim": 22, "turckheim": 23,
    "munster": 20, "rouffach": 8, "ensisheim": 15,
    "wittelsheim": 18, "kingersheim": 20, "illzach": 24,
    "rixheim": 26, "wittenheim": 20, "pfastatt": 21,
    "altkirch": 40, "saint-louis": 45, "huningue": 40
}

# Catégories normalisées
CATEGORY_KEYWORDS = {
    "concert": ["concert", "musique", "live", "festival musique", "jazz", "rock", "classique", "orchestre", "chorale"],
    "expo": ["exposition", "expo", "musée", "galerie", "art", "vernissage", "photographie"],
    "festival": ["festival", "fête", "foire", "carnaval", "kermesse"],
    "theatre": ["théâtre", "theatre", "spectacle", "comédie", "danse", "ballet", "cirque", "opéra", "opera"],
    "marche": ["marché", "marche", "brocante", "vide-grenier", "puces", "artisanat"],
    "balade": ["balade", "randonnée", "randonnee", "visite guidée", "visite", "découverte", "nature", "patrimoine"],
    "gastronomie": ["gastronomie", "dégustation", "vin", "cuisine", "repas", "brunch", "food", "terroir"]
}

# Stats des sources
SOURCES_STATUS = {
    "jds": {"method": None, "count": 0},
    "strasbourg": {"method": None, "count": 0},
    "visit_alsace": {"method": None, "count": 0}
}


def _normalize_city(city: str) -> str:
    """Normalise le nom de ville pour la recherche de distance."""
    return city.lower().strip().replace("-", " ").replace("'", "")


def _get_distance(city: str) -> float:
    """Retourne la distance depuis Guebwiller pour une ville."""
    if not city:
        return 100.0

    normalized = _normalize_city(city)

    if normalized in CITY_DISTANCES:
        return CITY_DISTANCES[normalized]

    for known_city, distance in CITY_DISTANCES.items():
        if known_city in normalized or normalized in known_city:
            return distance

    return 100.0


def _detect_category(title: str, description: str = "") -> str:
    """Détecte la catégorie d'un événement."""
    text = (title + " " + description).lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return category

    return "autre"


def _parse_price(price_text: str) -> str:
    """Parse et normalise le prix."""
    if not price_text:
        return "NC"

    price_lower = price_text.lower().strip()

    if "gratuit" in price_lower or "libre" in price_lower or "free" in price_lower:
        return "Gratuit"

    match = re.search(r'(\d+(?:[.,]\d+)?)\s*[€$]', price_text)
    if match:
        return f"{match.group(1)}€"

    match = re.search(r'[€$]\s*(\d+(?:[.,]\d+)?)', price_text)
    if match:
        return f"{match.group(1)}€"

    if "réservation" in price_lower or "inscription" in price_lower:
        return "Sur réservation"

    return "NC"


def _extract_city_from_text(text: str) -> str:
    """Extrait une ville depuis un texte."""
    if not text:
        return ""

    text_lower = text.lower()

    # Chercher les villes connues
    for city in CITY_DISTANCES.keys():
        if city in text_lower:
            return city.capitalize()

    # Chercher après des prépositions
    match = re.search(r'(?:à|de|en)\s+([A-Za-zÀ-ÿ\-]+)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return ""


def _parse_date_from_text(date_text: str, reference_date: date) -> Tuple[Optional[date], Optional[date]]:
    """Parse une date ou plage de dates depuis du texte."""
    if not date_text:
        return None, None

    date_text = date_text.lower().strip()
    year = reference_date.year

    months = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
    }

    # Format "du X au Y mois"
    range_match = re.search(r'(\d{1,2})\s*(?:au|[-–])\s*(\d{1,2})\s*(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)', date_text)
    if range_match:
        day_start = int(range_match.group(1))
        day_end = int(range_match.group(2))
        month = months.get(range_match.group(3))
        if month:
            try:
                return date(year, month, day_start), date(year, month, day_end)
            except ValueError:
                pass

    # Format "X mois"
    single_match = re.search(r'(\d{1,2})\s*(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)', date_text)
    if single_match:
        day = int(single_match.group(1))
        month = months.get(single_match.group(2))
        if month:
            try:
                d = date(year, month, day)
                return d, d
            except ValueError:
                pass

    # Format "DD/MM"
    date_match = re.search(r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?', date_text)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        if date_match.group(3):
            year = int(date_match.group(3))
            if year < 100:
                year += 2000
        try:
            d = date(year, month, day)
            return d, d
        except ValueError:
            pass

    return None, None


def _calculate_score(event: Dict, period: Dict) -> float:
    """Calcule le score de pertinence d'un événement."""
    score = 0.0

    if event.get("distance_km", 100) < 50:
        score += 0.3

    price = event.get("price", "NC")
    if price == "Gratuit":
        score += 0.2
    elif price != "NC" and price != "Sur réservation":
        try:
            price_val = float(re.search(r'(\d+(?:[.,]\d+)?)', price).group(1).replace(',', '.'))
            if price_val < 15:
                score += 0.2
        except (AttributeError, ValueError):
            pass

    if event.get("category") in ["expo", "concert"]:
        score += 0.2

    event_start = event.get("date_start")
    event_end = event.get("date_end")
    if event_start and event_end:
        period_start = period["start"]
        period_end = period["end"]
        current = max(event_start, period_start)
        end = min(event_end, period_end)
        while current <= end:
            if current.weekday() >= 5:
                score += 0.2
                break
            current += timedelta(days=1)

    if event.get("description") and len(event["description"]) > 20:
        score += 0.1

    return min(score, 1.0)


def _fetch_jds_rss(period_start: date, period_end: date) -> List[Dict]:
    """Récupère les événements JDS via RSS."""
    global SOURCES_STATUS

    rss_urls = [
        "https://www.jds.fr/rss",
        "https://www.jds.fr/rss/alsace",
        "https://www.jds.fr/feed",
        "https://www.jds.fr/alsace/rss",
        "https://www.jds.fr/alsace/agenda/rss"
    ]

    items, used_url = try_rss_urls(rss_urls)

    if items:
        events = []
        for item in items:
            title = item.get("title", "")
            if not title or len(title) < 3:
                continue

            description = item.get("description", "")
            city = _extract_city_from_text(title + " " + description)
            date_start, date_end = None, None

            if item.get("published"):
                pub = item["published"]
                if isinstance(pub, datetime):
                    date_start = pub.date()
                    date_end = date_start

            if not date_start:
                date_start, date_end = _parse_date_from_text(description, period_start)

            events.append({
                "title": title,
                "category": _detect_category(title, description),
                "date_start": date_start or period_start,
                "date_end": date_end or period_end,
                "location": "",
                "city": city,
                "distance_km": _get_distance(city),
                "price": "NC",
                "description": description[:300],
                "url": item.get("link", ""),
                "source": "JDS"
            })

        SOURCES_STATUS["jds"] = {"method": "RSS", "count": len(events)}
        print(f"  JDS : RSS OK ({len(events)} items)")
        return events

    # Fallback scraping
    print("  JDS : RSS KO → fallback scraping")
    SOURCES_STATUS["jds"] = {"method": "scraping", "count": 0}
    return _scrape_jds_fallback(period_start, period_end)


def _scrape_jds_fallback(period_start: date, period_end: date) -> List[Dict]:
    """Fallback scraping pour JDS."""
    global SOURCES_STATUS
    events = []

    url = "https://www.jds.fr/alsace/agenda"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")

        event_cards = soup.select("article, .event, .agenda-item, [class*='event'], .card")

        for card in event_cards:
            title_elem = card.select_one("h2, h3, h4, .title, [class*='title'] a")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            link = title_elem.get("href", "")
            if link and not link.startswith("http"):
                link = f"https://www.jds.fr{link}"

            location_elem = card.select_one(".location, .lieu, [class*='location']")
            city = ""
            if location_elem:
                city = _extract_city_from_text(location_elem.get_text())

            desc_elem = card.select_one(".description, .summary, p")
            description = desc_elem.get_text(strip=True)[:300] if desc_elem else ""

            events.append({
                "title": title,
                "category": _detect_category(title, description),
                "date_start": period_start,
                "date_end": period_end,
                "location": "",
                "city": city,
                "distance_km": _get_distance(city),
                "price": "NC",
                "description": description,
                "url": link,
                "source": "JDS"
            })

        SOURCES_STATUS["jds"]["count"] = len(events)

    except Exception as e:
        print(f"  ⚠ Erreur JDS scraping : {e}")

    return events


def _fetch_strasbourg_rss(period_start: date, period_end: date) -> List[Dict]:
    """Récupère les événements Strasbourg via RSS."""
    global SOURCES_STATUS

    rss_urls = [
        "https://www.strasbourg.eu/rss/agenda",
        "https://www.strasbourg.eu/agenda/rss",
        "https://www.strasbourg.eu/feed",
        "https://www.strasbourg.eu/rss"
    ]

    items, used_url = try_rss_urls(rss_urls)

    if items:
        events = []
        for item in items:
            title = item.get("title", "")
            if not title or len(title) < 3:
                continue

            description = item.get("description", "")
            date_start, date_end = None, None

            if item.get("published"):
                pub = item["published"]
                if isinstance(pub, datetime):
                    date_start = pub.date()
                    date_end = date_start

            events.append({
                "title": title,
                "category": _detect_category(title, description),
                "date_start": date_start or period_start,
                "date_end": date_end or period_end,
                "location": "",
                "city": "Strasbourg",
                "distance_km": _get_distance("Strasbourg"),
                "price": "NC",
                "description": description[:300],
                "url": item.get("link", ""),
                "source": "Strasbourg"
            })

        SOURCES_STATUS["strasbourg"] = {"method": "RSS", "count": len(events)}
        print(f"  Strasbourg : RSS OK ({len(events)} items)")
        return events

    # Fallback scraping
    print("  Strasbourg : RSS KO → fallback scraping")
    SOURCES_STATUS["strasbourg"] = {"method": "scraping", "count": 0}
    return _scrape_strasbourg_fallback(period_start, period_end)


def _scrape_strasbourg_fallback(period_start: date, period_end: date) -> List[Dict]:
    """Fallback scraping pour Strasbourg."""
    global SOURCES_STATUS
    events = []

    url = "https://www.strasbourg.eu/agenda"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")

        event_cards = soup.select("article, .event, .agenda-item, [class*='event'], .card")

        for card in event_cards:
            title_elem = card.select_one("h2, h3, h4, .title, [class*='title'] a")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            link = title_elem.get("href", "")
            if link and not link.startswith("http"):
                link = f"https://www.strasbourg.eu{link}"

            desc_elem = card.select_one(".description, .summary, p")
            description = desc_elem.get_text(strip=True)[:300] if desc_elem else ""

            events.append({
                "title": title,
                "category": _detect_category(title, description),
                "date_start": period_start,
                "date_end": period_end,
                "location": "",
                "city": "Strasbourg",
                "distance_km": _get_distance("Strasbourg"),
                "price": "NC",
                "description": description,
                "url": link,
                "source": "Strasbourg"
            })

        SOURCES_STATUS["strasbourg"]["count"] = len(events)

    except Exception as e:
        print(f"  ⚠ Erreur Strasbourg scraping : {e}")

    return events


def _fetch_visit_alsace_rss(period_start: date, period_end: date) -> List[Dict]:
    """Récupère les événements Visit Alsace via RSS."""
    global SOURCES_STATUS

    rss_urls = [
        "https://www.visit.alsace/feed",
        "https://www.visit.alsace/feed/",
        "https://www.visit.alsace/rss",
        "https://www.visit.alsace/agenda/feed"
    ]

    items, used_url = try_rss_urls(rss_urls)

    if items:
        events = []
        for item in items:
            title = item.get("title", "")
            if not title or len(title) < 3:
                continue

            description = item.get("description", "")
            city = _extract_city_from_text(title + " " + description)
            date_start, date_end = None, None

            if item.get("published"):
                pub = item["published"]
                if isinstance(pub, datetime):
                    date_start = pub.date()
                    date_end = date_start

            events.append({
                "title": title,
                "category": _detect_category(title, description),
                "date_start": date_start or period_start,
                "date_end": date_end or period_end,
                "location": "",
                "city": city,
                "distance_km": _get_distance(city),
                "price": "NC",
                "description": description[:300],
                "url": item.get("link", ""),
                "source": "Visit Alsace"
            })

        SOURCES_STATUS["visit_alsace"] = {"method": "RSS", "count": len(events)}
        print(f"  Visit Alsace : RSS OK ({len(events)} items)")
        return events

    # Fallback scraping
    print("  Visit Alsace : RSS KO → fallback scraping")
    SOURCES_STATUS["visit_alsace"] = {"method": "scraping", "count": 0}
    return _scrape_visit_alsace_fallback(period_start, period_end)


def _scrape_visit_alsace_fallback(period_start: date, period_end: date) -> List[Dict]:
    """Fallback scraping pour Visit Alsace."""
    global SOURCES_STATUS
    events = []

    url = "https://www.visit.alsace/agenda/"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")

        event_cards = soup.select("article, .event, .agenda-item, [class*='event'], .card, .item")

        for card in event_cards:
            title_elem = card.select_one("h2, h3, h4, .title, [class*='title'] a")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            link = title_elem.get("href", "")
            if link and not link.startswith("http"):
                link = f"https://www.visit.alsace{link}"

            location_elem = card.select_one(".location, .lieu, [class*='location'], .city")
            city = ""
            if location_elem:
                city = _extract_city_from_text(location_elem.get_text())

            desc_elem = card.select_one(".description, .summary, p")
            description = desc_elem.get_text(strip=True)[:300] if desc_elem else ""

            events.append({
                "title": title,
                "category": _detect_category(title, description),
                "date_start": period_start,
                "date_end": period_end,
                "location": "",
                "city": city,
                "distance_km": _get_distance(city),
                "price": "NC",
                "description": description,
                "url": link,
                "source": "Visit Alsace"
            })

        SOURCES_STATUS["visit_alsace"]["count"] = len(events)

    except Exception as e:
        print(f"  ⚠ Erreur Visit Alsace scraping : {e}")

    return events


def _deduplicate_events(events: List[Dict]) -> List[Dict]:
    """Dédoublonne les événements par titre + ville."""
    seen = set()
    unique = []

    for event in events:
        key = (_normalize_city(event["title"]), _normalize_city(event.get("city", "")))
        if key not in seen:
            seen.add(key)
            unique.append(event)

    return unique


def get_local_events(period: Dict) -> List[Dict]:
    """Récupère les événements locaux pour une période donnée."""
    period_start = period["start"]
    period_end = period["end"]

    print("  Scraping événements...")

    all_events = []

    # JDS
    jds_events = _fetch_jds_rss(period_start, period_end)
    all_events.extend(jds_events)
    time.sleep(0.3)

    # Strasbourg
    strasbourg_events = _fetch_strasbourg_rss(period_start, period_end)
    all_events.extend(strasbourg_events)
    time.sleep(0.3)

    # Visit Alsace
    visit_events = _fetch_visit_alsace_rss(period_start, period_end)
    all_events.extend(visit_events)

    # Dédoublonner
    all_events = _deduplicate_events(all_events)

    # Calculer les scores
    for event in all_events:
        event["score"] = _calculate_score(event, period)

    # Trier par score décroissant
    all_events.sort(key=lambda x: x["score"], reverse=True)

    return all_events


def get_events_summary(events: List[Dict]) -> Dict:
    """Génère un résumé des événements."""
    by_category = {}
    for event in events:
        cat = event.get("category", "autre")
        if cat not in by_category:
            by_category[cat] = 0
        by_category[cat] += 1

    return {
        "total": len(events),
        "by_source": {
            "JDS": SOURCES_STATUS["jds"]["count"],
            "Strasbourg": SOURCES_STATUS["strasbourg"]["count"],
            "Visit Alsace": SOURCES_STATUS["visit_alsace"]["count"]
        },
        "by_category": by_category,
        "top_events": events[:5]
    }


def get_sources_line() -> str:
    """Retourne la ligne de résumé des sources avec méthode."""
    parts = []
    source_names = {"jds": "JDS", "strasbourg": "Strasbourg", "visit_alsace": "Visit Alsace"}

    for key, name in source_names.items():
        status = SOURCES_STATUS[key]
        method = status["method"] or "N/A"
        count = status["count"]
        parts.append(f"{name} [{method}] ({count})")

    return " | ".join(parts)
