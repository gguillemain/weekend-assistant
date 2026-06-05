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
            films_seen TEXT,
            concerts_seen TEXT,
            expos_seen TEXT,
            stayed_home_reason TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration : ajouter les nouveaux champs si la table existe déjà
    _migrate_activity_log(cursor)

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

    # Table recommendations : recommandations de l'entourage
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            city TEXT,
            country TEXT,
            notes TEXT,
            url TEXT,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            done BOOLEAN DEFAULT 0,
            done_at DATETIME
        )
    """)

    # Table life_projects : projets de vie à accomplir
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS life_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT,
            keywords TEXT,
            status TEXT DEFAULT 'actif',
            priority INTEGER DEFAULT 2,
            notes TEXT,
            accomplished_at DATETIME,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # Peupler le profil initial
    _populate_initial_profile(cursor)

    # Peupler les projets de vie initiaux
    _populate_initial_projects(cursor)

    conn.commit()
    conn.close()


def _migrate_activity_log(cursor):
    """Ajoute les nouveaux champs à activity_log si ils n'existent pas."""
    # Vérifier les colonnes existantes
    cursor.execute("PRAGMA table_info(activity_log)")
    columns = {row[1] for row in cursor.fetchall()}

    new_columns = [
        ("films_seen", "TEXT"),
        ("concerts_seen", "TEXT"),
        ("expos_seen", "TEXT"),
        ("hiking_seen", "TEXT"),
        ("cycling_seen", "TEXT"),
        ("restaurants_seen", "TEXT"),
        ("stayed_home_reason", "TEXT"),
    ]

    for col_name, col_type in new_columns:
        if col_name not in columns:
            try:
                cursor.execute(f"ALTER TABLE activity_log ADD COLUMN {col_name} {col_type}")
            except Exception:
                # Colonne déjà ajoutée par un autre worker (race condition)
                pass


def _populate_initial_profile(cursor):
    """Insère ou met à jour le profil utilisateur."""
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
            "Fondation Beyeler Riehen/Bâle",
            "Fondation Schneider Wattwiller",
            "Espace Fernet-Branca Saint-Louis",
            "Musée Würth Erstein"
        ],
        "expo_cities": ["Bâle", "Strasbourg", "Mulhouse", "Belfort", "Besançon"],
        "hike_max_elev": 300,
        "hike_prefer_loop": True,
        "cinema_sources": ["Télérama", "Cahiers du Cinéma"]
    }

    # Clés à forcer la mise à jour (même si déjà présentes)
    force_update_keys = {"expo_fondations"}

    for key, value in initial_profile.items():
        if key in force_update_keys:
            # Mise à jour forcée via ON CONFLICT
            cursor.execute("""
                INSERT INTO user_profile (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
            """, (key, json.dumps(value, ensure_ascii=False), datetime.now().isoformat()))
        else:
            # Insertion uniquement si absent
            cursor.execute("""
                INSERT OR IGNORE INTO user_profile (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, json.dumps(value, ensure_ascii=False), datetime.now().isoformat()))


def _populate_initial_projects(cursor):
    """Insère les projets de vie initiaux."""
    initial_projects = [
        {
            "title": "Voir une expo Klimt",
            "category": "culture",
            "keywords": ["klimt", "symbolisme", "vienne", "expo"],
            "priority": 2
        },
        {
            "title": "Faire l'EuroVelo 15 — Rhin",
            "category": "sport",
            "keywords": ["eurovelo", "rhin", "velo", "cyclable"],
            "priority": 2
        },
        {
            "title": "Week-end à Vienne",
            "category": "voyage",
            "keywords": ["vienne", "autriche", "wien"],
            "priority": 2
        },
        {
            "title": "Concert The Cure",
            "category": "culture",
            "keywords": ["the cure", "cure", "concert"],
            "priority": 1
        },
        {
            "title": "Voir les Cinque Terre",
            "category": "voyage",
            "keywords": ["cinque terre", "ligurie", "italie"],
            "priority": 2
        },
        {
            "title": "Expo surréaliste à Bâle ou Strasbourg",
            "category": "culture",
            "keywords": ["surrealisme", "dali", "magritte", "expo", "surrealiste"],
            "priority": 2
        },
        {
            "title": "Week-end à Londres pour Géraldine",
            "category": "voyage",
            "keywords": ["londres", "london", "uk", "angleterre"],
            "priority": 3
        },
        {
            "title": "Randonnée GR5 — étape Vosges",
            "category": "sport",
            "keywords": ["gr5", "vosges", "grande randonnee"],
            "priority": 1
        }
    ]

    for project in initial_projects:
        cursor.execute("""
            INSERT OR IGNORE INTO life_projects (title, category, keywords, priority)
            SELECT ?, ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM life_projects WHERE title = ?
            )
        """, (
            project["title"],
            project["category"],
            json.dumps(project["keywords"], ensure_ascii=False),
            project["priority"],
            project["title"]
        ))


# Initialiser la DB au premier import
init_db()
