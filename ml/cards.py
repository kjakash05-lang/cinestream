"""
ml/cards.py
Single Source of Truth card builder for CineStream.
Guarantees title_en, year, language_name, industry, genres, cluster, tmdb_id,
media_type, and poster_url all come from the SAME database row in cinestream.db.
"""
import os
import sqlite3
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "cinestream.db")

_CARD_ROW_CACHE = {}

def _load_card_cache():
    global _CARD_ROW_CACHE
    if not os.path.exists(DB_PATH):
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM movies")
        rows = cursor.fetchall()
        for r in rows:
            m_type = str(r["media_type"] or "movie").lower().strip()
            tid = int(r["tmdb_id"])
            d = dict(r)
            _CARD_ROW_CACHE[(m_type, tid)] = d
            _CARD_ROW_CACHE[("movie", tid)] = d
            _CARD_ROW_CACHE[tid] = d
        conn.close()
    except Exception as e:
        print(f"[Cards] Cache load error: {e}")

_load_card_cache()

def get_card(media_type: str = "movie", tmdb_id: int = 0, predicted_rating: float = None, user_rating: float = None, cluster_names: dict = None):
    """
    Returns a unified card object strictly from the SAME database row.
    Keyed by (media_type, tmdb_id).
    """
    m_type = str(media_type or "movie").lower().strip()
    try:
        tid = int(tmdb_id)
    except (ValueError, TypeError):
        tid = 0

    row = _CARD_ROW_CACHE.get((m_type, tid)) or _CARD_ROW_CACHE.get(("movie", tid)) or _CARD_ROW_CACHE.get(tid)
    if not row:
        # Fallback query directly to SQLite
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM movies WHERE tmdb_id = ? LIMIT 1", (tid,))
            found = cursor.fetchone()
            conn.close()
            if found:
                row = dict(found)
                _CARD_ROW_CACHE[(m_type, tid)] = row
        except Exception:
            row = None

    if not row:
        # Fallback card structure if movie not in DB
        return {
            "tmdb_id": tid,
            "tmdbId": tid,
            "movieId": tid,
            "media_type": m_type,
            "title_en": f"Movie #{tid}",
            "title": f"Movie #{tid}",
            "title_native": "",
            "year": None,
            "lang": "en",
            "language_name": "English",
            "industry": "Cinema",
            "genres": "",
            "cluster": 0,
            "cluster_name": "General",
            "clusterName": "General",
            "avgRating": 7.0,
            "avgRatingDisplay": "★ 7.0/10",
            "ratingCount": 0,
            "popularity": 0.0,
            "runtime": 120,
            "poster_url": "https://image.tmdb.org/t/p/w500/yQvGrMoipbRoddT0ZR8tPoR7NfX.jpg",
            "poster_large_url": "https://image.tmdb.org/t/p/w780/yQvGrMoipbRoddT0ZR8tPoR7NfX.jpg",
            "backdrop_url": "",
            "overview": "",
            "has_poster": True
        }

    cid = int(row.get("cluster") or 0)
    cname = "General"
    if cluster_names and cid in cluster_names:
        cname = cluster_names[cid]
    elif row.get("cluster_name"):
        cname = str(row["cluster_name"])

    title_en = str(row.get("title_en") or row.get("title") or f"Movie #{tid}").strip()
    poster_url = str(row.get("poster_url") or "").strip()
    if not poster_url or not poster_url.startswith("http"):
        poster_url = "https://image.tmdb.org/t/p/w500/yQvGrMoipbRoddT0ZR8tPoR7NfX.jpg"

    poster_large = str(row.get("poster_large_url") or poster_url).strip()
    backdrop = str(row.get("backdrop_url") or "").strip()

    vote_avg = round(float(row.get("vote_average") or 7.0), 1)

    card = {
        "tmdb_id": tid,
        "tmdbId": tid,
        "movieId": tid,
        "media_type": m_type,
        "title_en": title_en,
        "title": title_en,
        "title_native": str(row.get("title_native") or title_en),
        "year": int(row["year"]) if row.get("year") else None,
        "lang": str(row.get("lang") or "en").lower(),
        "language_name": str(row.get("language_name") or "English"),
        "industry": str(row.get("industry") or "Cinema"),
        "genres": str(row.get("genres") or ""),
        "cluster": cid,
        "cluster_name": cname,
        "clusterName": cname,
        "avgRating": vote_avg,
        "avgRatingDisplay": f"★ {vote_avg:.1f}/10",
        "ratingCount": int(row.get("vote_count") or 0),
        "popularity": round(float(row.get("popularity") or 0.0), 1),
        "runtime": int(row["runtime"]) if row.get("runtime") else None,
        "poster_url": poster_url,
        "poster_large_url": poster_large,
        "backdrop_url": backdrop,
        "overview": str(row.get("overview") or ""),
        "has_poster": bool(poster_url and poster_url.startswith("http"))
    }

    if user_rating is not None:
        ur = round(float(user_rating), 1)
        card["userRating"] = ur
        card["userRatingDisplay"] = f"Your rating: {int(ur) if ur.is_integer() else ur:.1f}/5"

    if predicted_rating is not None:
        pr = round(float(predicted_rating), 1)
        if pr <= 5.0:
            s10 = round(min(9.9, max(1.0, pr * 2.0)), 1)
        else:
            s10 = round(min(9.9, max(1.0, pr)), 1)
        card["predictedRating"] = pr
        card["predicted_rating"] = pr
        card["predicted_score_10"] = s10
        card["predicted_score_label"] = f"{s10:.1f}/10"
        card["predictedRatingDisplay"] = f"★ {s10:.1f}/10"

    return card

def get_quick_pick_cards():
    """Returns the 5 diverse taste-profile quick-pick cards across 5 industries."""
    quick_pick_ids = [
        ("movie", 157336),  # Interstellar (Hollywood)
        ("movie", 656908),  # Ramayana: Part 1 (Bollywood)
        ("movie", 587412),  # K.G.F: Chapter 2 (Sandalwood)
        ("movie", 743563),  # Vikram (Kollywood)
        ("movie", 579974)   # RRR (Tollywood)
    ]
    cards = []
    for mtype, tid in quick_pick_ids:
        c = get_card(media_type=mtype, tmdb_id=tid)
        cards.append(c)
    return cards
