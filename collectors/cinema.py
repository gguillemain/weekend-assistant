import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
import re
import time

from collectors.rss_reader import fetch_rss, try_rss_urls
from engine.cache import cache_get, cache_set, CACHE_TTL

# Session HTTP réutilisable (connection pooling)
_session = requests.Session()


# Configuration des cinémas à scraper
CINEMAS = [
    {
        "name": "Le Florival",
        "city": "Guebwiller",
        "distance_km": 0,
        "url": "https://www.allocine.fr/seance/salle_gen_csalle=P0961.html"
    },
    {
        "name": "Bel-Air",
        "city": "Mulhouse",
        "distance_km": 25,
        "url": "https://www.allocine.fr/seance/salle_gen_csalle=P0663.html"
    },
    {
        "name": "Cinéma Le Palace",
        "city": "Colmar",
        "distance_km": 30,
        "url": "https://www.allocine.fr/seance/salle_gen_csalle=P0203.html"
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Cache pour les recommandations éditoriales
TELERAMA_PICKS: Dict[str, int] = {}  # {titre_normalisé: étoiles}
CAHIERS_PICKS: Set[str] = set()  # {titre_normalisé}

# Statut des sources
SOURCES_STATUS = {
    "telerama": {"method": None, "count": 0},
    "cahiers": {"method": None, "count": 0}
}


# Mots-clés STRICTS pour détecter les films familiaux (dans le titre uniquement)
FAMILY_TITLE_KEYWORDS = [
    "mario", "disney", "pixar", "dreamworks", "illumination",
    "sonic", "pokemon", "pokémon", "lego", "minions", "paw patrol",
    "pat patrouille", "winnie", "reine des neiges", "frozen",
    "vaiana", "moana", "encanto", "shrek", "kung fu panda"
]

# Mots-clés pour les genres (si trouvés dans les labels de genre)
FAMILY_GENRE_KEYWORDS = ["animation", "famille", "enfants"]


def _is_family_film(title: str, genres: str = "") -> bool:
    """
    Détecte si un film est un film familial/enfants.
    Basé sur le titre ET les genres, pas sur le texte complet de la page.
    """
    title_lower = title.lower()
    genres_lower = genres.lower() if genres else ""

    # 1. Mots-clés stricts dans le titre
    for keyword in FAMILY_TITLE_KEYWORDS:
        if keyword in title_lower:
            return True

    # 2. Genre "Animation" ou "Famille" explicite
    for genre_kw in FAMILY_GENRE_KEYWORDS:
        if genre_kw in genres_lower:
            return True

    # 3. Pattern "X Le Film" avec mot-clé enfant
    if re.search(r'\b(le film|the movie)\b', title_lower):
        for kid_pattern in FAMILY_TITLE_KEYWORDS:
            if kid_pattern in title_lower:
                return True

    return False


def _normalize_title(title: str) -> str:
    """Normalise un titre pour la comparaison."""
    title = title.lower().strip()
    replacements = {
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'à': 'a', 'â': 'a', 'ä': 'a',
        'ù': 'u', 'û': 'u', 'ü': 'u',
        'î': 'i', 'ï': 'i',
        'ô': 'o', 'ö': 'o',
        'ç': 'c',
        "'": "", "'": "", ":": "", "-": " ", "–": " ", "—": " "
    }
    for old, new in replacements.items():
        title = title.replace(old, new)
    title = re.sub(r'[^\w\s]', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()


def _extract_film_title_from_rss(item: Dict) -> Optional[str]:
    """Extrait le titre du film entre guillemets depuis un item RSS."""
    title = item.get("title", "")
    if not title:
        return None

    # Extraire le titre entre guillemets (format Télérama : "Titre du film")
    match = re.search(r'[«""]([^»""]+)[»""]', title)
    if match:
        return match.group(1).strip()

    return None


def _has_positive_rating(item: Dict) -> tuple:
    """
    Vérifie si un item RSS contient un indicateur de note EXPLICITE positif.
    Retourne (has_rating, stars) où stars est 4 ou 5.
    """
    title = item.get("title", "")
    desc = item.get("description", "")
    full_text = title + " " + desc

    # Patterns STRICTS pour les notations explicites
    # ★★★★ ou ★★★★★ (4-5 étoiles unicode)
    stars_match = re.search(r'[★]{4,5}', full_text)
    if stars_match:
        return True, len(stars_match.group())

    # "4 étoiles" ou "5 étoiles" (texte explicite)
    etoiles_match = re.search(r'\b([45])\s*[ée]toiles?\b', full_text, re.IGNORECASE)
    if etoiles_match:
        return True, int(etoiles_match.group(1))

    # "Télérama recommande" ou "coup de cœur"
    if re.search(r'télérama\s+recommande', full_text, re.IGNORECASE):
        return True, 4

    if re.search(r'coup\s+de\s+c[oœ]ur', full_text, re.IGNORECASE):
        return True, 5

    # "chef-d'œuvre" dans le contexte d'une critique (pas juste mentionné)
    if re.search(r'\b(un|ce|vrai|pur)\s+chef.d.[oœ]uvre\b', full_text, re.IGNORECASE):
        return True, 5

    # "à voir absolument" / "incontournable" dans un contexte de recommandation
    if re.search(r'\bà voir absolument\b', full_text, re.IGNORECASE):
        return True, 4

    # PAS de correspondance : ne pas retourner de faux positif
    return False, 0


def fetch_telerama_picks() -> Dict[str, int]:
    """
    Récupère les recommandations Télérama via RSS.
    STRICT : seuls les films avec notation EXPLICITE (★★★★, "4 étoiles", etc.) sont retenus.
    """
    global TELERAMA_PICKS, SOURCES_STATUS

    rss_urls = [
        "https://www.telerama.fr/rss/cinema.xml",
        "https://www.telerama.fr/feeds/cinema.xml",
        "https://www.telerama.fr/cinema/rss"
    ]

    items, used_url = try_rss_urls(rss_urls)

    if items:
        picks = {}
        for item in items:
            # 1. L'item doit contenir une notation EXPLICITE positive
            has_rating, stars = _has_positive_rating(item)
            if not has_rating:
                continue  # Ignorer les items sans notation explicite

            # 2. Extraire le titre du film (entre guillemets uniquement)
            film_title = _extract_film_title_from_rss(item)
            if not film_title or len(film_title) < 2:
                continue

            normalized = _normalize_title(film_title)
            picks[normalized] = stars

        TELERAMA_PICKS = picks
        SOURCES_STATUS["telerama"] = {"method": "RSS", "count": len(picks)}
        return picks

    # Fallback scraping si RSS échoue
    SOURCES_STATUS["telerama"] = {"method": "scraping", "count": 0}
    return _scrape_telerama_fallback()


def _scrape_telerama_fallback() -> Dict[str, int]:
    """
    Fallback scraping pour Télérama.
    STRICT : cherche uniquement les films avec notation visible (étoiles, badges).
    """
    global TELERAMA_PICKS, SOURCES_STATUS

    urls = [
        "https://www.telerama.fr/cinema/films/sorties-de-la-semaine",
        "https://www.telerama.fr/cinema"
    ]

    for url in urls:
        try:
            response = _session.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, "lxml")
                picks = {}

                # Chercher les éléments avec notation visible
                film_cards = soup.select("article, [class*='film'], [class*='movie'], .card")

                for card in film_cards:
                    # Chercher une notation EXPLICITE dans la carte
                    card_text = card.get_text()

                    # Compter les étoiles visuelles
                    stars = 0
                    star_elems = card.select("[class*='star'], [class*='etoile'], svg[class*='star']")
                    if star_elems:
                        # Compter les étoiles pleines/actives
                        for star in star_elems:
                            classes = " ".join(star.get("class", []))
                            if "full" in classes or "active" in classes or "filled" in classes:
                                stars += 1
                        if stars == 0:
                            stars = len(star_elems)  # Si pas de distinction, compter tout

                    # Ou chercher "★★★★" dans le texte
                    if stars == 0:
                        star_match = re.search(r'[★]{4,5}', card_text)
                        if star_match:
                            stars = len(star_match.group())

                    # Ignorer si moins de 4 étoiles
                    if stars < 4:
                        continue

                    # Extraire le titre
                    title_elem = card.select_one("h2, h3, h4, .title, [class*='title'] a")
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    if not title or len(title) < 2:
                        continue

                    normalized = _normalize_title(title)
                    picks[normalized] = stars

                if picks:
                    TELERAMA_PICKS = picks
                    SOURCES_STATUS["telerama"]["count"] = len(picks)
                    return picks

        except Exception:
            continue

    return {}


def fetch_cahiers_picks() -> Set[str]:
    """Récupère les recommandations des Cahiers du Cinéma via RSS."""
    global CAHIERS_PICKS, SOURCES_STATUS

    # URLs RSS Cahiers du Cinéma à essayer
    rss_urls = [
        "https://www.cahiersducinema.com/feed/",
        "https://www.cahiersducinema.com/rss/",
        "https://www.cahiersducinema.com/feed",
        "https://www.cahiersducinema.com/rss",
        "https://www.cahiersducinema.com/critiques/feed/"
    ]

    items, used_url = try_rss_urls(rss_urls)

    if items:
        picks = set()
        for item in items:
            title = _extract_film_title_from_rss(item)
            if not title or len(title) < 2:
                continue

            # Vérifier si c'est une critique de film
            categories = [c.lower() for c in item.get("categories", [])]
            text = (item.get("title", "") + " " + item.get("description", "")).lower()

            is_film_review = (
                "film" in categories or
                "critique" in categories or
                "cinéma" in categories or
                "critique" in text or
                "film" in text
            )

            if is_film_review:
                normalized = _normalize_title(title)
                picks.add(normalized)

        CAHIERS_PICKS = picks
        SOURCES_STATUS["cahiers"] = {"method": "RSS", "count": len(picks)}
        return picks

    # Fallback scraping
    SOURCES_STATUS["cahiers"] = {"method": "scraping", "count": 0}
    return _scrape_cahiers_fallback()


def _scrape_cahiers_fallback() -> Set[str]:
    """Fallback scraping pour Cahiers du Cinéma."""
    global CAHIERS_PICKS, SOURCES_STATUS

    url = "https://www.cahiersducinema.com/critiques-de-films/"

    try:
        response = _session.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "lxml")
            picks = set()

            articles = soup.select("article, .article, .post, .critique, [class*='film'], .card")

            for article in articles:
                title_elem = article.select_one("h2, h3, h4, .title, [class*='title'] a")
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                if title and len(title) >= 2:
                    normalized = _normalize_title(title)
                    picks.add(normalized)

            if picks:
                CAHIERS_PICKS = picks
                SOURCES_STATUS["cahiers"]["count"] = len(picks)

    except Exception:
        pass

    return CAHIERS_PICKS


def get_telerama_info(title: str) -> Tuple[bool, Optional[int]]:
    """
    Vérifie si un film est dans les recommandations Télérama.
    Correspondance STRICTE : le titre normalisé doit correspondre exactement
    ou être contenu entièrement (pas de match partiel sur quelques mots).
    """
    if not TELERAMA_PICKS:
        return False, None

    normalized = _normalize_title(title)

    # Match exact
    if normalized in TELERAMA_PICKS:
        return True, TELERAMA_PICKS[normalized]

    # Match si le titre Allocine est contenu exactement dans un titre Télérama
    # (ex: "Autofiction" dans "Autofiction de Pedro Almodovar")
    for telerama_title, stars in TELERAMA_PICKS.items():
        # Le titre doit être substantiel (> 5 chars) et correspondre en entier
        if len(normalized) > 5 and normalized == telerama_title:
            return True, stars
        # Ou le titre Télérama commence/finit par le titre Allocine
        if len(normalized) > 5 and (
            telerama_title.startswith(normalized + " ") or
            telerama_title.endswith(" " + normalized)
        ):
            return True, stars

    return False, None


def get_cahiers_info(title: str) -> bool:
    """Vérifie si un film est dans les recommandations des Cahiers."""
    normalized = _normalize_title(title)

    if normalized in CAHIERS_PICKS:
        return True

    # Correspondance souple
    for cahiers_title in CAHIERS_PICKS:
        if normalized in cahiers_title or cahiers_title in normalized:
            return True
        # Correspondance par mots
        norm_words = set(normalized.split())
        cah_words = set(cahiers_title.split())
        if len(norm_words & cah_words) >= min(2, len(norm_words)):
            return True

    return False


def get_artetal_movies(period: Dict) -> List[Dict]:
    """Récupère les films Art & Essai des cinémas proches de Guebwiller."""
    period_start = period["start"]
    period_end = period["end"]

    # Clé de cache
    cache_key = f"cinema_{period_start}_{period_end}"

    # Vérifier le cache
    cached = cache_get(cache_key)
    if cached:
        print("  Cinéma : CACHE HIT")
        filtered_movies = cached
    else:
        print("  Cinéma : CACHE MISS → scraping")

        # Récupérer les recommandations éditoriales
        fetch_telerama_picks()
        fetch_cahiers_picks()

        # Afficher le statut des sources
        _print_sources_status()

        all_movies = []

        for cinema in CINEMAS:
            try:
                movies = _scrape_cinema(cinema, period_start, period_end)
                all_movies.extend(movies)
            except Exception as e:
                print(f"⚠ Erreur scraping {cinema['name']}: {e}")
                continue

            time.sleep(0.5)

        # Ajouter les infos éditoriales à chaque film
        for movie in all_movies:
            is_telerama, stars = get_telerama_info(movie["title"])
            movie["telerama_pick"] = is_telerama
            movie["telerama_stars"] = stars
            movie["cahiers_pick"] = get_cahiers_info(movie["title"])

        # Filtrer les films intéressants
        filtered_movies = [
            m for m in all_movies
            if m["telerama_pick"] or m["cahiers_pick"] or m["art_et_essai"] or (m["press_rating"] and m["press_rating"] >= 3.5)
        ]

        # Tri multi-critères
        def sort_key(movie):
            priority = 0
            if movie["telerama_pick"] and movie["cahiers_pick"]:
                priority = 2000 + (movie["telerama_stars"] or 0) * 100 + (movie["press_rating"] or 0) * 10
            elif movie["telerama_pick"]:
                priority = 1500 + (movie["telerama_stars"] or 0) * 100 + (movie["press_rating"] or 0) * 10
            elif movie["cahiers_pick"]:
                priority = 1000 + (movie["press_rating"] or 0) * 10
            elif movie["art_et_essai"] and movie["press_rating"] and movie["press_rating"] >= 3.5:
                priority = 500 + (movie["press_rating"] or 0) * 10
            else:
                priority = (movie["press_rating"] or 0) * 10
            return -priority

        filtered_movies.sort(key=sort_key)

        # Mettre en cache les données AVANT déduplication
        if filtered_movies:
            cache_set(cache_key, filtered_movies, CACHE_TTL.get("cinema", 360))

    # Déduplication TOUJOURS appliquée (cache ou pas)
    from engine.profile import get_seen_items_normalized, normalize_for_matching

    seen_films = get_seen_items_normalized('films', days=365)

    def is_film_seen(title: str) -> bool:
        """Vérifie si un film a été vu (matching partiel)."""
        normalized = normalize_for_matching(title)
        if normalized in seen_films:
            return True
        for seen in seen_films:
            if seen in normalized or normalized in seen:
                return True
        return False

    deduplicated = []
    for movie in filtered_movies:
        if not is_film_seen(movie["title"]):
            deduplicated.append(movie)
        else:
            print(f"  [SKIP] Film déjà vu : {movie['title']}")

    print(f"  Cinéma : {len(deduplicated)} films après déduplication")

    return deduplicated


def _print_sources_status():
    """Affiche le statut des sources éditoriales."""
    parts = []
    for source, status in SOURCES_STATUS.items():
        method = status["method"]
        count = status["count"]
        if method:
            parts.append(f"{source.capitalize()} [{method}] ({count})")
        else:
            parts.append(f"{source.capitalize()} [N/A]")

    print(f"  Sources cinéma : {' | '.join(parts)}")


def _scrape_cinema(cinema: Dict, period_start: date, period_end: date) -> List[Dict]:
    """Scrape les séances d'un cinéma pour la période donnée."""
    base_url = cinema["url"]
    current_date = period_start
    movies_by_title = {}

    while current_date <= period_end:
        date_str = current_date.strftime("%Y-%m-%d")

        try:
            response = _session.get(base_url, headers=HEADERS, timeout=10, params={"d": date_str})
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "lxml")

            day_movies = _parse_cinema_page(soup, cinema, current_date)

            for movie in day_movies:
                title = movie["title"]
                if title in movies_by_title:
                    movies_by_title[title]["showtimes"].extend(movie["showtimes"])
                else:
                    movies_by_title[title] = movie

        except requests.exceptions.RequestException as e:
            print(f"  ⚠ Erreur requête {cinema['name']} ({date_str}): {e}")

        current_date += timedelta(days=1)
        time.sleep(0.3)

    return list(movies_by_title.values())


