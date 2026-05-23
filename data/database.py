"""
Module de gestion de la base de données SQLite.
Stocke les feedbacks utilisateur sur les suggestions.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "activity.db"


def get_connection():
    """Retourne une connexion à la base SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialise la base de données avec les tables nécessaires."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suggestion_title TEXT NOT NULL,
            feedback_type TEXT NOT NULL CHECK(feedback_type IN ('like', 'dislike')),
            period_label TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def log_feedback(suggestion_title: str, feedback_type: str, period_label: str = None) -> int:
    """
    Enregistre un feedback utilisateur.

    Args:
        suggestion_title: Titre de la suggestion
        feedback_type: 'like' ou 'dislike'
        period_label: Label de la période (ex: "Week-end du 24 mai")

    Returns:
        ID du feedback créé
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO feedback (suggestion_title, feedback_type, period_label)
        VALUES (?, ?, ?)
    """, (suggestion_title, feedback_type, period_label))

    feedback_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return feedback_id


def get_feedback_stats() -> dict:
    """
    Retourne les statistiques de feedback.

    Returns:
        Dict avec total_likes, total_dislikes, recent_feedback
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Totaux
    cursor.execute("SELECT COUNT(*) FROM feedback WHERE feedback_type = 'like'")
    total_likes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM feedback WHERE feedback_type = 'dislike'")
    total_dislikes = cursor.fetchone()[0]

    # 10 derniers feedbacks
    cursor.execute("""
        SELECT suggestion_title, feedback_type, period_label, created_at
        FROM feedback
        ORDER BY created_at DESC
        LIMIT 10
    """)
    recent = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        "total_likes": total_likes,
        "total_dislikes": total_dislikes,
        "recent_feedback": recent
    }


# Initialiser la DB au premier import
init_db()
