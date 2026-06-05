from flask import Flask, render_template, Response, request, jsonify
import json
import atexit
from datetime import date
import config
from engine import calendar_engine
from engine import suggest
from engine import email_sender
from engine import profile
from engine.travel_engine import generate_travel_suggestions
from engine.cache import cache_stats, cache_clear_all, cache_clear_expired
from collectors import weather, cinema, events, hiking
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)


# Filtre Jinja2 pour formater les dates
@app.template_filter('format_month')
def format_month_filter(date_str):
    """Formate une date en 'jour mois' français."""
    mois = ['jan', 'fév', 'mars', 'avr', 'mai', 'juin',
            'juil', 'août', 'sept', 'oct', 'nov', 'déc']
    if isinstance(date_str, str):
        # Format YYYY-MM-DD
        parts = date_str.split('-')
        if len(parts) == 3:
            day = int(parts[2])
            month = int(parts[1])
            return f"{day} {mois[month - 1]}"
    elif hasattr(date_str, 'day') and hasattr(date_str, 'month'):
        return f"{date_str.day} {mois[date_str.month - 1]}"
    return str(date_str)
app.secret_key = config.FLASK_SECRET_KEY

# Scheduler pour l'envoi d'email hebdomadaire
scheduler = BackgroundScheduler()


def scheduled_email_job():
    """Job planifié pour l'envoi d'email."""
    with app.app_context():
        result = email_sender.send_weekly_email(app)
        print(f"[Scheduler] Email: {result['message']}")


# Planifier l'envoi chaque mercredi à 11h30
scheduler.add_job(
    func=scheduled_email_job,
    trigger="cron",
    day_of_week="wed",
    hour=11,
    minute=30,
    id="weekly_email",
    replace_existing=True
)

# Démarrer le scheduler (seulement si pas déjà démarré)
if not scheduler.running:
    scheduler.start()

# Arrêter proprement le scheduler à la fermeture
atexit.register(lambda: scheduler.shutdown())


def prepare_movies_for_template(movies: list) -> list:
    """Prépare les films pour le template."""
    if not movies:
        return []

    grouped = cinema.group_movies_by_title(movies)
    result = []

    for movie in grouped[:5]:
        if movie.get("family_film"):
            continue

        cinemas_display = cinema.format_cinemas_line(movie.get("cinemas", []))

        result.append({
            "title": movie["title"],
            "director": movie.get("director", ""),
            "press_rating": movie.get("press_rating"),
            "telerama_pick": movie.get("telerama_pick", False),
            "telerama_stars": movie.get("telerama_stars"),
            "cahiers_pick": movie.get("cahiers_pick", False),
            "cinemas_display": cinemas_display,
            "allocine_url": movie.get("allocine_url", "")
        })

    return result


