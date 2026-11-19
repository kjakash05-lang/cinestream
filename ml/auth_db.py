"""
auth_db.py - Authentication, User Profile, and Preferences Storage
Manages users, hashed passwords, preferences, ratings, interactions,
and anonymous session migration in data/cinestream.db.
"""
import os
import json
import sqlite3
import uuid
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "cinestream.db")

def get_connection():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_auth_db():
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    avatar TEXT DEFAULT 'avatar-1',
                    favorite_genres TEXT DEFAULT '[]',
                    preferred_languages TEXT DEFAULT '["all"]',
                    preferred_audio_lang TEXT DEFAULT 'en',
                    favorite_tabs TEXT DEFAULT '["all"]',
                    adult_content INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_ratings (
                    user_id TEXT NOT NULL,
                    tmdb_id INTEGER NOT NULL,
                    rating REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, tmdb_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_interactions (
                    user_id TEXT NOT NULL,
                    tmdb_id INTEGER NOT NULL,
                    interaction_type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, tmdb_id, interaction_type)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    message TEXT NOT NULL,
                    movies_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ratings_user ON user_ratings(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_interactions_user ON user_interactions(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_id)")
    finally:
        conn.close()

# Initialize tables immediately
init_auth_db()

class AuthUser(UserMixin):
    """Flask-Login compatible user wrapper."""
    def __init__(self, user_dict):
        self.id = user_dict["id"]
        self.username = user_dict["username"]
        self.display_name = user_dict.get("display_name") or user_dict["username"]
        self.avatar = user_dict.get("avatar", "avatar-1")
        self.created_at = user_dict.get("created_at")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "avatar": self.avatar,
            "created_at": str(self.created_at) if self.created_at else None
        }

def create_user(username, password, display_name=None):
    """
    Creates a new user and returns AuthUser or raises ValueError if username exists.
    """
    username = username.strip().lower()
    if not username or len(username) < 3:
        raise ValueError("Username must be at least 3 characters.")
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    pwd_hash = generate_password_hash(password)
    display = (display_name or username).strip()

    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
                (user_id, username, pwd_hash)
            )
            conn.execute(
                """
                INSERT INTO user_preferences (user_id, display_name, avatar, favorite_genres, preferred_languages)
                VALUES (?, ?, 'avatar-1', '[]', '["all"]')
                """,
                (user_id, display)
            )
        return get_user_by_id(user_id)
    except sqlite3.IntegrityError:
        raise ValueError("Username is already taken.")
    finally:
        conn.close()

def get_user_by_id(user_id):
    """Returns AuthUser or None."""
    if not user_id:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.created_at, p.display_name, p.avatar
            FROM users u
            LEFT JOIN user_preferences p ON u.id = p.user_id
            WHERE u.id = ?
            """,
            (user_id,)
        ).fetchone()
        if row:
            return AuthUser(dict(row))
        return None
    finally:
        conn.close()

def get_user_by_username(username):
    """Returns raw sqlite row dict with password_hash or None."""
    if not username:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(username) = ?",
            (username.strip().lower(),)
        ).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()

def verify_user(username, password):
    """Verifies credentials and returns AuthUser or None."""
    user_row = get_user_by_username(username)
    if not user_row:
        return None
    if check_password_hash(user_row["password_hash"], password):
        return get_user_by_id(user_row["id"])
    return None

def get_user_preferences(user_id):
    """Returns preferences dict for user_id or sensible defaults."""
    default_prefs = {
        "user_id": user_id,
        "display_name": "",
        "avatar": "avatar-1",
        "favorite_genres": [],
        "preferred_languages": ["all"],
        "preferred_audio_lang": "en",
        "favorite_tabs": ["all"],
        "adult_content": 0,
        "updated_at": None
    }
    if not user_id:
        return default_prefs

    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return default_prefs
        d = dict(row)
        for json_col in ["favorite_genres", "preferred_languages", "favorite_tabs"]:
            if isinstance(d.get(json_col), str):
                try:
                    d[json_col] = json.loads(d[json_col])
                except Exception:
                    d[json_col] = []
        return d
    finally:
        conn.close()

def update_user_preferences(user_id, prefs):
    """Updates user preferences, creating row if missing."""
    if not user_id:
        return False
    display_name = prefs.get("display_name", "").strip()
    avatar = prefs.get("avatar", "avatar-1")
    fav_genres = json.dumps(prefs.get("favorite_genres", []))
    pref_langs = json.dumps(prefs.get("preferred_languages", ["all"]))
    pref_audio = prefs.get("preferred_audio_lang", "en")
    fav_tabs = json.dumps(prefs.get("favorite_tabs", ["all"]))
    adult = 1 if prefs.get("adult_content") else 0

    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO user_preferences (user_id, display_name, avatar, favorite_genres, preferred_languages, preferred_audio_lang, favorite_tabs, adult_content, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    avatar = excluded.avatar,
                    favorite_genres = excluded.favorite_genres,
                    preferred_languages = excluded.preferred_languages,
                    preferred_audio_lang = excluded.preferred_audio_lang,
                    favorite_tabs = excluded.favorite_tabs,
                    adult_content = excluded.adult_content,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, display_name, avatar, fav_genres, pref_langs, pref_audio, fav_tabs, adult)
            )
        return True
    finally:
        conn.close()

def record_user_rating(user_id, tmdb_id, rating):
    """Inserts or updates a user rating (1.0 to 5.0)."""
    if not user_id or not tmdb_id:
        return False
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO user_ratings (user_id, tmdb_id, rating, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, tmdb_id) DO UPDATE SET
                    rating = excluded.rating,
                    created_at = CURRENT_TIMESTAMP
                """,
                (user_id, int(tmdb_id), float(rating))
            )
        return True
    finally:
        conn.close()

