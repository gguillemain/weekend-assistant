import anthropic
import json
from datetime import datetime
from typing import Dict, List

from engine import calendar_engine, profile
from collectors import weather, cinema, events, hiking, travel, concerts


BASE_SYSTEM_PROMPT = """Tu es un assistant personnel de loisirs pour un couple
d'enseignants alsaciens (région Guebwiller, Haut-Rhin).
Ils ont passé la cinquantaine et cherchent à profiter
davantage de leur temps libre. Ils aiment le cinéma
Art & Essai, les expositions, les balades, la gastronomie,
les voyages et les concerts. Leur rayon d'action habituel est 300km.

Pour les concerts, mets en avant ceux dont le profile_match est > 0.3.
Si un artiste correspond exactement aux artistes favoris du profil,
signale-le explicitement dans ta suggestion.
Tu proposes des idées concrètes, bien argumentées,
adaptées à la météo et aux événements réels fournis.
Tu n'inventes rien : tu t'appuies uniquement sur les
données fournies. Ton ton est chaleureux et direct,
pas trop formel.

Pour les suggestions de randonnée, utilise UNIQUEMENT
les données Visorando fournies. Ne jamais inventer
de randonnée. Si aucune donnée n'est disponible,
ne propose pas de randonnée.

{profile_section}

IMPORTANT : Tu dois répondre UNIQUEMENT en JSON valide,
sans markdown, sans texte avant ou après. Pas de ```json, juste le JSON brut."""


VACATION_BASE_PROMPT = """Tu es un assistant personnel de voyages pour un couple
d'enseignants alsaciens (région Guebwiller, Haut-Rhin).
Ils ont passé la cinquantaine et profitent de leurs vacances
pour voyager. Ils aiment la culture, l'art, la gastronomie,
les belles villes européennes. Ils préfèrent les city breaks
authentiques aux destinations touristiques de masse.

Tu proposes des idées de voyages concrètes et réalisables,
basées UNIQUEMENT sur les destinations fournies.
Tu n'inventes pas de destinations. Ton ton est enthousiaste
mais réaliste, avec des conseils pratiques.

{profile_section}

IMPORTANT : Tu dois répondre UNIQUEMENT en JSON valide,
sans markdown, sans texte avant ou après. Pas de ```json, juste le JSON brut."""


def _build_profile_section() -> str:
    """Construit la section profil pour le prompt système."""
    user_profile = profile.get_profile()
    stats = profile.get_activity_stats()

    lines = ["Profil utilisateur :"]

    # Musique
    artists = user_profile.get("music_artists", [])
    genres = user_profile.get("music_genres", [])
    if artists or genres:
        lines.append(f"Musique appréciée : {', '.join(artists)}")
        lines.append(f"Genres : {', '.join(genres)}")

    # Expos
    expo_artists = user_profile.get("expo_artists", [])
    expo_style = user_profile.get("expo_style", "")
    fondations = user_profile.get("expo_fondations", [])
    if expo_artists:
        lines.append(f"Expos : artistes {', '.join(expo_artists)}, style {expo_style}")
    if fondations:
        lines.append(f"Fondations favorites : {', '.join(fondations)}")

    # Comportement récent
    lines.append("")
    lines.append("Comportement récent :")

    last_outing = stats.get("last_outing_days_ago", -1)
    if last_outing >= 0:
        lines.append(f"- Dernière vraie sortie : il y a {last_outing} jours")
    else:
        lines.append("- Aucune sortie enregistrée récemment")

    streak = stats.get("streak_home", 0)
    lines.append(f"- Semaines consécutives à la maison : {streak}")

    # Message de motivation si streak >= 3
    if streak >= 3:
        lines.append("")
        lines.append("IMPORTANT : Cela fait plusieurs semaines qu'ils restent à la maison.")
        lines.append("Commence tes suggestions par une phrase de motivation douce mais directe,")
        lines.append("sans culpabiliser, pour les encourager à sortir.")

    # Historique récent (films, concerts, expos)
    films_recent = stats.get("films_seen_recent", [])
    concerts_recent = stats.get("concerts_seen_recent", [])
    expos_recent = stats.get("expos_seen_recent", [])

    if films_recent or concerts_recent or expos_recent:
        lines.append("")
        lines.append("Historique récent :")
        if films_recent:
            lines.append(f"Films récemment vus : {', '.join(films_recent)}")
            lines.append("→ Ne pas reproposer ces films.")
        if concerts_recent:
            lines.append(f"Concerts récents : {', '.join(concerts_recent)}")
        if expos_recent:
            lines.append(f"Expos récentes : {', '.join(expos_recent)}")

    return "\n".join(lines)