@app.route("/")
def index():
    """Page principale avec les suggestions."""
    result = suggest.get_suggestions_for_next_period()

    # Calculer les données vacances pour la section voyages
    today = date.today()
    periods = calendar_engine.get_next_periods(limit=10)
    vacations = [p for p in periods if p.get("type") == "vacation" or p.get("mode") == "vacances"]

    next_vacation = vacations[0] if vacations else None
    days_until_vacation = (next_vacation["start"] - today).days if next_vacation else 999
    is_vacation_soon = days_until_vacation <= 21

    # Données voyage (sans appel API lourd sur la page d'accueil)
    # Les données complètes sont générées via /test-travel ou en mode vacances
    cheap_flights = []
    travel_citybreaks = []
    travel_roadtrips = []

    # On récupère uniquement les données statiques pour l'affichage
    # sans déclencher les appels API Ryanair/EasyJet/Claude
    if next_vacation and days_until_vacation <= 90:
        try:
            from collectors.travel_citybreaks import get_citybreaks, CITY_BREAKS
            from collectors.travel_roadtrips import get_roadtrips, ROAD_TRIPS

            user_profile = profile.get_profile()

            # City-breaks statiques (top 3 par score saison)
            travel_citybreaks = [
                {
                    "destination": c["destination"],
                    "country": c["country"],
                    "duration_days": c.get("duration_days", [4, 5]),
                    "highlights": c.get("highlights", [])[:4],
                    "budget": c.get("budget", "€€"),
                    "geraldine_loves": c.get("geraldine_loves", False),
                    "flight_info": None,
                    "travel_score": 0.5,
                }
                for c in CITY_BREAKS[:3]
            ]

            # Roadtrips statiques (top 3)
            travel_roadtrips = [
                {
                    "destination": r["destination"],
                    "country": r["country"],
                    "drive_hours": r["drive_hours"],
                    "duration_days": r.get("duration_days", [3, 4]),
                    "highlights": r.get("highlights", [])[:4],
                    "best_season": r.get("seasons", ["été"])[0] if r.get("seasons") and r.get("seasons") != ["all"] else "toute saison",
                    "travel_score": 0.5,
                }
                for r in ROAD_TRIPS[:3]
            ]
        except Exception as e:
            print(f"  ⚠ Erreur données voyages : {e}")

    # Calendrier des 4 prochaines vacances
    upcoming_vacations = vacations[:4]

    if result.get("error"):
        return render_template("index.html",
                               error=result["error"],
                               period=None,
                               weather=None,
                               suggestions=[],
                               intro="",
                               movies=[],
                               hikes=[],
                               show_hiking=False,
                               restaurants=[],
                               show_restaurants=False,
                               is_vacation=False,
                               travel={},
                               is_vacation_soon=is_vacation_soon,
                               next_vacation=next_vacation,
                               days_until_vacation=days_until_vacation,
                               cheap_flights=cheap_flights,
                               travel_citybreaks=travel_citybreaks,
                               travel_roadtrips=travel_roadtrips,
                               upcoming_vacations=upcoming_vacations,
                               generated_at=result.get("generated_at"))

    # Suggestions structurées (déjà parsées depuis JSON)
    suggestions = result.get("suggestions", [])
    intro = result.get("intro", "")
    is_vacation = result.get("is_vacation", False)

    # Préparer les films (seulement en mode week-end)
    movies = []
    if not is_vacation:
        movies = prepare_movies_for_template(result.get("movies", []))

    # Vérifier si on affiche les randonnées (au moins un jour favorable)
    weather_data = result.get("weather", {})
    show_hiking = False
    if not is_vacation and weather_data.get("days"):
        show_hiking = any(d.get("suitable_outdoor", False) for d in weather_data["days"])

    # Restaurants toujours affichés en mode week-end
    show_restaurants = not is_vacation

    return render_template("index.html",
                           period=result["period"],
                           weather=weather_data,
                           suggestions=suggestions,
                           intro=intro,
                           movies=movies,
                           hikes=result.get("hikes", [])[:3],
                           show_hiking=show_hiking,
                           restaurants=result.get("restaurants", [])[:3],
                           show_restaurants=show_restaurants,
                           is_vacation=is_vacation,
                           travel=result.get("travel", {}),
                           is_vacation_soon=is_vacation_soon,
                           next_vacation=next_vacation,
                           days_until_vacation=days_until_vacation,
                           cheap_flights=cheap_flights,
                           travel_citybreaks=travel_citybreaks,
                           travel_roadtrips=travel_roadtrips,
                           upcoming_vacations=upcoming_vacations,
                           generated_at=result["generated_at"])


@app.route("/suggest")
def suggest_route():
    """Endpoint debug : suggestions en JSON."""
    result = suggest.get_suggestions_for_next_period()

    if result.get("error"):
        return Response(json.dumps({"error": result["error"]}, ensure_ascii=False),
                        mimetype="application/json; charset=utf-8")

    output = {
        "period": result["period"]["label"],
        "dates": f"{result['period']['start'].strftime('%d/%m/%Y')} - {result['period']['end'].strftime('%d/%m/%Y')}",
        "generated_at": result["generated_at"].strftime("%d/%m/%Y %H:%M"),
        "intro": result.get("intro", ""),
        "suggestions": result.get("suggestions", []),
        "fallback_text": result.get("suggestions_text")  # None si JSON parsé OK
    }
    return Response(json.dumps(output, ensure_ascii=False, indent=2),
                    mimetype="application/json; charset=utf-8")


