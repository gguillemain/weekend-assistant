"""
Module de collecte des événements "découverte" — bons plans locaux inattendus.
RSS en priorité, scraping en fallback.
"""

import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import re

import config
from collectors import rss_reader

# Distances depuis Guebwiller
CITY_DISTANCES = getattr(config, "CITY_DISTANCES", {})

# Headers pour le scraping
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,de;q=0.8,en;q=0.7",
}

# Catégories connues
CATEGORY_KEYWORDS = {
    "gastronomie": ["restaurant", "gastronomie", "dégustation", "vin", "bière", "food", "cuisine", "marché gourmand", "brunch"],
    "marche": ["marché", "brocante", "vide-grenier", "puces", "artisanat", "markt"],
    "festival": ["festival", "fête", "fest", "kermesse", "carnaval", "fasching"],
    "sport": ["sport", "course", "marathon", "vélo", "cyclisme", "trail", "randonnée sportive", "triathlon"],
    "nature": ["nature", "jardin", "parc", "balade", "promenade", "forêt", "observation"],
    "patrimoine": ["patrimoine", "visite guidée", "château", "église", "historique", "monument", "journées"],
    "insolite": ["insolite", "escape", "énigme", "mystère", "secret", "underground", "alternatif"],
}


def _get_distance(city: str) -> float:
    """Retourne la distance depuis Guebwiller pour une ville."""
    if not city:
        return 100.0
    city_lower = city.lower().strip()
    for known_city, dist in CITY_DISTANCES.items():
        if known_city.lower() in city_lower or city_lower in known_city.lower():
            return float(dist)
    # Estimations pour villes courantes non listées
    estimates = {
        "basel": 45, "bâle": 45, "freiburg": 50, "fribourg": 50,
        "sélestat": 50, "obernai": 70, "haguenau": 120,
    }
    for name, dist in estimates.items():
        if name in city_lower:
            return float(dist)
    return 100.0


def _detect_category(title: str, description: str) -> str:
    """Détecte la catégorie d'un événement."""
    text = f"{title} {description}".lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return category

    return "autre"


def _parse_date_fr(text: str) -> Optional[date]:
    """Parse une date française."""
    if not text:
        return None

    text = text.strip().lower()

    months_fr = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    }

    # Format "15 mars 2026"
    match = re.search(r"(\d{1,2})\s+([a-zéû]+)\.?\s*(\d{4})?", text)
    if match:
        day = int(match.group(1))
        month_str = match.group(2)
        year = int(match.group(3)) if match.group(3) else date.today().year

        for month_name, month_num in months_fr.items():
            if month_str.startswith(month_name[:3]):
                try:
                    return date(year, month_num, day)
                except ValueError:
                    pass

    # Format "15/03/2026"
    match = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", text)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except ValueError:
            pass

    return None


def _extract_price(text: str) -> str:
    """Extrait le prix d'un texte."""
    if not text:
        return "NC"

    text_lower = text.lower()

    if "gratuit" in text_lower or "free" in text_lower or "entrée libre" in text_lower:
        return "Gratuit"

    # Chercher un prix en euros
    match = re.search(r"(\d+(?:[.,]\d{2})?)\s*€", text)
    if match:
        return f"{match.group(1)}€"

    return "NC"


def _calculate_surprise_score(
    category: str,
    distance_km: float,
    price: str,
    description: str,
    date_start: Optional[date],
    date_end: Optional[date],
    period_start: date,
    period_end: date
) -> float:
    """
    Calcule le score de surprise (favorise ce qui sort du profil habituel).

    Returns:
        Score entre 0 et 1
    """
    score = 0.0

    # Catégorie NON dans les habituels (+0.4)
    usual_categories = ["cinema", "rando", "concert", "expo", "exposition"]
    if category not in usual_categories:
        score += 0.4

    # Distance entre 30 et 150km (+0.2)
    if 30 <= distance_km <= 150:
        score += 0.2

    # Prix gratuit ou < 10€ (+0.2)
    if price == "Gratuit":
        score += 0.2
    elif price != "NC":
        try:
            price_val = float(re.search(r"(\d+)", price).group(1))
            if price_val < 10:
                score += 0.2
        except (AttributeError, ValueError):
            pass

    # Description non vide (+0.1)
    if description and len(description) > 20:
        score += 0.1

    # Week-end couvert (+0.1)
    if date_start and date_end:
        if date_start <= period_end and date_end >= period_start:
            score += 0.1
    elif date_start:
        if period_start <= date_start <= period_end:
            score += 0.1

    return min(score, 1.0)


