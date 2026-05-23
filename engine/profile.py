"""
Module de gestion du profil utilisateur et des statistiques d'activité.
"""

import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional

from engine.database import get_connection


def get_profile() -> Dict[str, Any]:
    """
    Lit toutes les clés du profil utilisateur.

    Returns:
        Dict avec toutes les préférences désérialisées
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT key, value FROM user_profile")
    rows = cursor.fetchall()
    conn.close()

    profile = {}
    for row in rows:
        try:
            profile[row["key"]] = json.loads(row["value"])
        except json.JSONDecodeError:
            profile[row["key"]] = row["value"]

    return profile


def update_profile(key: str, value: Any) -> None:
    """
    Met à jour ou insère une préférence.

    Args:
        key: Clé de la préférence
        value: Valeur (sera sérialisée en JSON)
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO user_profile (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
    """, (key, json.dumps(value, ensure_ascii=False), datetime.now().isoformat()))

    conn.commit()
    conn.close()


def log_activity(period: Dict, category: str, note: str = "") -> None:
    """
    Enregistre une activité pour un week-end.

    Args:
        period: Dict avec start, end, label
        category: Type d'activité (maison, travaux, sortie_locale, voyage, etc.)
        note: Commentaire optionnel
    """
    conn = get_connection()
    cursor = conn.cursor()

    period_start = period.get("start")
    period_end = period.get("end")
    period_label = period.get("label", "")

    # Convertir les dates si nécessaire
    if isinstance(period_start, str):
        period_start = datetime.strptime(period_start, "%Y-%m-%d").date()
    if isinstance(period_end, str):
        period_end = datetime.strptime(period_end, "%Y-%m-%d").date()

    cursor.execute("""
        INSERT INTO activity_log (period_start, period_end, period_label, category, note)
        VALUES (?, ?, ?, ?, ?)
    """, (
        period_start.isoformat() if period_start else None,
        period_end.isoformat() if period_end else None,
        period_label,
        category,
        note
    ))

    conn.commit()
    conn.close()


def add_feedback(period: Dict, title: str, suggestion_type: str, rating: int) -> None:
    """
    Enregistre un feedback sur une suggestion.

    Args:
        period: Dict avec start
        title: Titre de la suggestion
        suggestion_type: Type (cinema, rando, voyage, etc.)
        rating: 1 pour 👍, -1 pour 👎
    """
    conn = get_connection()
    cursor = conn.cursor()

    period_start = period.get("start")
    if isinstance(period_start, str):
        period_start = datetime.strptime(period_start, "%Y-%m-%d").date()

    cursor.execute("""
        INSERT INTO suggestion_feedback (period_start, suggestion_title, suggestion_type, rating)
        VALUES (?, ?, ?, ?)
    """, (
        period_start.isoformat() if period_start else None,
        title,
        suggestion_type,
        rating
    ))

    conn.commit()
    conn.close()


def get_activity_stats() -> Dict[str, Any]:
    """
    Retourne des statistiques utiles sur l'activité récente.

    Returns:
        Dict avec last_outing_days_ago, streak_home, favorite_categories, thumbs_up_types
    """
    conn = get_connection()
    cursor = conn.cursor()

    today = date.today()

    # Dernière vraie sortie (non maison/travaux)
    cursor.execute("""
        SELECT period_start FROM activity_log
        WHERE category NOT IN ('maison', 'travaux')
        ORDER BY period_start DESC
        LIMIT 1
    """)
    row = cursor.fetchone()

    if row and row["period_start"]:
        last_outing = datetime.strptime(row["period_start"], "%Y-%m-%d").date()
        last_outing_days_ago = (today - last_outing).days
    else:
        last_outing_days_ago = -1  # Jamais de sortie enregistrée

    # Semaines consécutives à la maison (streak_home)
    cursor.execute("""
        SELECT period_start, category FROM activity_log
        ORDER BY period_start DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()

    streak_home = 0
    for row in rows:
        if row["category"] in ("maison", "travaux"):
            streak_home += 1
        else:
            break

    # Top 3 catégories favorites (toutes activités)
    cursor.execute("""
        SELECT category, COUNT(*) as count FROM activity_log
        GROUP BY category
        ORDER BY count DESC
        LIMIT 3
    """)
    favorite_categories = [row["category"] for row in cursor.fetchall()]

    # Types de suggestions les mieux notés
    cursor.execute("""
        SELECT suggestion_type, SUM(rating) as score
        FROM suggestion_feedback
        GROUP BY suggestion_type
        HAVING score > 0
        ORDER BY score DESC
        LIMIT 3
    """)
    thumbs_up_types = [row["suggestion_type"] for row in cursor.fetchall()]

    conn.close()

    return {
        "last_outing_days_ago": last_outing_days_ago,
        "streak_home": streak_home,
        "favorite_categories": favorite_categories,
        "thumbs_up_types": thumbs_up_types
    }


def get_recent_feedback(limit: int = 10) -> List[Dict]:
    """Retourne les derniers feedbacks."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT suggestion_title, suggestion_type, rating, created_at
        FROM suggestion_feedback
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_recent_activities(limit: int = 10) -> List[Dict]:
    """Retourne les dernières activités."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT period_label, category, note, created_at
        FROM activity_log
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results
