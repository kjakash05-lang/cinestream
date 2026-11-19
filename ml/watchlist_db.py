"""
watchlist_db.py - SQLite Storage Layer for CineStream Watchlist
Manages watchlist entries, watched state, ratings, and custom positions in data/cinestream.db.
"""
import os
import sqlite3
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "cinestream.db")

def get_connection():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    user_id TEXT NOT NULL,
                    tmdb_id INTEGER NOT NULL,
                    media_type TEXT NOT NULL DEFAULT 'movie',
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    watched INTEGER DEFAULT 0,
                    rating REAL,
                    position INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, tmdb_id, media_type)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id)")
    finally:
        conn.close()

# Auto-initialize table on import
init_db()

def get_watchlist(user_id, media_type=None, watched=None, sort_by=None):
    """
    Returns list of watchlist rows for a user_id.
    """
    conn = get_connection()
    try:
        query = "SELECT * FROM watchlist WHERE user_id = ?"
        params = [user_id]

        if media_type and media_type.lower() not in ("all", ""):
            query += " AND LOWER(media_type) = ?"
            params.append(media_type.lower())

        if watched is not None:
            query += " AND watched = ?"
            params.append(1 if watched else 0)

        # Sorting
        if sort_by == "title_asc":
            # Handled in application layer after join with metadata
            query += " ORDER BY position ASC, added_at DESC"
        elif sort_by == "year_desc":
            query += " ORDER BY position ASC, added_at DESC"
        elif sort_by == "rating_desc":
            query += " ORDER BY rating DESC, added_at DESC"
        elif sort_by == "custom":
            query += " ORDER BY position ASC, added_at DESC"
        else: # recently_added
            query += " ORDER BY added_at DESC"

        cursor = conn.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        return rows
    finally:
        conn.close()

def add_to_watchlist(user_id, tmdb_id, media_type="movie"):
    """
    Adds or ensures a movie/show is in user's watchlist.
    """
    conn = get_connection()
    try:
        with conn:
            # Get max position for custom order
            cur = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM watchlist WHERE user_id = ?", (user_id,))
            next_pos = cur.fetchone()[0]

            conn.execute("""
                INSERT INTO watchlist (user_id, tmdb_id, media_type, added_at, watched, position)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, 0, ?)
                ON CONFLICT(user_id, tmdb_id, media_type) DO NOTHING
            """, (user_id, int(tmdb_id), str(media_type).lower(), next_pos))
        return True
    except Exception as e:
        print(f"[watchlist_db] Error adding to watchlist: {e}")
        return False
    finally:
        conn.close()

def remove_from_watchlist(user_id, media_type, tmdb_id):
    """
    Removes an item from user's watchlist.
    """
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute("""
                DELETE FROM watchlist
                WHERE user_id = ? AND media_type = ? AND tmdb_id = ?
            """, (user_id, str(media_type).lower(), int(tmdb_id)))
            return cur.rowcount > 0
    except Exception as e:
        print(f"[watchlist_db] Error removing from watchlist: {e}")
        return False
    finally:
        conn.close()

def update_watchlist_item(user_id, media_type, tmdb_id, watched=None, rating=None, position=None):
    """
    Updates watched state, user rating, or custom position.
    """
    conn = get_connection()
    try:
        updates = []
        params = []
        if watched is not None:
            updates.append("watched = ?")
            params.append(1 if watched else 0)
        if rating is not None:
            updates.append("rating = ?")
            params.append(float(rating) if rating > 0 else None)
        if position is not None:
            updates.append("position = ?")
            params.append(int(position))

        if not updates:
            return True

        query = f"UPDATE watchlist SET {', '.join(updates)} WHERE user_id = ? AND media_type = ? AND tmdb_id = ?"
        params.extend([user_id, str(media_type).lower(), int(tmdb_id)])

        with conn:
            cur = conn.execute(query, params)
            return cur.rowcount > 0
    except Exception as e:
        print(f"[watchlist_db] Error updating watchlist item: {e}")
        return False
    finally:
        conn.close()

def clear_watchlist(user_id):
    """
    Clears all watchlist items for a user.
    """
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute("DELETE FROM watchlist WHERE user_id = ?", (user_id,))
            return cur.rowcount
    except Exception as e:
        print(f"[watchlist_db] Error clearing watchlist: {e}")
        return 0
    finally:
        conn.close()

def reorder_watchlist(user_id, items):
    """
    items: list of dicts with tmdb_id, media_type, position
    """
    conn = get_connection()
    try:
        with conn:
            for it in items:
                conn.execute(
                    "UPDATE watchlist SET position = ? WHERE user_id = ? AND media_type = ? AND tmdb_id = ?",
                    (int(it["position"]), user_id, str(it.get("media_type", "movie")).lower(), int(it["tmdb_id"]))
                )
        return True
    except Exception as e:
        print(f"[watchlist_db] Error reordering watchlist: {e}")
        return False
    finally:
        conn.close()

def get_watchlist_count(user_id):
    """
    Returns total count of items in user's watchlist.
    """
    conn = get_connection()
    try:
        cur = conn.execute("SELECT COUNT(*) FROM watchlist WHERE user_id = ?", (user_id,))
        return cur.fetchone()[0]
    finally:
        conn.close()

def get_user_implicit_ratings(user_id, default_implicit=4.0):
    """
    Returns a dict {movieId: rating} for ML recommender.
    Saved items get implicit rating default_implicit (4.0).
    Watched items with a user rating use that rating.
    """
    items = get_watchlist(user_id)
    ratings = {}
    for item in items:
        mid = item["tmdb_id"]
        if item.get("watched") and item.get("rating") is not None and item["rating"] > 0:
            ratings[mid] = float(item["rating"])
        else:
            ratings[mid] = float(default_implicit)
    return ratings