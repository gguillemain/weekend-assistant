import anthropic
from datetime import datetime
from typing import Dict, List

from engine import calendar_engine
from collectors import weather, cinema, events, hiking


SYSTEM_PROMPT = """Tu es un assistant personnel de loisirs pour un couple
d'enseignants alsaciens (région Guebwiller, Haut-Rhin).
Ils ont passé la cinquantaine et cherchent à profiter
davantage de leur temps libre. Ils aiment le cinéma
Art & Essai, les expositions, les balades, la gastronomie,
les voyages. Leur rayon d'action habituel est 300km.
Tu proposes des idées concrètes, bien argumentées,
adaptées à la météo et aux événements réels fournis.
Tu n'inventes rien : tu t'appuies uniquement sur les
données fournies. Ton ton est chaleureux et direct,
pas trop formel.

Pour les suggestions de randonnée, utilise UNIQUEMENT
les données Visorando fournies. Ne jamais inventer
de randonnée. Si aucune donnée n'est disponible,
ne propose pas de randonnée."""


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


def _build_user_prompt(period: Dict, weather_data: Dict, movies: List[Dict], events_list: List[Dict], hikes: List[Dict]) -> str:
    """Construit le prompt utilisateur complet."""
    period_info = f"""Période : {period['label']}
Dates : du {period['start'].strftime('%d/%m/%Y')} au {period['end'].strftime('%d/%m/%Y')}
Durée : {period['days']} jours
Mode : {period['mode']}"""

    weather_context = _format_weather_context(weather_data)
    movies_context = _format_movies_context(movies)
    events_context = _format_events_context(events_list)
    hiking_context = _format_hiking_context(hikes)

    request = """Propose 3 à 5 suggestions pour cette période.
Chaque suggestion doit avoir :
- Un titre accrocheur
- Une description de 3-4 phrases expliquant l'activité
- Le jour recommandé (ou "flexible")
- Pourquoi c'est adapté à la météo
- Un niveau d'effort logistique : spontané / à réserver / à planifier

Privilégie la variété : mélange cinéma, randonnée, culture, gastronomie si possible."""

    return f"""{period_info}

{weather_context}

{movies_context}

{events_context}

{hiking_context}

{request}"""


def generate_suggestions(period: Dict) -> Dict:
    """
    Orchestre tous les collectors et appelle Claude API
    pour produire des suggestions structurées.
    """
    # 1. Collecter les données
    weather_data = weather.get_weather_forecast(period)
    movies = cinema.get_artetal_movies(period)
    events_list = events.get_local_events(period)
    hikes = hiking.get_hiking_suggestions(period, weather_data)

    # 2. Construire le contexte pour Claude
    user_prompt = _build_user_prompt(period, weather_data, movies, events_list, hikes)

    # 3. Appeler Claude API
    client = anthropic.Anthropic()

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )

    suggestions_text = message.content[0].text

    # 4. Retourner le résultat
    return {
        "period": period,
        "weather": weather_data,
        "movies": movies[:5],
        "events": events_list[:8],
        "hikes": hikes[:3],
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
