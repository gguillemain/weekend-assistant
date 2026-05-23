from flask import Flask, render_template, Response, request, jsonify
import json
import atexit
import config
from engine import calendar_engine
from engine import suggest
from engine import email_sender
from engine import profile
from collectors import weather, cinema, events, hiking
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

# Scheduler pour l'envoi d'email hebdomadaire
scheduler = BackgroundScheduler()


def scheduled_email_job():
    """Job planifié pour l'envoi d'email."""
    with app.app_context():
        result = email_sender.send_weekly_email(app)
        print(f"[Scheduler] Email: {result['message']}")


# Planifier l'envoi chaque mercredi à 18h
scheduler.add_job(
    func=scheduled_email_job,
    trigger="cron",
    day_of_week="wed",
    hour=18,
    minute=0,
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
                               is_vacation=False,
                               travel={},
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

    return render_template("index.html",
                           period=result["period"],
                           weather=weather_data,
                           suggestions=suggestions,
                           intro=intro,
                           movies=movies,
                           hikes=result.get("hikes", [])[:3],
                           show_hiking=show_hiking,
                           is_vacation=is_vacation,
                           travel=result.get("travel", {}),
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
    recent_activities = profile.get_recent_activities(10)

    return jsonify({
        "profile": user_profile,
        "stats": stats,
        "recent_feedback": recent_feedback,
        "recent_activities": recent_activities
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

    if not category:
        return jsonify({"error": "category requis"}), 400

    period = {
        "start": period_start,
        "end": period_end,
        "label": period_label
    }
    profile.log_activity(period, category, note)

    return jsonify({"ok": True})


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
