"""
Moteur de génération de suggestions de voyage.
Orchestre les collectors flights, citybreaks et roadtrips,
puis appelle Claude pour générer des recommandations personnalisées.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional

import anthropic

import config
from collectors.travel_flights import get_cheap_flights, format_flights_context
from collectors.travel_citybreaks import get_citybreaks, format_citybreaks_context
from collectors.travel_roadtrips import get_roadtrips, format_roadtrips_context
from engine.profile import get_profile, get_activity_stats


# =============================================================================
# CONFIGURATION
# =============================================================================

TRAVEL_SYSTEM_PROMPT = """Tu es un conseiller voyage pour un couple d'enseignants alsaciens d'une cinquantaine d'années, habitant Guebwiller (Haut-Rhin).

Leur profil :
- Budget raisonnable, pas de luxe mais confort correct
- Ils aiment : culture, musique (The Cure, Pulp, Fontaines D.C., Bertrand Belin), expositions d'art (Soulages, Banksy, art contemporain), gastronomie, nature douce
- Géraldine adore Londres (concerts, musées, ambiance)
- Aéroport : Basel-Mulhouse (BSL/EAP), à 45min de chez eux
- Pas de voiture de location préférée, ils préfèrent leur propre voiture ou les transports locaux

Tes recommandations doivent être :
- Concrètes avec budget estimé réaliste (vol + hôtel + sur place)
- Adaptées à la saison et à la durée des vacances
- Variées (mix avion et voiture si pertinent)
- Avec un conseil de timing pour réserver (combien de temps à l'avance)

Format JSON attendu pour chaque suggestion :
{
  "destination": "Nom de la ville/région",
  "country": "Pays",
  "transport": "avion" ou "voiture",
  "duration_days": 4,
  "budget_total": "800€",
  "budget_breakdown": {
    "transport": "150€ (vol Ryanair A/R)" ou "120€ (essence + péages)",
    "hotel": "400€ (4 nuits, hôtel 3*)",
    "sur_place": "250€ (repas, visites, transports)"
  },
  "best_booking_time": "6 semaines avant pour les meilleurs tarifs vols",
  "highlights": ["Point d'intérêt 1", "Point d'intérêt 2", "Point d'intérêt 3"],
  "why_now": "Explication de pourquoi cette destination est idéale pour cette période",
  "practical_tip": "Un conseil pratique utile"
}"""


def _get_season_name(dt: datetime) -> str:
    """Retourne le nom de la saison en français."""
    month = dt.month
    if month in [3, 4, 5]:
        return "printemps"
    elif month in [6, 7, 8]:
        return "été"
    elif month in [9, 10, 11]:
        return "automne"
    else:
        return "hiver"


def _build_travel_prompt(
    vacation_period: Dict,
    flights: List[Dict],
    citybreaks: List[Dict],
    roadtrips: List[Dict],
    profile: Dict
) -> str:
    """Construit le prompt utilisateur pour Claude."""

    start = vacation_period.get("start", "")
    end = vacation_period.get("end", "")
    days = vacation_period.get("days", 7)
    label = vacation_period.get("label", "Vacances")

    if isinstance(start, str):
        start_dt = datetime.strptime(start, "%Y-%m-%d")
    else:
        start_dt = datetime.combine(start, datetime.min.time())

    season = _get_season_name(start_dt)

    # Formater les vols
    flights_text = format_flights_context(flights, limit=5)

    # Formater les city-breaks (top 3)
    top_citybreaks = citybreaks[:3]
    citybreaks_lines = []
    for city in top_citybreaks:
        flight_info = ""
        if city.get("flight_info"):
            fi = city["flight_info"]
            flight_info = f" — Vol {fi['airline']} : {fi['price']:.0f}€ A/R"

        tags = ", ".join(city.get("tags", [])[:5])
        citybreaks_lines.append(
            f"- {city['destination']} ({city['country']}) : "
            f"score {city['travel_score']:.2f}{flight_info}\n"
            f"  Durée idéale : {city['duration_days'][0]}-{city['duration_days'][1]} jours | "
            f"Budget : {city['budget']}\n"
            f"  Tags : {tags}"
        )
        if city.get("notes"):
            citybreaks_lines.append(f"  Note : {city['notes']}")
        if city.get("geraldine_loves"):
            citybreaks_lines.append("  ❤️ Géraldine adore cette destination")

    citybreaks_text = "\n".join(citybreaks_lines) if citybreaks_lines else "Aucun city-break recommandé."

    # Formater les roadtrips (top 3)
    top_roadtrips = roadtrips[:3]
    roadtrips_lines = []
    for trip in top_roadtrips:
        highlights = ", ".join(trip.get("highlights", [])[:4])
        roadtrips_lines.append(
            f"- {trip['destination']} ({trip['country']}) : "
            f"{trip['drive_hours']}h de route ({trip['drive_km']}km)\n"
            f"  Score : {trip['travel_score']:.2f} | "
            f"Durée idéale : {trip['duration_days'][0]}-{trip['duration_days'][1]} jours | "
            f"Budget : {trip['budget']}\n"
            f"  Highlights : {highlights}"
        )
        if trip.get("notes"):
            roadtrips_lines.append(f"  Note : {trip['notes']}")

    roadtrips_text = "\n".join(roadtrips_lines) if roadtrips_lines else "Aucun roadtrip recommandé."

    # Construire le prompt
    prompt = f"""Prochaines vacances : {label}
Du {start} au {end} ({days} jours)
Saison : {season}

{flights_text}

City-breaks recommandés (par avion) :
{citybreaks_text}

Roadtrips recommandés (en voiture) :
{roadtrips_text}

---

En te basant sur ces données, propose 3 à 4 suggestions de voyage concrètes et personnalisées.

Pour chaque suggestion, fournis :
- Destination et durée recommandée
- Transport (vol avec compagnie + prix estimé, ou voiture avec km)
- Budget total estimé pour 2 personnes (détaillé : transport, hôtel, sur place)
- Meilleur moment pour réserver
- 2-3 highlights de la destination
- Pourquoi c'est adapté à cette période et à leur profil

Inclus au moins une destination avion ET une destination voiture si les deux sont pertinentes.
Privilégie les destinations avec les meilleurs scores et celles qui correspondent à leurs goûts (musique, art, gastronomie).

Réponds UNIQUEMENT avec un tableau JSON valide de suggestions, sans texte avant ou après.
Format : [{{"destination": "...", ...}}, ...]"""

    return prompt


def _parse_claude_response(response_text: str) -> List[Dict]:
    """Parse la réponse JSON de Claude."""
    # Nettoyer les backticks markdown si présents
    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        suggestions = json.loads(text)
        if isinstance(suggestions, list):
            return suggestions
        elif isinstance(suggestions, dict) and "suggestions" in suggestions:
            return suggestions["suggestions"]
        else:
            return [suggestions]
    except json.JSONDecodeError as e:
        print(f"  ⚠ Erreur parsing JSON voyage : {e}")
        return []


# =============================================================================
# FONCTION PRINCIPALE
# =============================================================================

def generate_travel_suggestions(
    vacation_period: Dict,
    profile: Optional[Dict] = None
) -> Dict:
    """
    Génère des suggestions de voyage pour une période de vacances.

    Args:
        vacation_period: Dict avec start, end, days, label
        profile: Dict profil utilisateur (optionnel, récupéré si absent)

    Returns:
        Dict avec vacation_period, flights_found, suggestions, generated_at
    """
    print("\n" + "=" * 50)
    print("GÉNÉRATION SUGGESTIONS VOYAGE")
    print("=" * 50)

    # Récupérer le profil si non fourni
    if profile is None:
        profile = get_profile()
        stats = get_activity_stats()
        profile["trips_seen_recent"] = stats.get("trips_seen_recent", [])

    # Collecter les données
    print("\n1. Collecte des données voyage...")

    flights = get_cheap_flights(vacation_period)
    citybreaks = get_citybreaks(vacation_period, flights, profile)
    roadtrips = get_roadtrips(vacation_period, profile)

    print(f"\n   Vols trouvés : {len(flights)}")
    print(f"   City-breaks scorés : {len(citybreaks)}")
    print(f"   Roadtrips scorés : {len(roadtrips)}")

    # Construire le prompt
    print("\n2. Construction du prompt Claude...")
    user_prompt = _build_travel_prompt(
        vacation_period, flights, citybreaks, roadtrips, profile
    )

    # Appeler Claude
    print("\n3. Appel Claude API...")

    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=TRAVEL_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )

        response_text = response.content[0].text
        suggestions = _parse_claude_response(response_text)

        print(f"   {len(suggestions)} suggestions générées")

    except Exception as e:
        print(f"   ⚠ Erreur Claude API : {e}")
        suggestions = []

    # Construire le résultat
    result = {
        "vacation_period": vacation_period,
        "flights_found": len(flights),
        "citybreaks_top": [
            {
                "destination": c["destination"],
                "country": c["country"],
                "travel_score": c["travel_score"],
                "geraldine_loves": c.get("geraldine_loves", False),
            }
            for c in citybreaks[:5]
        ],
        "roadtrips_top": [
            {
                "destination": r["destination"],
                "country": r["country"],
                "drive_hours": r["drive_hours"],
                "travel_score": r["travel_score"],
            }
            for r in roadtrips[:5]
        ],
        "suggestions": suggestions,
        "generated_at": datetime.now().isoformat(),
    }

    print("\n" + "=" * 50)
    print("SUGGESTIONS VOYAGE GÉNÉRÉES")
    print("=" * 50)

    return result


def format_travel_suggestions_html(result: Dict) -> str:
    """Formate les suggestions voyage en HTML pour l'affichage."""
    suggestions = result.get("suggestions", [])
    period = result.get("vacation_period", {})

    if not suggestions:
        return "<p>Aucune suggestion de voyage disponible.</p>"

    html_parts = [
        f"<div class='travel-suggestions'>",
        f"<h2>✈️ Idées pour vos vacances</h2>",
        f"<p class='period'>{period.get('label', 'Vacances')} — "
        f"{period.get('start')} au {period.get('end')}</p>",
    ]

    for i, sugg in enumerate(suggestions, 1):
        transport_icon = "✈️" if sugg.get("transport") == "avion" else "🚗"
        budget = sugg.get("budget_total", "N/A")

        html_parts.append(f"""
        <div class='travel-card'>
            <h3>{transport_icon} {sugg.get('destination', 'Destination')} ({sugg.get('country', '')})</h3>
            <div class='travel-meta'>
                <span class='duration'>{sugg.get('duration_days', '?')} jours</span>
                <span class='budget'>{budget}</span>
            </div>
            <div class='highlights'>
                <strong>À voir :</strong> {', '.join(sugg.get('highlights', [])[:3])}
            </div>
            <p class='why'>{sugg.get('why_now', '')}</p>
            <p class='tip'>💡 {sugg.get('practical_tip', '')}</p>
            <p class='booking'>📅 Réserver : {sugg.get('best_booking_time', 'Dès que possible')}</p>
        </div>
        """)

    html_parts.append("</div>")

    return "\n".join(html_parts)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    from datetime import date, timedelta

    print("=" * 60)
    print("TEST TRAVEL ENGINE")
    print("=" * 60)

    # Simuler des vacances dans 15 jours
    start = date.today() + timedelta(days=15)
    end = start + timedelta(days=7)

    test_period = {
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "days": 7,
        "label": "Vacances test",
    }

    test_profile = {
        "music_artists": ["The Cure", "Pulp", "Fontaines D.C.", "Bertrand Belin"],
        "expo_artists": ["Soulages", "Banksy", "Klimt"],
        "trips_seen_recent": [],
    }

    result = generate_travel_suggestions(test_period, test_profile)

    print("\n" + "=" * 60)
    print("RÉSULTAT")
    print("=" * 60)

    print(f"\nVols trouvés : {result['flights_found']}")
    print(f"Suggestions : {len(result['suggestions'])}")

    if result["suggestions"]:
        print("\nSuggestions :")
        for i, sugg in enumerate(result["suggestions"], 1):
            print(f"\n{i}. {sugg.get('destination', 'N/A')} ({sugg.get('country', '')})")
            print(f"   Transport : {sugg.get('transport', 'N/A')}")
            print(f"   Budget : {sugg.get('budget_total', 'N/A')}")
            print(f"   Highlights : {', '.join(sugg.get('highlights', []))}")
            print(f"   Pourquoi : {sugg.get('why_now', 'N/A')[:100]}...")

    # Vérifier Dublin et Londres
    print("\n" + "-" * 40)
    print("VÉRIFICATIONS SPÉCIFIQUES")
    print("-" * 40)

    citybreaks = result.get("citybreaks_top", [])
    for city in citybreaks:
        if city["destination"] == "Dublin":
            print(f"✓ Dublin présent avec score {city['travel_score']}")
        if city["destination"] == "Londres" and city.get("geraldine_loves"):
            print(f"✓ Londres présent avec geraldine_loves=True")