@app.route("/feedback", methods=["POST"])
def feedback_route():
    """Endpoint pour enregistrer le feedback utilisateur."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "JSON requis"}), 400

    title = data.get("title")
    suggestion_type = data.get("type", "autre")
    rating = data.get("rating")
    period_start = data.get("period_start")

    if not title or rating is None:
        return jsonify({"error": "title et rating requis"}), 400

    if rating not in (1, -1):
        return jsonify({"error": "rating doit etre 1 ou -1"}), 400

    period = {"start": period_start} if period_start else {}
    profile.add_feedback(period, title, suggestion_type, rating)

    return jsonify({"ok": True})


@app.route("/profile")
def profile_route():
    """Endpoint pour consulter le profil complet."""
    user_profile = profile.get_profile()
    stats = profile.get_activity_stats()
    recent_feedback = profile.get_recent_feedback(10)

    # Mode complet ou récent selon param
    mode = request.args.get('mode', 'recent')
    if mode == 'full':
        activities = profile.get_full_activity_history(limit=50)
    else:
        activities = profile.get_recent_activities(10)

    return jsonify({
        "profile": user_profile,
        "stats": stats,
        "recent_feedback": recent_feedback,
        "activities": activities
    })


@app.route("/activity", methods=["POST"])
def activity_route():
    """Endpoint pour enregistrer une activité."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "JSON requis"}), 400

    category = data.get("category")
    note = data.get("note", "")
    period_start = data.get("period_start")
    period_end = data.get("period_end")
    period_label = data.get("period_label", "")

    # Nouveaux champs
    films_seen = data.get("films_seen")
    concerts_seen = data.get("concerts_seen")
    expos_seen = data.get("expos_seen")
    hiking_seen = data.get("hiking_seen")
    stayed_home_reason = data.get("stayed_home_reason")

    if not category:
        return jsonify({"error": "category requis"}), 400

    period = {
        "start": period_start,
        "end": period_end,
        "label": period_label
    }
    profile.log_activity(
        period, category, note,
        films_seen=films_seen,
        concerts_seen=concerts_seen,
        expos_seen=expos_seen,
        hiking_seen=hiking_seen,
        stayed_home_reason=stayed_home_reason
    )

    return jsonify({"ok": True})


@app.route("/mark-as-done", methods=["POST"])
def mark_as_done_route():
    """Marque une suggestion comme déjà faite."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "Aucune donnée fournie"}), 400

    title = data.get("title")
    suggestion_type = data.get("type")
    done_date = data.get("date")  # Format ISO "2026-05-27"

    if not title or not suggestion_type:
        return jsonify({"error": "title et type requis"}), 400

    # Date par défaut = aujourd'hui
    if not done_date:
        from datetime import date
        done_date = date.today().isoformat()

    # Formater selon le type
    if suggestion_type == "cinema":
        item = title  # Simple titre
        field = "films_seen"
    elif suggestion_type == "concert":
        item = title  # Format "Artiste - Lieu" déjà présent
        field = "concerts_seen"
    elif suggestion_type == "expo":
        item = title  # Format "Expo - Lieu" déjà présent
        field = "expos_seen"
    elif suggestion_type == "rando":
        # Format : "Nom rando (DD/MM/YYYY)"
        from datetime import datetime
        date_obj = datetime.strptime(done_date, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%d/%m/%Y")
        item = f"{title} ({formatted_date})"
        field = "hiking_seen"
    else:
        return jsonify({"error": f"Type '{suggestion_type}' non supporté"}), 400

    # Créer une activité avec juste cet item
    from datetime import datetime
    date_obj = datetime.strptime(done_date, "%Y-%m-%d")
    period = {
        "start": done_date,
        "end": done_date,
        "label": f"Marqué le {date_obj.strftime('%d/%m/%Y')}"
    }

    kwargs = {
        "period": period,
        "category": "sortie_locale",
        field: [item]
    }

    profile.log_activity(**kwargs)

    return jsonify({"ok": True, "message": f"{title} marqué comme fait"})


@app.route("/send-email")
def send_email_route():
    """Endpoint pour envoyer manuellement l'email (JSON)."""
    result = email_sender.send_weekly_email(app)
    return jsonify(result)


@app.route("/test-email")
def test_email_route():
    """Endpoint pour tester l'envoi d'email avec confirmation HTML."""
    result = email_sender.send_weekly_email(app)

    if result["success"]:
        html = f"""
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <title>Email envoyé</title>
            <style>
                body {{ font-family: system-ui, sans-serif; background: #FAFAF8; padding: 40px; }}
                .card {{ max-width: 500px; margin: 0 auto; background: white; border-radius: 12px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; }}
                .icon {{ font-size: 48px; margin-bottom: 16px; }}
                h1 {{ color: #7C9A7E; margin: 0 0 16px 0; }}
                p {{ color: #555; margin: 8px 0; }}
                .recipients {{ background: #f5f5f5; padding: 12px; border-radius: 6px; margin-top: 16px; font-size: 14px; }}
                a {{ color: #7C9A7E; }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="icon">✅</div>
                <h1>Email envoyé !</h1>
                <p>{result['message']}</p>
                <div class="recipients">
                    <strong>Destinataires :</strong><br>
                    {', '.join(result.get('recipients', []))}
                </div>
                <p style="margin-top: 24px;"><a href="/">← Retour à l'accueil</a></p>
            </div>
        </body>
        </html>
        """
    else:
        html = f"""
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <title>Erreur d'envoi</title>
            <style>
                body {{ font-family: system-ui, sans-serif; background: #FAFAF8; padding: 40px; }}
                .card {{ max-width: 500px; margin: 0 auto; background: white; border-radius: 12px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; }}
                .icon {{ font-size: 48px; margin-bottom: 16px; }}
                h1 {{ color: #C0392B; margin: 0 0 16px 0; }}
                p {{ color: #555; margin: 8px 0; }}
                .error {{ background: #ffeaea; padding: 12px; border-radius: 6px; margin-top: 16px; font-size: 14px; color: #C0392B; }}
                a {{ color: #7C9A7E; }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="icon">❌</div>
                <h1>Échec de l'envoi</h1>
                <div class="error">{result['message']}</div>
                <p style="margin-top: 24px;"><a href="/">← Retour à l'accueil</a></p>
            </div>
        </body>
        </html>
        """

    return html


