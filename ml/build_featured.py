"""
ml/build_featured.py
Automatically builds data/featured_by_language.json for CineStream.
Supports: all, en, hi, kn, ta, te, ml.
Pulls English metadata (title, overview, genres, cast) and official YouTube trailers from TMDB.
Run: python ml/build_featured.py
"""
import os
import sys
import json
import time
import requests
from dotenv import load_dotenv

# Safe UTF-8 console output for Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# DNS workaround for TMDB in restricted environments
try:
    import urllib3.util.connection as urllib_conn
    _orig = urllib_conn.create_connection

    def _safe_conn(address, *args, **kwargs):
        host, port = address
        if host == "api.themoviedb.org":
            return _orig(("3.175.86.37", port), *args, **kwargs)
        return _orig(address, *args, **kwargs)

    urllib_conn.create_connection = _safe_conn
except Exception:
    pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
CURATED_FEATURED_PATH = os.path.join(DATA_DIR, "featured.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "featured_by_language.json")

load_dotenv(os.path.join(ROOT_DIR, ".env"))
TMDB_KEY = os.getenv("TMDB_API_KEY", "").strip()
TMDB_BASE = "https://api.themoviedb.org/3"
IMG_W780 = "https://image.tmdb.org/t/p/w780"
IMG_W1280 = "https://image.tmdb.org/t/p/w1280"

LANG_INFO = {
    "all": {"name": "All", "industry": "Global"},
    "en": {"name": "English", "industry": "Hollywood"},
    "hi": {"name": "Hindi", "industry": "Bollywood"},
    "kn": {"name": "Kannada", "industry": "Sandalwood"},
    "ta": {"name": "Tamil", "industry": "Kollywood"},
    "te": {"name": "Telugu", "industry": "Tollywood"},
    "ml": {"name": "Malayalam", "industry": "Mollywood"}
}

def tmdb_get(endpoint, params=None, max_retries=3):
    if not TMDB_KEY:
        return None
    url = f"{TMDB_BASE}{endpoint}"
    p = {"api_key": TMDB_KEY}
    if params:
        p.update(params)
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=p, timeout=8)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(1.0 * (attempt + 1))
            elif resp.status_code == 404:
                return None
        except Exception:
            time.sleep(0.5)
    return None

def fetch_movie_trailers(tmdb_id):
    """Fetches trailers from TMDB across multiple languages."""
    data = tmdb_get(f"/movie/{tmdb_id}/videos", {"include_video_language": "en,hi,kn,ta,te,ml,null"})
    if not data or "results" not in data:
        return {}
    trailers = {}
    for v in data["results"]:
        if v.get("site") == "YouTube":
            lang = v.get("iso_639_1") or "en"
            key = v.get("key")
            vtype = v.get("type", "")
            if vtype == "Trailer" and lang not in trailers and key:
                trailers[lang] = key
    for v in data["results"]:
        if v.get("site") == "YouTube":
            lang = v.get("iso_639_1") or "en"
            key = v.get("key")
            if lang not in trailers and key:
                trailers[lang] = key
    return trailers

def fetch_full_movie_info(tmdb_id, default_lang="en"):
    """Fetches English details, credits, and trailers for a movie."""
    details = tmdb_get(f"/movie/{tmdb_id}", {"language": "en-US", "append_to_response": "credits"})
    if not details:
        return None

    credits = details.get("credits", {})
    cast_list = [c["name"] for c in credits.get("cast", [])[:5]]
    director = ""
    for crew in credits.get("crew", []):
        if crew.get("job") == "Director":
            director = crew.get("name")
            break

    genres = [g["name"] for g in details.get("genres", [])]
    genres_formatted = " • ".join(genres[:3]) if genres else "Drama • Action"

    trailers = fetch_movie_trailers(tmdb_id)
    poster_path = details.get("poster_path")
    backdrop_path = details.get("backdrop_path")

    title = details.get("title") or details.get("original_title") or "Movie"
    slug = title.lower().replace(":", "").replace(" - ", "-").replace(" ", "-").replace("'", "")
    slug = "".join(c for c in slug if c.isalnum() or c == "-").strip("-")

    year = 2024
    rel_date = details.get("release_date", "")
    if rel_date and len(rel_date) >= 4:
        try:
            year = int(rel_date[:4])
        except ValueError:
            pass

    return {
        "slug": slug,
        "title": title,
        "year": year,
        "director": director or "Acclaimed Director",
        "cast": ", ".join(cast_list) if cast_list else "Ensemble Cast",
        "genres": genres,
        "genres_formatted": genres_formatted,
        "tmdb_id": tmdb_id,
        "poster_url": f"{IMG_W780}{poster_path}" if poster_path else "https://image.tmdb.org/t/p/w780/jIsKmkxMzdCZ0Ux1GVSnu8m6Na6.jpg",
        "backdrop_url": f"{IMG_W1280}{backdrop_path}" if backdrop_path else "https://image.tmdb.org/t/p/w1280/kXElm7wt2kAXEVwJqW4cFhP43nW.jpg",
        "trailers": trailers,
        "default_lang": default_lang,
        "original_lang": details.get("original_language", default_lang),
        "is_now_showing": False,
        "badge_text": "BLOCKBUSTER" if details.get("popularity", 0) > 80 else "",
        "overview": details.get("overview") or "An extraordinary cinematic journey combining breathtaking visuals and unforgettable storytelling."
    }