# =============================================================================
# SOURCES RSS + SCRAPING
# =============================================================================

def _fetch_jds_rss(city: str, verbose: bool = False) -> List[Dict]:
    """Récupère les événements JDS via RSS."""
    url = f"https://www.jds.fr/rss/{city.lower()}"
    source = f"JDS {city.title()}"
    events = []

    try:
        items = rss_reader.fetch_rss(url)
        if verbose:
            print(f"  {source} RSS: {len(items)} items")

        for item in items:
            title = item.get("title", "")
            if not title:
                continue

            description = item.get("description", "")
            category = _detect_category(title, description)
            pub_date = item.get("published")

            events.append({
                "title": title,
                "category": category,
                "date_start": pub_date.date() if isinstance(pub_date, datetime) else None,
                "date_end": None,
                "city": city.title(),
                "distance_km": _get_distance(city),
                "price": _extract_price(description),
                "description": description[:300] if description else "",
                "url": item.get("link", ""),
                "source": source,
                "surprise_score": 0.0
            })

        return events

    except Exception as e:
        if verbose:
            print(f"  {source} RSS: ERREUR — {e}")
        return []


def _scrape_jds(city: str, verbose: bool = False) -> List[Dict]:
    """Scrape les événements JDS."""
    url = f"https://www.jds.fr/{city.lower()}/agenda"
    source = f"JDS {city.title()}"
    events = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if verbose:
            print(f"  {source} scraping: HTTP {resp.status_code}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "lxml")

        for item in soup.select("article, .event, .agenda-item, [class*='event']"):
            title_el = item.select_one("h2, h3, .title, a")
            date_el = item.select_one(".date, [class*='date'], time")
            desc_el = item.select_one("p, .description")
            link_el = item.select_one("a[href]")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            description = desc_el.get_text(strip=True)[:300] if desc_el else ""
            dates_text = date_el.get_text(strip=True) if date_el else ""

            events.append({
                "title": title,
                "category": _detect_category(title, description),
                "date_start": _parse_date_fr(dates_text),
                "date_end": None,
                "city": city.title(),
                "distance_km": _get_distance(city),
                "price": _extract_price(description),
                "description": description,
                "url": link_el.get("href", "") if link_el else url,
                "source": source,
                "surprise_score": 0.0
            })

        return events

    except Exception as e:
        if verbose:
            print(f"  {source} scraping: ERREUR — {e}")
        return []


def _fetch_tourisme_alsace(verbose: bool = False) -> List[Dict]:
    """Récupère les événements Tourisme Alsace."""
    rss_url = "https://www.tourisme-alsace.com/rss/agenda"
    scrape_url = "https://www.tourisme-alsace.com/agenda/"
    source = "Tourisme Alsace"
    events = []

    # Essayer RSS d'abord
    try:
        items = rss_reader.fetch_rss(rss_url)
        if items:
            if verbose:
                print(f"  {source} RSS: {len(items)} items")

            for item in items:
                title = item.get("title", "")
                if not title:
                    continue

                description = item.get("description", "")
                pub_date = item.get("published")

                events.append({
                    "title": title,
                    "category": _detect_category(title, description),
                    "date_start": pub_date.date() if isinstance(pub_date, datetime) else None,
                    "date_end": None,
                    "city": "Alsace",
                    "distance_km": 50.0,
                    "price": _extract_price(description),
                    "description": description[:300] if description else "",
                    "url": item.get("link", ""),
                    "source": source,
                    "surprise_score": 0.0
                })

            return events
    except Exception:
        pass

    # Fallback scraping
    if verbose:
        print(f"  {source} RSS: KO → fallback scraping")

    try:
        resp = requests.get(scrape_url, headers=HEADERS, timeout=15)
        if verbose:
            print(f"  {source} scraping: HTTP {resp.status_code}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "lxml")

        for item in soup.select("article, .event, [class*='event'], .card"):
            title_el = item.select_one("h2, h3, .title")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            desc_el = item.select_one("p, .description")
            description = desc_el.get_text(strip=True)[:300] if desc_el else ""

            events.append({
                "title": title,
                "category": _detect_category(title, description),
                "date_start": None,
                "date_end": None,
                "city": "Alsace",
                "distance_km": 50.0,
                "price": _extract_price(description),
                "description": description,
                "url": scrape_url,
                "source": source,
                "surprise_score": 0.0
            })

        return events

    except Exception as e:
        if verbose:
            print(f"  {source} scraping: ERREUR — {e}")
        return []


def _fetch_basel_agenda(verbose: bool = False) -> List[Dict]:
    """Récupère les événements Basel."""
    rss_url = "https://www.basel.com/de/feed"
    scrape_url = "https://www.basel.com/de/agenda"
    source = "Basel Agenda"
    events = []

    # Essayer RSS d'abord
    try:
        items = rss_reader.fetch_rss(rss_url)
        if items:
            if verbose:
                print(f"  {source} RSS: {len(items)} items")

            for item in items:
                title = item.get("title", "")
                if not title:
                    continue

                description = item.get("description", "")
                pub_date = item.get("published")

                events.append({
                    "title": title,
                    "category": _detect_category(title, description),
                    "date_start": pub_date.date() if isinstance(pub_date, datetime) else None,
                    "date_end": None,
                    "city": "Bâle",
                    "distance_km": _get_distance("Bâle"),
                    "price": _extract_price(description),
                    "description": description[:300] if description else "",
                    "url": item.get("link", ""),
                    "source": source,
                    "surprise_score": 0.0
                })

            return events
    except Exception:
        pass

    # Fallback scraping
    if verbose:
        print(f"  {source} RSS: KO → fallback scraping")

    try:
        resp = requests.get(scrape_url, headers=HEADERS, timeout=15)
        if verbose:
            print(f"  {source} scraping: HTTP {resp.status_code}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "lxml")

        for item in soup.select("article, .event, [class*='event'], .teaser"):
            title_el = item.select_one("h2, h3, .title")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            desc_el = item.select_one("p, .description")
            description = desc_el.get_text(strip=True)[:300] if desc_el else ""

            events.append({
                "title": title,
                "category": _detect_category(title, description),
                "date_start": None,
                "date_end": None,
                "city": "Bâle",
                "distance_km": _get_distance("Bâle"),
                "price": _extract_price(description),
                "description": description,
                "url": scrape_url,
                "source": source,
                "surprise_score": 0.0
            })

        return events

    except Exception as e:
        if verbose:
            print(f"  {source} scraping: ERREUR — {e}")
        return []


def _scrape_timeout_basel(verbose: bool = False) -> List[Dict]:
    """Scrape Timeout Basel."""
    url = "https://www.timeout.com/basel/things-to-do"
    source = "Timeout Basel"
    events = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if verbose:
            print(f"  {source} scraping: HTTP {resp.status_code}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "lxml")

        for item in soup.select("article, .card, [class*='tile'], [class*='article']"):
            title_el = item.select_one("h2, h3, .title, [class*='title']")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            desc_el = item.select_one("p, .description, [class*='summary']")
            description = desc_el.get_text(strip=True)[:300] if desc_el else ""
            link_el = item.select_one("a[href]")

            events.append({
                "title": title,
                "category": _detect_category(title, description),
                "date_start": None,
                "date_end": None,
                "city": "Bâle",
                "distance_km": _get_distance("Bâle"),
                "price": "NC",
                "description": description,
                "url": link_el.get("href", url) if link_el else url,
                "source": source,
                "surprise_score": 0.0
            })

        return events

    except Exception as e:
        if verbose:
            print(f"  {source} scraping: ERREUR — {e}")
        return []


# =============================================================================
# FONCTION PRINCIPALE
# =============================================================================

def get_discovery_events(period: Dict, verbose: bool = False) -> List[Dict]:
    """
    Récupère les événements "découverte" pour une période.

    Args:
        period: Dict avec start, end
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

    # Source 1 — JDS Mulhouse
    events = _fetch_jds_rss("mulhouse", verbose)
    if not events:
        events = _scrape_jds("mulhouse", verbose)
        stats["JDS Mulhouse"] = f"scraping ({len(events)})"
    else:
        stats["JDS Mulhouse"] = f"RSS ({len(events)})"
    all_events.extend(events)

    # Source 2 — JDS Colmar
    events = _fetch_jds_rss("colmar", verbose)
    if not events:
        events = _scrape_jds("colmar", verbose)
        stats["JDS Colmar"] = f"scraping ({len(events)})"
    else:
        stats["JDS Colmar"] = f"RSS ({len(events)})"
    all_events.extend(events)

    # Source 3 — Tourisme Alsace
    events = _fetch_tourisme_alsace(verbose)
    stats["Tourisme Alsace"] = f"{len(events)} events"
    all_events.extend(events)

    # Source 4 — Basel Agenda
    events = _fetch_basel_agenda(verbose)
    stats["Basel Agenda"] = f"{len(events)} events"
    all_events.extend(events)

    # Source 5 — Timeout Basel
    events = _scrape_timeout_basel(verbose)
    stats["Timeout Basel"] = f"scraping ({len(events)})"
    all_events.extend(events)

    if verbose:
        print()
        print("Résumé sources discovery:")
        for src, count in stats.items():
            print(f"  {src}: {count}")

    # Filtrer les titres invalides
    all_events = [e for e in all_events if e.get("title") and len(e["title"]) > 5]

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
            event["description"],
            event["date_start"],
            event["date_end"],
            start_date,
            end_date
        )

    # Trier par surprise_score décroissant
    unique_events.sort(key=lambda x: -x["surprise_score"])

    return unique_events


def format_discovery_context(events: List[Dict]) -> str:
    """Formate les événements discovery pour le contexte Claude."""
    if not events:
        return ""

    top_events = events[:4]
    lines = ["Bons plans / Découvertes :"]

    for event in top_events:
        date_str = event["date_start"].strftime("%d/%m") if event["date_start"] else "Date NC"
        price_str = f" | {event['price']}" if event["price"] != "NC" else ""

        lines.append(f"- [{event['category'].upper()}] {event['title']}")
        lines.append(f"  {event['city']} ({event['distance_km']:.0f}km) | {date_str}{price_str}")
        if event["description"]:
            desc = event["description"][:100] + "..." if len(event["description"]) > 100 else event["description"]
            lines.append(f"  {desc}")

    return "\n".join(lines)


def display_discovery(events: List[Dict]) -> None:
    """Affiche les événements discovery dans le terminal (pour debug)."""
    print(f"\n{'='*50}")
    print("DÉCOUVERTES / BONS PLANS")
    print(f"{'='*50}")

    if not events:
        print("Aucun événement trouvé")
        return

    # Stats par source
    sources = {}
    for e in events:
        src = e.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1

    print(f"\nSources : {sources}")
    print(f"Total : {len(events)} événements")

    # Stats par catégorie
    categories = {}
    for e in events:
        cat = e.get("category", "autre")
        categories[cat] = categories.get(cat, 0) + 1
    print(f"Catégories : {categories}")

    # Top 3 par surprise_score
    print(f"\n{'—'*50}")
    print("TOP 3 par surprise_score")
    print(f"{'—'*50}")

    for i, event in enumerate(events[:3], 1):
        date_str = event["date_start"].strftime("%d/%m/%Y") if event["date_start"] else "Date NC"

        print(f"\n{i}. [{event['category'].upper()}] {event['title']}")
        print(f"   Lieu : {event['city']} ({event['distance_km']:.0f}km)")
        print(f"   Date : {date_str} | Prix : {event['price']}")
        print(f"   Surprise score : {event['surprise_score']:.2f}")
        if event["description"]:
            print(f"   {event['description'][:80]}...")

    print(f"\n{'='*50}\n")
