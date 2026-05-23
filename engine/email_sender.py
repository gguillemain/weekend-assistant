"""
Module d'envoi d'emails hebdomadaires.
Envoie le digest des suggestions chaque mercredi.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from flask import render_template
import config
from engine import suggest
from collectors import cinema


def _prepare_email_data() -> dict:
    """Prépare les données pour le template email."""
    result = suggest.get_suggestions_for_next_period()

    if result.get("error"):
        return None

    # Préparer les films comme dans app.py
    movies = []
    if result.get("movies"):
        grouped = cinema.group_movies_by_title(result["movies"])
        for movie in grouped[:3]:
            if movie.get("family_film"):
                continue
            movies.append({
                "title": movie["title"],
                "director": movie.get("director", ""),
                "press_rating": movie.get("press_rating"),
                "telerama_pick": movie.get("telerama_pick", False),
                "cinemas_display": cinema.format_cinemas_line(movie.get("cinemas", []))
            })

    # Vérifier si on affiche les randonnées
    weather_data = result.get("weather", {})
    show_hiking = False
    if weather_data.get("days"):
        show_hiking = any(d.get("suitable_outdoor", False) for d in weather_data["days"])

    return {
        "period": result["period"],
        "weather": weather_data,
        "suggestions": result.get("suggestions", []),
        "intro": result.get("intro", ""),
        "movies": movies,
        "hikes": result.get("hikes", [])[:3],
        "show_hiking": show_hiking,
        "is_vacation": result.get("is_vacation", False),
        "generated_at": result["generated_at"],
        "app_url": config.BASE_LOCATION.get("app_url", "")
    }


def send_weekly_email(app=None) -> dict:
    """
    Génère et envoie l'email hebdomadaire.

    Args:
        app: Instance Flask pour le contexte de rendu

    Returns:
        Dict avec success, message, recipients
    """
    # Vérifier la configuration SMTP
    if not config.SMTP_USER or not config.SMTP_PASSWORD:
        return {
            "success": False,
            "message": "Configuration SMTP manquante (SMTP_USER, SMTP_PASSWORD)",
            "recipients": []
        }

    if not config.EMAIL_TO or not config.EMAIL_TO[0]:
        return {
            "success": False,
            "message": "Aucun destinataire configure (EMAIL_TO)",
            "recipients": []
        }

    # Préparer les données
    data = _prepare_email_data()
    if not data:
        return {
            "success": False,
            "message": "Erreur lors de la generation des suggestions",
            "recipients": []
        }

    # Rendre le template email
    if app:
        with app.app_context():
            html_content = render_template("email.html", **data)
    else:
        # Fallback sans contexte Flask
        return {
            "success": False,
            "message": "Contexte Flask requis pour le rendu du template",
            "recipients": []
        }

    # Construire l'email
    subject = f"Weekend Assistant - {data['period']['label']}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM
    msg["To"] = ", ".join(config.EMAIL_TO)

    # Version texte simple (fallback)
    text_content = f"""Weekend Assistant - {data['period']['label']}

{data.get('intro', '')}

Suggestions :
"""
    for s in data.get("suggestions", []):
        text_content += f"\n{s.get('emoji', '')} {s.get('title', '')}\n{s.get('description', '')}\n"

    msg.attach(MIMEText(text_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    # Envoyer l'email
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.EMAIL_FROM, config.EMAIL_TO, msg.as_string())

        return {
            "success": True,
            "message": f"Email envoye: {subject}",
            "recipients": config.EMAIL_TO,
            "sent_at": datetime.now().isoformat()
        }

    except smtplib.SMTPException as e:
        return {
            "success": False,
            "message": f"Erreur SMTP: {str(e)}",
            "recipients": config.EMAIL_TO
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Erreur inattendue: {str(e)}",
            "recipients": config.EMAIL_TO
        }