def build_all_featured():
    print("[INFO] Building multi-language featured dataset for CineStream...", flush=True)

    curated = []
    if os.path.exists(CURATED_FEATURED_PATH):
        with open(CURATED_FEATURED_PATH, "r", encoding="utf-8") as f:
            curated = json.load(f)

    curated_by_id = {m.get("tmdb_id"): m for m in curated}
    kantara_id = 858485
    ramayana_id = 656908
    brahmastra_id = 496331
    sse_id = 1168104

    # Ensure curated movies have all TMDB fields updated if missing
    for m in curated:
        tmdb_id = m.get("tmdb_id")
        if tmdb_id:
            tmdb_trailers = fetch_movie_trailers(tmdb_id)
            existing_trailers = m.get("trailers", {})
            for lang_code, t_id in tmdb_trailers.items():
                if not existing_trailers.get(lang_code):
                    existing_trailers[lang_code] = t_id
            m["trailers"] = existing_trailers

    featured_by_lang = {}
    featured_by_lang["all"] = curated

    pinned_ids = {
        "hi": [ramayana_id, brahmastra_id, 939243, 786892],
        "kn": [kantara_id, sse_id, 1083862, 94997],
        "en": [693134, 872585, 945961, 763215],
        "ta": [969681, 987917, 870096, 736526],
        "te": [783832, 579974, 940551, 804616],
        "ml": [1078449, 1226578, 878077, 1014590]
    }

    for lang in ["en", "hi", "kn", "ta", "te", "ml"]:
        print(f"Fetching featured movies for language: {lang}...", flush=True)
        lang_movies = []
        seen_ids = set()

        for pid in pinned_ids.get(lang, []):
            if pid in curated_by_id:
                lang_movies.append(curated_by_id[pid])
                seen_ids.add(pid)
            else:
                info = fetch_full_movie_info(pid, default_lang=lang)
                if info and info.get("trailers"):
                    lang_movies.append(info)
                    seen_ids.add(pid)

        np_data = tmdb_get("/movie/now_playing", {"region": "IN", "language": "en-US"})
        if np_data and "results" in np_data:
            for item in np_data["results"]:
                if len(lang_movies) >= 6:
                    break
                m_id = item.get("id")
                orig_lang = item.get("original_language")
                if orig_lang == lang and m_id not in seen_ids:
                    info = fetch_full_movie_info(m_id, default_lang=lang)
                    if info and info.get("trailers"):
                        info["is_now_showing"] = True
                        info["badge_text"] = "NOW SHOWING IN THEATRES"
                        lang_movies.append(info)
                        seen_ids.add(m_id)

        disc = tmdb_get("/discover/movie", {
            "with_original_language": lang,
            "sort_by": "popularity.desc",
            "vote_count.gte": 20,
            "language": "en-US"
        })
        if disc and "results" in disc:
            for item in disc["results"]:
                if len(lang_movies) >= 6:
                    break
                m_id = item.get("id")
                if m_id not in seen_ids:
                    info = fetch_full_movie_info(m_id, default_lang=lang)
                    if info and info.get("trailers"):
                        lang_movies.append(info)
                        seen_ids.add(m_id)

        if len(lang_movies) < 4:
            for cm in curated:
                if cm.get("tmdb_id") not in seen_ids:
                    lang_movies.append(cm)
                    seen_ids.add(cm.get("tmdb_id"))
                if len(lang_movies) >= 4:
                    break

        print(f"  -> Got {len(lang_movies)} movies for {lang}.", flush=True)
        featured_by_lang[lang] = lang_movies

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(featured_by_lang, f, indent=2, ensure_ascii=False)

    print(f"[SUCCESS] Saved multi-language featured dataset to {OUTPUT_PATH}!", flush=True)

if __name__ == "__main__":
    build_all_featured()