def _format_weather_context(weather_data: Dict) -> str:
    """Formate les données météo pour le contexte."""
    if weather_data.get("error"):
        return f"Météo : données indisponibles ({weather_data['error']})"

    lines = [f"Météo à {weather_data['location']} :"]
    lines.append(f"Résumé : {weather_data['summary']}")
    lines.append(f"Meilleur jour : {weather_data['best_day']}")
    lines.append("")

    for day in weather_data.get("days", []):
        outdoor = "favorable aux sorties" if day["suitable_outdoor"] else "peu favorable aux sorties extérieures"
        lines.append(f"- {day['label']} ({day['date']}) : {day['temp_min']}°C à {day['temp_max']}°C, "
                     f"{day['description']}, pluie {day['rain_mm']}mm — {outdoor}")

    return "\n".join(lines)


def _format_movies_context(movies: List[Dict]) -> str:
    """Formate les films pour le contexte."""
    if not movies:
        return "Films : aucun film Art & Essai trouvé pour cette période."

    # Grouper par titre
    grouped = cinema.group_movies_by_title(movies)
    top_movies = [m for m in grouped if not m.get("family_film", False)][:5]

    lines = ["Films Art & Essai disponibles :"]

    for i, movie in enumerate(top_movies, 1):
        rating = f"{movie['press_rating']:.1f}/5" if movie.get("press_rating") else "N/A"
        cinemas_line = cinema.format_cinemas_line(movie.get("cinemas", []))

        labels = []
        if movie.get("telerama_pick"):
            labels.append("Télérama")
        if movie.get("cahiers_pick"):
            labels.append("Cahiers du Cinéma")
        label_str = f" (recommandé par {', '.join(labels)})" if labels else ""

        lines.append(f"{i}. {movie['title']}{label_str}")
        lines.append(f"   Réalisateur : {movie.get('director', 'NC')}")
        lines.append(f"   Note presse : {rating}")
        lines.append(f"   Cinémas : {cinemas_line}")
        if movie.get("synopsis"):
            synopsis = movie["synopsis"][:200] + "..." if len(movie.get("synopsis", "")) > 200 else movie.get("synopsis", "")
            lines.append(f"   Synopsis : {synopsis}")
        lines.append("")

    return "\n".join(lines)


def _format_events_context(events_list: List[Dict]) -> str:
    """Formate les événements pour le contexte."""
    if not events_list:
        return "Événements : aucun événement trouvé pour cette période."

    top_events = sorted(events_list, key=lambda e: -e.get("score", 0))[:8]

    lines = ["Événements locaux :"]

    for i, event in enumerate(top_events, 1):
        category = event.get("category", "autre").upper()
        distance = event.get("distance_km", 0)
        price = event.get("price", "NC")
        city = event.get("city", "NC")

        lines.append(f"{i}. [{category}] {event['title']}")
        lines.append(f"   Lieu : {city} ({distance:.0f} km)")
        lines.append(f"   Prix : {price}")
        if event.get("description"):
            desc = event["description"][:150] + "..." if len(event.get("description", "")) > 150 else event.get("description", "")
            lines.append(f"   Description : {desc}")
        lines.append("")

    return "\n".join(lines)


def _format_hiking_context(hikes: List[Dict]) -> str:
    """Formate les randonnées pour le contexte."""
    if not hikes:
        return "Randonnées : aucune randonnée disponible (données Visorando indisponibles)."

    top_hikes = hikes[:3]

    lines = ["Randonnées disponibles (dénivelé max 300m) :"]

    for hike in top_hikes:
        rating_str = f"{hike['rating']:.1f}/5" if hike.get("rating", 0) > 0 else "N/A"
        loop_str = "boucle" if hike.get("loop") else "aller-retour"

        lines.append(f"- {hike['title']} — {hike['distance_km']:.1f}km, {hike['duration_h']:.1f}h, {hike['elevation_gain']}m D+")
        lines.append(f"  Départ : {hike.get('start_city', 'NC')} ({hike['distance_from_home']:.0f}km de Guebwiller)")
        lines.append(f"  Terrain : {hike['terrain']} | Note : {rating_str} | {loop_str}")
        lines.append("")

    return "\n".join(lines)


def _build_vacation_prompt(period: Dict, travel_data: Dict) -> str:
    """Construit le prompt utilisateur pour les vacances."""
    period_info = f"""Période : {period['label']}
Dates : du {period['start'].strftime('%d/%m/%Y')} au {period['end'].strftime('%d/%m/%Y')}
Durée : {period['days']} jours"""

    travel_context = travel.format_travel_context(travel_data)

    request = """Propose 3 à 4 idées de voyage pour ces vacances.

Réponds UNIQUEMENT en JSON valide avec ce format exact :
{
  "intro": "phrase d'accroche enthousiaste pour ces vacances",
  "suggestions": [
    {
      "emoji": "🇮🇹",
      "title": "Escapade à [Ville]",
      "description": "Description de 3-4 phrases expliquant pourquoi cette destination est idéale, ce qu'il y a à voir/faire, et des conseils pratiques.",
      "day": "3-4 jours",
      "logistics": "Train direct",
      "type": "voyage",
      "destination": "Ville, Pays"
    }
  ]
}

Valeurs possibles :
- day : durée suggérée ("2-3 jours", "4-5 jours", "1 semaine")
- logistics : mode de transport ("Train", "Avion", "Voiture", "Train direct")
- type : toujours "voyage"

Mélange city breaks proches et destinations plus lointaines si la durée le permet."""

    return f"""{period_info}

{travel_context}

{request}"""