def _parse_cinema_page(soup: BeautifulSoup, cinema: Dict, show_date: date) -> List[Dict]:
    """Parse une page de séances Allocine."""
    movies = []

    movie_cards = soup.select(".card.entity-card, .movie-card, .hred, .mdl")
    if not movie_cards:
        movie_cards = soup.select("[class*='movie'], [class*='film'], .showtimes-movie")
    if not movie_cards:
        movie_cards = soup.select(".item-seances, .showtimes-item")

    for card in movie_cards:
        try:
            movie = _parse_movie_card(card, cinema, show_date)
            if movie and movie["title"]:
                movies.append(movie)
        except Exception:
            continue

    return movies


def _parse_movie_card(card: BeautifulSoup, cinema: Dict, show_date: date) -> Optional[Dict]:
    """Parse une carte de film individuelle."""
    title_elem = card.select_one("a.meta-title, .title a, h2 a, .meta-title-link, a[href*='/film/']")
    if not title_elem:
        title_elem = card.select_one("a")
    if not title_elem:
        return None

    title = title_elem.get_text(strip=True)
    allocine_url = title_elem.get("href", "")
    if allocine_url and not allocine_url.startswith("http"):
        allocine_url = f"https://www.allocine.fr{allocine_url}"

    director = ""
    director_elem = card.select_one(".meta-body-direction, .director, [class*='director']")
    if director_elem:
        director = director_elem.get_text(strip=True)
        director = re.sub(r"^[Dd]e\s*", "", director).strip()

    duration_min = 0
    duration_elem = card.select_one(".meta-body-info, .duration, [class*='duration']")
    if duration_elem:
        duration_text = duration_elem.get_text()
        duration_match = re.search(r"(\d+)h\s*(\d+)?", duration_text)
        if duration_match:
            hours = int(duration_match.group(1))
            minutes = int(duration_match.group(2) or 0)
            duration_min = hours * 60 + minutes

    synopsis = ""
    synopsis_elem = card.select_one(".synopsis, .content-txt, [class*='synopsis']")
    if synopsis_elem:
        synopsis = synopsis_elem.get_text(strip=True)[:300]

    press_rating = _extract_rating(card, "press")
    public_rating = _extract_rating(card, "public")

    art_et_essai = False
    labels = card.select(".label, .tag, [class*='label']")
    for label in labels:
        label_text = label.get_text(strip=True).lower()
        if "art" in label_text and "essai" in label_text:
            art_et_essai = True
            break
    card_classes = " ".join(card.get("class", []))
    if "art-et-essai" in card_classes or "art-essai" in card_classes:
        art_et_essai = True

    showtimes = _extract_showtimes(card, show_date)

    # Extraire les genres/labels pour la détection de films familiaux
    genres_text = ""
    genre_elems = card.select(".meta-body-info, .genres, .label, .tag, [class*='genre']")
    for elem in genre_elems:
        genres_text += " " + elem.get_text(strip=True).lower()

    # Détecter les films familiaux (basé sur titre + genres uniquement)
    family_film = _is_family_film(title, genres_text)

    return {
        "cinema": cinema["name"],
        "city": cinema["city"],
        "distance_km": cinema["distance_km"],
        "title": title,
        "director": director,
        "duration_min": duration_min,
        "synopsis": synopsis,
        "press_rating": press_rating,
        "public_rating": public_rating,
        "art_et_essai": art_et_essai,
        "showtimes": showtimes,
        "allocine_url": allocine_url,
        "telerama_pick": False,
        "telerama_stars": None,
        "cahiers_pick": False,
        "family_film": family_film
    }