@app.route("/test-travel")
def test_travel_route():
    """Endpoint pour tester le système de voyage sans attendre les vacances."""
    from datetime import date, timedelta
    from engine.travel_engine import generate_travel_suggestions

    # Paramètres personnalisables via query string
    days_ahead = int(request.args.get("days_ahead", 45))
    duration = int(request.args.get("duration", 7))

    # Créer une période de vacances fictive
    start = date.today() + timedelta(days=days_ahead)
    end = start + timedelta(days=duration)

    test_period = {
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "days": duration,
        "label": f"Vacances test ({duration}j dans {days_ahead}j)",
    }

    # Générer les suggestions
    try:
        result = generate_travel_suggestions(test_period)

        # Ajouter les paramètres utilisés
        result["test_params"] = {
            "days_ahead": days_ahead,
            "duration": duration,
            "period": test_period,
        }

        return jsonify(result)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[test-travel] Erreur : {e}")
        print(error_trace)
        return jsonify({"error": str(e), "trace": error_trace}), 500


@app.route("/cache-stats")
def cache_stats_route():
    """Endpoint pour voir les statistiques du cache."""
    stats = cache_stats()
    return jsonify(stats)


@app.route("/cache-clear", methods=["DELETE"])
def cache_clear_route():
    """Endpoint pour vider le cache."""
    mode = request.args.get("mode", "all")

    if mode == "expired":
        count = cache_clear_expired()
        return jsonify({"cleared": count, "mode": "expired"})
    else:
        count = cache_clear_all()
        return jsonify({"cleared": count, "mode": "all"})


@app.route("/recommendations")
def recommendations_list_route():
    """Retourne la liste des recommandations."""
    pending = profile.get_pending_recommendations()
    done = profile.get_done_recommendations()
    return jsonify({
        "pending": pending,
        "done": done
    })