def _build_user_prompt(period: Dict, weather_data: Dict, movies: List[Dict], events_list: List[Dict], hikes: List[Dict], concerts_list: List[Dict] = None) -> str:
    """Construit le prompt utilisateur complet."""
    period_info = f"""Période : {period['label']}
Dates : du {period['start'].strftime('%d/%m/%Y')} au {period['end'].strftime('%d/%m/%Y')}
Durée : {period['days']} jours
Mode : {period['mode']}"""

    weather_context = _format_weather_context(weather_data)
    movies_context = _format_movies_context(movies)
    events_context = _format_events_context(events_list)
    hiking_context = _format_hiking_context(hikes)
    concerts_context = concerts.format_concerts_context(concerts_list) if concerts_list else ""

    request = """Propose 3 à 5 suggestions pour cette période.

Réponds UNIQUEMENT en JSON valide avec ce format exact :
{
  "intro": "phrase d'accroche courte pour le week-end",
  "suggestions": [
    {
      "emoji": "🎬",
      "title": "Titre accrocheur",
      "description": "Description de 3-4 phrases expliquant l'activité et pourquoi c'est adapté à la météo.",
      "day": "Samedi",
      "logistics": "Spontané",
      "type": "cinema"
    }
  ]
}

Valeurs possibles :
- day : "Samedi", "Dimanche", "Lundi", "Flexible"
- logistics : "Spontané", "À réserver", "À planifier"
- type : "cinema", "rando", "culture", "gastronomie", "concert", "autre"

Privilégie la variété : mélange cinéma, randonnée, culture, concert, gastronomie si possible."""

    return f"""{period_info}

{weather_context}

{movies_context}

{events_context}

{hiking_context}

{concerts_context}

{request}"""


def generate_suggestions(period: Dict) -> Dict:
    """
    Orchestre tous les collectors et appelle Claude API
    pour produire des suggestions structurées.
    """
    is_vacation = period.get("mode") == "vacances"

    # Construire la section profil pour le prompt
    profile_section = _build_profile_section()

    if is_vacation:
        # Mode vacances : suggestions voyage
        travel_data = travel.get_travel_suggestions(period)
        user_prompt = _build_vacation_prompt(period, travel_data)
        system_prompt = VACATION_BASE_PROMPT.format(profile_section=profile_section)

        # Données minimales pour le template
        weather_data = {}
        movies = []
        events_list = []
        hikes = []
        concerts_list = []
    else:
        # Mode week-end : suggestions locales
        user_profile = profile.get_profile()
        weather_data = weather.get_weather_forecast(period)
        movies = cinema.get_artetal_movies(period)
        events_list = events.get_local_events(period)
        hikes = hiking.get_hiking_suggestions(period, weather_data)
        concerts_list = concerts.get_concerts(period, user_profile)
        user_prompt = _build_user_prompt(period, weather_data, movies, events_list, hikes, concerts_list)
        system_prompt = BASE_SYSTEM_PROMPT.format(profile_section=profile_section)
        travel_data = {}

    # Appeler Claude API
    client = anthropic.Anthropic()

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )

    raw_response = message.content[0].text

    # 4. Parser le JSON
    suggestions = []
    intro = ""
    suggestions_text = raw_response  # Fallback

    try:
        # Nettoyer les éventuels backticks markdown
        clean = raw_response.strip()
        if clean.startswith("```"):
            clean = clean.lstrip("```json").lstrip("```")
        if clean.endswith("```"):
            clean = clean.rstrip("```")
        clean = clean.strip()

        result = json.loads(clean)
        suggestions = result.get("suggestions", [])
        intro = result.get("intro", "")
        suggestions_text = None  # Plus besoin du texte brut

    except json.JSONDecodeError as e:
        print(f"  ⚠ Erreur parsing JSON Claude: {e}")
        print(f"  Réponse brute: {raw_response[:200]}...")
        # Fallback : on garde le texte brut
        suggestions = []

    # 5. Retourner le résultat
    return {
        "period": period,
        "weather": weather_data,
        "movies": movies[:5] if movies else [],
        "events": events_list[:8] if events_list else [],
        "hikes": hikes[:3] if hikes else [],
        "concerts": concerts_list[:5] if concerts_list else [],
        "travel": travel_data if is_vacation else {},
        "is_vacation": is_vacation,
        "suggestions": suggestions,
        "intro": intro,
        "suggestions_text": suggestions_text,
        "generated_at": datetime.now()
    }


def get_suggestions_for_next_period() -> Dict:
    """Raccourci pour obtenir les suggestions de la prochaine période."""
    next_period = calendar_engine.get_next_period()
    if not next_period:
        return {
            "error": "Aucune période à venir trouvée",
            "generated_at": datetime.now()
        }
    return generate_suggestions(next_period)
