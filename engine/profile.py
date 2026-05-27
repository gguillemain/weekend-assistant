"""
Module de gestion du profil utilisateur et des statistiques d'activité.
"""

import json
import unicodedata
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional

from engine.database import get_connection


def normalize_for_matching(text: str) -> str:
    """Normalise un titre pour comparaison (accents, ponctuation, casse)."""
    if not text:
        return ""
    text = text.lower()
    # Supprimer accents
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    # Supprimer ponctuation
    text = re.sub(r'[^\w\s-]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def get_seen_items_normalized(activity_type: str, days: int = 180) -> set:
    """
    Retourne un set de titres normalisés vus dans les N derniers jours.

    Args:
        activity_type: 'films', 'concerts', ou 'expos'
        days: Nombre de jours dans le passé (défaut 180 = 6 mois)
    """
    conn = get_connection()
    cursor = conn.cursor()

    cutoff_date = (date.today() - timedelta(days=days)).isoformat()

    field_map = {
        'films': 'films_seen',
        'concerts': 'concerts_seen',
        'expos': 'expos_seen'
    }

    field = field_map.get(activity_type)
    if not field:
        return set()

    cursor.execute(f"""
        SELECT {field} FROM activity_log
        WHERE {field} IS NOT NULL
        AND period_start >= ?
        ORDER BY period_start DESC
    """, (cutoff_date,))

    seen = set()
    for row in cursor.fetchall():
        try:
            items = json.loads(row[field])
            for item in items:
                normalized = normalize_for_matching(item)
                if normalized:
                    seen.add(normalized)
        except (json.JSONDecodeError, TypeError):
            pass

    conn.close()
    return seen


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


def log_activity(
    period: Dict,
    category: str,
    note: str = "",
    films_seen: List[str] = None,
    concerts_seen: List[str] = None,
    expos_seen: List[str] = None,
    stayed_home_reason: str = None
) -> None:
    """
    Enregistre une activité pour un week-end.

    Args:
        period: Dict avec start, end, label
        category: Type d'activité (maison, travaux, sortie_locale, voyage, etc.)
        note: Commentaire optionnel
        films_seen: Liste de titres de films vus
        concerts_seen: Liste "Artiste - Lieu"
        expos_seen: Liste "Expo - Lieu"
        stayed_home_reason: Raison si resté à la maison (repos, travaux, météo, autre)
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
        INSERT INTO activity_log (
            period_start, period_end, period_label, category, note,
            films_seen, concerts_seen, expos_seen, stayed_home_reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        period_start.isoformat() if period_start else None,
        period_end.isoformat() if period_end else None,
        period_label,
        category,
        note,
        json.dumps(films_seen, ensure_ascii=False) if films_seen else None,
        json.dumps(concerts_seen, ensure_ascii=False) if concerts_seen else None,
        json.dumps(expos_seen, ensure_ascii=False) if expos_seen else None,
        stayed_home_reason
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

    # Films récemment vus (10 derniers)
    cursor.execute("""
        SELECT films_seen FROM activity_log
        WHERE films_seen IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 20
    """)
    films_seen_recent = []
    for row in cursor.fetchall():
        try:
            films = json.loads(row["films_seen"])
            films_seen_recent.extend(films)
        except (json.JSONDecodeError, TypeError):
            pass
    films_seen_recent = films_seen_recent[:10]

    # Concerts récents (5 derniers)
    cursor.execute("""
        SELECT concerts_seen FROM activity_log
        WHERE concerts_seen IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 10
    """)
    concerts_seen_recent = []
    for row in cursor.fetchall():
        try:
            concerts = json.loads(row["concerts_seen"])
            concerts_seen_recent.extend(concerts)
        except (json.JSONDecodeError, TypeError):
            pass
    concerts_seen_recent = concerts_seen_recent[:5]

    # Expos récentes (5 dernières)
    cursor.execute("""
        SELECT expos_seen FROM activity_log
        WHERE expos_seen IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 10
    """)
    expos_seen_recent = []
    for row in cursor.fetchall():
        try:
            expos = json.loads(row["expos_seen"])
            expos_seen_recent.extend(expos)
        except (json.JSONDecodeError, TypeError):
            pass
    expos_seen_recent = expos_seen_recent[:5]

    conn.close()

    return {
        "last_outing_days_ago": last_outing_days_ago,
        "streak_home": streak_home,
        "favorite_categories": favorite_categories,
        "thumbs_up_types": thumbs_up_types,
        "films_seen_recent": films_seen_recent,
        "concerts_seen_recent": concerts_seen_recent,
        "expos_seen_recent": expos_seen_recent
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


def get_full_activity_history(limit: int = 50) -> Dict:
    """Retourne l'historique complet groupé par mois."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id, period_label, period_start, period_end, category, note,
            films_seen, concerts_seen, expos_seen, stayed_home_reason, created_at
        FROM activity_log
        ORDER BY period_start DESC
        LIMIT ?
    """, (limit,))

    activities = []
    for row in cursor.fetchall():
        activity = dict(row)

        # Désérialiser JSON fields
        for field in ['films_seen', 'concerts_seen', 'expos_seen']:
            if activity[field]:
                try:
                    activity[field] = json.loads(activity[field])
                except json.JSONDecodeError:
                    activity[field] = []
            else:
                activity[field] = []

        activities.append(activity)

    conn.close()

    # Grouper par mois
    grouped = {}
    for activity in activities:
        if not activity['period_start']:
            continue

        try:
            period_date = datetime.strptime(activity['period_start'], '%Y-%m-%d')
            month_key = period_date.strftime('%Y-%m')
            month_label = period_date.strftime('%B %Y')
        except ValueError:
            month_key = 'unknown'
            month_label = 'Date inconnue'

        if month_key not in grouped:
            grouped[month_key] = {
                'month_label': month_label,
                'activities': []
            }

        grouped[month_key]['activities'].append(activity)

    return {
        'total': len(activities),
        'grouped': [v for k, v in sorted(grouped.items(), reverse=True)]
    }