@app.route("/recommendations", methods=["POST"])
def recommendations_add_route():
    """Ajoute une nouvelle recommandation."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "JSON requis"}), 400

    source = data.get("source")
    rec_type = data.get("type")
    title = data.get("title")

    if not source or not rec_type or not title:
        return jsonify({"error": "source, type et title requis"}), 400

    rec_id = profile.add_recommendation(
        source=source,
        type=rec_type,
        title=title,
        city=data.get("city", ""),
        country=data.get("country", ""),
        notes=data.get("notes", ""),
        url=data.get("url", "")
    )

    return jsonify({"ok": True, "id": rec_id})


@app.route("/recommendations/<int:rec_id>/done", methods=["POST"])
def recommendations_done_route(rec_id):
    """Marque une recommandation comme faite."""
    profile.mark_recommendation_done(rec_id)
    return jsonify({"ok": True})


def display_weather_forecast(forecast: dict) -> None:
    """Affiche les prévisions météo de manière formatée."""
    print(f"\n{'='*50}")
    print(f"MÉTÉO - {forecast['location']}")
    print(f"Période : {forecast['period_label']}")
    print(f"{'='*50}")

    if forecast.get("error"):
        print(f"⚠ Erreur : {forecast['error']}")
        return

    for day in forecast["days"]:
        outdoor = "✓" if day["suitable_outdoor"] else "✗"
        print(f"\n{day['label']} ({day['date']})")
        print(f"  Températures : {day['temp_min']}°C — {day['temp_max']}°C")
        print(f"  Conditions   : {day['description']}")
        print(f"  Pluie        : {day['rain_mm']} mm")
        print(f"  Sortie       : {outdoor}")

    print(f"\n{'—'*50}")
    print(f"Résumé     : {forecast['summary']}")
    print(f"Meilleur   : {forecast['best_day']}")
    print(f"{'='*50}\n")


def display_cinema_movies(movies: list) -> None:
    """Affiche les films cinéma de manière formatée."""
    print(f"\n{'='*50}")
    print("CINÉMA - Films Art & Essai")
    print(f"{'='*50}")

    if not movies:
        print("Aucun film trouvé pour cette période")
        return

    # Résumé
    summary = cinema.get_movies_summary(movies)

    # Sources éditoriales
    print(f"\n{cinema.get_editorial_sources_line()}")

    print(f"\nFilms : {summary['unique_films']} uniques ({summary['total_entries']} entrées)")
    for cinema_name, count in summary["by_cinema"].items():
        print(f"  • {cinema_name} : {count}")

    # Top 3 films (groupés par titre)
    print(f"\n{'—'*50}")
    print("TOP 3 FILMS")
    print(f"{'—'*50}")

    for i, movie in enumerate(summary["top_movies"], 1):
        rating = movie["press_rating"] or "N/A"
        if isinstance(rating, float):
            rating = f"{rating:.1f}/5"

        # Labels éditoriaux
        labels = []
        if movie.get("telerama_pick") and movie.get("cahiers_pick"):
            stars = movie.get("telerama_stars") or 0
            labels.append(f"★★ Télérama {'★' * stars} + Cahiers")
        elif movie.get("telerama_pick"):
            stars = movie.get("telerama_stars") or 0
            labels.append(f"★ Télérama {'★' * stars}")
        elif movie.get("cahiers_pick"):
            labels.append("★ Cahiers")
        if movie["art_et_essai"]:
            labels.append("Art & Essai")
        label_str = f" [{', '.join(labels)}]" if labels else ""

        # Ligne cinémas groupés
        cinemas_line = cinema.format_cinemas_line(movie.get("cinemas", []))

        print(f"\n{i}. {movie['title']}{label_str}")
        if movie["director"]:
            print(f"   Réalisateur : {movie['director']}")
        print(f"   Note presse : {rating}")
        print(f"   Où           : {cinemas_line}")

    print(f"\n{'='*50}\n")


def display_events(events_list: list) -> None:
    """Affiche les événements de manière formatée."""
    print(f"\n{'='*50}")
    print("ÉVÉNEMENTS LOCAUX")
    print(f"{'='*50}")

    if not events_list:
        print("Aucun événement trouvé pour cette période")
        return

    summary = events.get_events_summary(events_list)

    # Sources
    print(f"\nSources : {events.get_sources_line()}")
    print(f"Total : {summary['total']} événements")

    # Par catégorie
    if summary["by_category"]:
        cats = ", ".join([f"{cat} ({count})" for cat, count in summary["by_category"].items()])
        print(f"Catégories : {cats}")

    # Top 5 événements
    print(f"\n{'—'*50}")
    print("TOP 5 ÉVÉNEMENTS")
    print(f"{'—'*50}")

    for i, event in enumerate(summary["top_events"], 1):
        score_bar = "●" * int(event["score"] * 5) + "○" * (5 - int(event["score"] * 5))
        category = event.get("category", "autre").upper()

        print(f"\n{i}. [{category}] {event['title']}")
        print(f"   Lieu     : {event.get('city', 'NC')} ({event.get('distance_km', 0):.0f} km)")
        print(f"   Prix     : {event.get('price', 'NC')}")
        print(f"   Score    : {score_bar} ({event['score']:.2f})")

    print(f"\n{'='*50}\n")


if __name__ == "__main__":
    # Affiche la prochaine période au démarrage
    next_period = calendar_engine.get_next_period()
    if next_period:
        print(f"\n{'='*50}")
        print(f"Prochaine période : {next_period['label']}")
        print(f"Du {next_period['start'].strftime('%d/%m/%Y')} au {next_period['end'].strftime('%d/%m/%Y')}")
        print(f"Durée : {next_period['days']} jours ({next_period['mode']})")
        print(f"{'='*50}")

        # Test météo
        forecast = weather.get_weather_forecast(next_period)
        display_weather_forecast(forecast)

        # Test cinéma
        movies = cinema.get_artetal_movies(next_period)
        display_cinema_movies(movies)

        # Test événements
        local_events = events.get_local_events(next_period)
        display_events(local_events)

        # Test randonnées
        hikes = hiking.get_hiking_suggestions(next_period, forecast)
        hiking.display_hiking_suggestions(hikes)

    app.run(debug=True, port=5001)