def get_user_ratings(user_id):
    """Returns dict of {tmdb_id: rating} for user_id."""
    if not user_id:
        return {}
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT tmdb_id, rating FROM user_ratings WHERE user_id = ?",
            (user_id,)
        ).fetchall()
        return {r["tmdb_id"]: r["rating"] for r in rows}
    finally:
        conn.close()

def record_user_interaction(user_id, tmdb_id, interaction_type):
    """Records interaction: 'not_interested', 'clicked', 'viewed'."""
    if not user_id or not tmdb_id:
        return False
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO user_interactions (user_id, tmdb_id, interaction_type, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, tmdb_id, interaction_type) DO UPDATE SET
                    created_at = CURRENT_TIMESTAMP
                """,
                (user_id, int(tmdb_id), interaction_type)
            )
        return True
    finally:
        conn.close()

def get_user_dismissed_ids(user_id):
    """Returns set of tmdb_ids marked 'not_interested'."""
    if not user_id:
        return set()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT tmdb_id FROM user_interactions WHERE user_id = ? AND interaction_type = 'not_interested'",
            (user_id,)
        ).fetchall()
        return {r["tmdb_id"] for r in rows}
    finally:
        conn.close()

def migrate_anonymous_data(anon_uid, user_id):
    """
    Migrates watchlist entries, ratings, and interactions from anonymous cookie
    uid into permanent user_id, merging without errors.
    """
    if not anon_uid or not user_id or anon_uid == user_id:
        return 0

    conn = get_connection()
    migrated_count = 0
    try:
        with conn:
            # 1. Watchlist migration
            watchlist_items = conn.execute(
                "SELECT * FROM watchlist WHERE user_id = ?", (anon_uid,)
            ).fetchall()
            for item in watchlist_items:
                conn.execute(
                    """
                    INSERT INTO watchlist (user_id, tmdb_id, media_type, added_at, watched, rating, position)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, tmdb_id, media_type) DO UPDATE SET
                        watched = MAX(watchlist.watched, excluded.watched),
                        rating = COALESCE(excluded.rating, watchlist.rating)
                    """,
                    (user_id, item["tmdb_id"], item["media_type"], item["added_at"],
                     item["watched"], item["rating"], item["position"])
                )
                migrated_count += 1
            conn.execute("DELETE FROM watchlist WHERE user_id = ?", (anon_uid,))

            # 2. Ratings migration
            ratings = conn.execute(
                "SELECT * FROM user_ratings WHERE user_id = ?", (anon_uid,)
            ).fetchall()
            for r in ratings:
                conn.execute(
                    """
                    INSERT INTO user_ratings (user_id, tmdb_id, rating, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, tmdb_id) DO UPDATE SET
                        rating = excluded.rating
                    """,
                    (user_id, r["tmdb_id"], r["rating"], r["created_at"])
                )
            conn.execute("DELETE FROM user_ratings WHERE user_id = ?", (anon_uid,))

            # 3. Interactions migration
            interactions = conn.execute(
                "SELECT * FROM user_interactions WHERE user_id = ?", (anon_uid,)
            ).fetchall()
            for inter in interactions:
                conn.execute(
                    """
                    INSERT INTO user_interactions (user_id, tmdb_id, interaction_type, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, tmdb_id, interaction_type) DO NOTHING
                    """,
                    (user_id, inter["tmdb_id"], inter["interaction_type"], inter["created_at"])
                )
            conn.execute("DELETE FROM user_interactions WHERE user_id = ?", (anon_uid,))

        return migrated_count
    finally:
        conn.close()

def delete_user_account(user_id):
    """Permanently deletes user, preferences, watchlist, ratings, interactions, and chat history."""
    if not user_id:
        return False
    conn = get_connection()
    try:
        with conn:
            conn.execute("DELETE FROM watchlist WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM user_ratings WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM user_interactions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return True
    finally:
        conn.close()