def _extract_rating(card: BeautifulSoup, rating_type: str) -> Optional[float]:
    """Extrait une note (presse ou public) de la carte."""
    if rating_type == "press":
        selectors = [".rating-item.press .stareval-note", "[class*='press'] .stareval-note",
                     ".rating-mdl .rating-item:first-child .stareval-note"]
    else:
        selectors = [".rating-item.public .stareval-note", "[class*='public'] .stareval-note",
                     ".rating-mdl .rating-item:last-child .stareval-note"]

    for selector in selectors:
        elem = card.select_one(selector)
        if elem:
            try:
                rating_text = elem.get_text(strip=True).replace(",", ".")
                return float(rating_text)
            except ValueError:
                continue

    rating_elems = card.select(".stareval-note, .rating-value, [class*='rating'] span")
    for elem in rating_elems:
        try:
            rating_text = elem.get_text(strip=True).replace(",", ".")
            rating = float(rating_text)
            if 0 <= rating <= 5:
                return rating
        except ValueError:
            continue

    return None


def _extract_showtimes(card: BeautifulSoup, show_date: date) -> List[str]:
    """Extrait les horaires de séances."""
    showtimes = []
    date_str = show_date.strftime("%d/%m")

    time_elems = card.select(".showtimes-hour, .showtime, .time, [class*='seance'] span, .txt-item")

    for elem in time_elems:
        time_text = elem.get_text(strip=True)
        time_match = re.search(r"(\d{1,2})[h:](\d{2})", time_text)
        if time_match:
            hour = time_match.group(1).zfill(2)
            minute = time_match.group(2)
            showtimes.append(f"{date_str} {hour}:{minute}")

    return showtimes


