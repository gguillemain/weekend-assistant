"""
Module de gestion de la base de données SQLite.
Stocke le profil utilisateur, l'historique d'activités et les feedbacks.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "preferences.db"


def get_connection():
    """Retourne une connexion à la base SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialise la base de données avec les tables et le profil initial."""
    conn = get_connection()
    cursor = conn.cursor()

    # Table user_profile : clés/valeurs de préférences
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profile (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Table activity_log : journal des activités
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_start DATE,
            period_end DATE,
            period_label TEXT,
            category TEXT,
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Table suggestion_feedback : feedback sur les suggestions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suggestion_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_start DATE,
            suggestion_title TEXT,
            suggestion_type TEXT,
            rating INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # Peupler le profil initial
    _populate_initial_profile(cursor)
    conn.commit()
    conn.close()


def _populate_initial_profile(cursor):
    """Insère le profil initial si les clés n'existent pas."""
    initial_profile = {
        "music_artists": ["The Cure", "Pulp", "Fontaines D.C.", "Bertrand Belin"],
        "music_genres": ["new wave", "post-punk", "jazz", "indie rock", "pop anglaise"],
        "music_venues": [
            "La Laiterie Strasbourg",
            "La Poudrière Belfort",
            "Kaserne Basel",
            "Parc Expo Mulhouse"
        ],
        "expo_artists": ["Soulages", "Banksy", "surréalistes"],
        "expo_style": "non-mainstream, contemporain, subversif",
        "expo_fondations": [
            "Fondation Beyeler Bâle",
            "Fondation Schneider Mulhouse"
        ],
        "expo_cities": ["Bâle", "Strasbourg", "Mulhouse", "Belfort", "Besançon"],
        "hike_max_elev": 300,
        "hike_prefer_loop": True,
        "cinema_sources": ["Télérama", "Cahiers du Cinéma"]
    }

    for key, value in initial_profile.items():
        cursor.execute("""
            INSERT OR IGNORE INTO user_profile (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, json.dumps(value, ensure_ascii=False), datetime.now().isoformat()))


# Initialiser la DB au premier import
init_db()