def group_movies_by_title(movies: List[Dict]) -> List[Dict]:
    """Groupe les films par titre et agrège les cinémas."""
    grouped = {}

    for movie in movies:
        title = movie["title"]
        if title not in grouped:
            grouped[title] = {
                **movie,
                "cinemas": [{
                    "name": movie["cinema"],
                    "city": movie["city"],
                    "distance_km": movie["distance_km"],
                    "showtimes": movie["showtimes"]
                }]
            }
        else:
            grouped[title]["cinemas"].append({
                "name": movie["cinema"],
                "city": movie["city"],
                "distance_km": movie["distance_km"],
                "showtimes": movie["showtimes"]
            })

    result = []
    for movie in grouped.values():
        movie["cinemas"].sort(key=lambda c: c["distance_km"])
        result.append(movie)

    return result


def format_cinemas_line(cinemas: List[Dict]) -> str:
    """Formate la liste des cinémas sur une ligne."""
    parts = []
    for c in cinemas:
        if c["city"] == "Guebwiller":
            parts.append(c["name"])
        else:
            parts.append(f"{c['name']} ({c['city']})")
    return " + ".join(parts)


def get_movies_summary(movies: List[Dict]) -> Dict:
    """Génère un résumé des films avec groupement par titre."""
    grouped = group_movies_by_title(movies)

    by_cinema = {}
    for movie in movies:
        cinema_name = movie["cinema"]
        if cinema_name not in by_cinema:
            by_cinema[cinema_name] = 0
        by_cinema[cinema_name] += 1

    # Filtrer les films familiaux pour le top
    non_family_films = [m for m in grouped if not m.get("family_film", False)]

    return {
        "total_entries": len(movies),
        "unique_films": len(grouped),
        "family_films": len(grouped) - len(non_family_films),
        "telerama_count": SOURCES_STATUS["telerama"]["count"],
        "cahiers_count": SOURCES_STATUS["cahiers"]["count"],
        "by_cinema": by_cinema,
        "top_movies": non_family_films[:3]  # Exclure les films familiaux du top
    }


def get_editorial_sources_line() -> str:
    """Retourne la ligne de résumé des sources éditoriales."""
    parts = []
    for source, status in SOURCES_STATUS.items():
        method = status["method"] or "N/A"
        count = status["count"]
        parts.append(f"{source.capitalize()} [{method}] ({count})")
    return "Sources éditoriales : " + " | ".join(parts)
