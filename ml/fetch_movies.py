"""
fetch_movies.py - Multi-Language TMDB Movie Dataset Creator
Fetches movies across 6 languages:
- English (Hollywood)
- Hindi (Bollywood)
- Kannada (Sandalwood)
- Tamil (Kollywood)
- Telugu (Tollywood)
- Malayalam (Mollywood)

Saves to data/movies_all.csv and caches to data/cache.json.
"""
import os
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import requests
from dotenv import load_dotenv

# Safe UTF-8 console output for Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Safe DNS resolver for TMDB in restricted ISP environments
try:
    import urllib3.util.connection as urllib_conn
    _orig_create_connection = urllib_conn.create_connection

    def _safe_create_connection(address, *args, **kwargs):
        host, port = address
        if host == "api.themoviedb.org":
            return _orig_create_connection(("3.175.86.37", port), *args, **kwargs)
        return _orig_create_connection(address, *args, **kwargs)

    urllib_conn.create_connection = _safe_create_connection
except Exception:
    pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
CACHE_FILE = os.path.join(DATA_DIR, "cache.json")
OUTPUT_CSV = os.path.join(DATA_DIR, "movies_all.csv")
os.makedirs(DATA_DIR, exist_ok=True)

load_dotenv(os.path.join(ROOT_DIR, ".env"))
TMDB_KEY = os.getenv("TMDB_API_KEY", "").strip()
TMDB_BASE = "https://api.themoviedb.org/3"
IMG_W500 = "https://image.tmdb.org/t/p/w500"
IMG_W780 = "https://image.tmdb.org/t/p/w780"

LANGS = {
    "en": {"name": "English", "industry": "Hollywood", "font": "Poppins"},
    "hi": {"name": "हिन्दी", "industry": "Bollywood", "font": "Noto Sans Devanagari"},
    "kn": {"name": "ಕನ್ನಡ", "industry": "Sandalwood", "font": "Noto Sans Kannada"},
    "ta": {"name": "தமிழ்", "industry": "Kollywood", "font": "Noto Sans Tamil"},
    "te": {"name": "తెలుగు", "industry": "Tollywood", "font": "Noto Sans Telugu"},
    "ml": {"name": "മലയാളം", "industry": "Mollywood", "font": "Noto Sans Malayalam"}
}

GENRE_MAP = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
    27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance", 878: "Sci-Fi",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western"
}


def fetch_details(tmdb_id, max_retries=3):
    """Fetches full movie details including runtime and genres."""
    url = f"{TMDB_BASE}/movie/{tmdb_id}"
    params = {"api_key": TMDB_KEY, "language": "en-US"}
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=6)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(0.8 * (attempt + 1))
            elif resp.status_code == 404:
                return None
        except Exception:
            time.sleep(0.4)
    return None


def fetch_all_languages(max_pages_per_lang=25, max_workers=10):
    if not TMDB_KEY or TMDB_KEY == "your_tmdb_api_key_here":
        print("[ERROR] TMDB_API_KEY is missing from .env!", flush=True)
        return

    # Load existing cache
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"[INFO] Loaded {len(cache)} existing cached movies from {CACHE_FILE}", flush=True)
        except Exception as e:
            print(f"[WARN] Error reading cache: {e}", flush=True)

    session = requests.Session()
    all_movies = []

    for lang_code, meta in LANGS.items():
        min_votes = 20 if lang_code in ("kn", "ml") else 50
        industry = meta["industry"]
        print(f"\n[INFO] Discovering {lang_code.upper()} - {industry} (min_votes={min_votes})...", flush=True)

        discovered = []
        for page in range(1, max_pages_per_lang + 1):
            url = f"{TMDB_BASE}/discover/movie"
            params = {
                "api_key": TMDB_KEY,
                "with_original_language": lang_code,
                "sort_by": "vote_count.desc",
                "vote_count.gte": min_votes,
                "page": page,
                "language": "en-US"
            }
            try:
                r = session.get(url, params=params, timeout=8)
                if r.status_code != 200:
                    break
                data = r.json()
                results = data.get("results", [])
                if not results:
                    break
                for item in results:
                    if item.get("poster_path"):
                        discovered.append(item)
                if page >= data.get("total_pages", 1):
                    break
            except Exception as e:
                print(f"  [WARN] Page {page} failed: {e}", flush=True)
                break

        print(f"  Found {len(discovered)} candidates for {lang_code.upper()}.", flush=True)

        to_fetch = []
        for basic in discovered:
            mid = basic["id"]
            s_mid = str(mid)
            if s_mid in cache and cache[s_mid].get("runtime") is not None:
                cached_entry = dict(cache[s_mid])
                cached_entry["lang"] = lang_code
                cached_entry["industry"] = industry
                all_movies.append(cached_entry)
            else:
                to_fetch.append(basic)

        print(f"  {len(discovered) - len(to_fetch)} cached, fetching {len(to_fetch)} details with {max_workers} threads...", flush=True)

        if to_fetch:
            completed_in_lang = 0
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(fetch_details, basic["id"]): basic
                    for basic in to_fetch
                }
                for fut in as_completed(future_map):
                    basic = future_map[fut]
                    mid = basic["id"]
                    try:
                        detail = fut.result()
                    except Exception:
                        detail = None

                    src = detail if detail else basic
                    poster_path = src.get("poster_path") or basic.get("poster_path")
                    if not poster_path:
                        continue

                    backdrop_path = src.get("backdrop_path") or basic.get("backdrop_path")
                    
                    # Resolve genres
                    if "genres" in src and isinstance(src["genres"], list) and src["genres"] and isinstance(src["genres"][0], dict):
                        genres_str = "|".join([g["name"] for g in src["genres"] if "name" in g])
                    elif "genre_ids" in basic and basic["genre_ids"]:
                        genres_str = "|".join([GENRE_MAP.get(gid, "Drama") for gid in basic["genre_ids"]])
                    else:
                        genres_str = "Drama"

                    rel_date = src.get("release_date") or basic.get("release_date") or ""
                    year = int(rel_date[:4]) if len(rel_date) >= 4 and rel_date[:4].isdigit() else 2020

                    entry = {
                        "tmdb_id": int(mid),
                        "lang": lang_code,
                        "industry": industry,
                        "title_en": src.get("title") or basic.get("title") or "Unknown",
                        "title_native": src.get("original_title") or basic.get("original_title") or src.get("title") or "Unknown",
                        "year": year,
                        "genres": genres_str or "Drama",
                        "runtime": int(src.get("runtime") or 125),
                        "vote_average": round(float(src.get("vote_average") or basic.get("vote_average") or 6.5), 2),
                        "vote_count": int(src.get("vote_count") or basic.get("vote_count") or 100),
                        "popularity": round(float(src.get("popularity") or basic.get("popularity") or 10.0), 2),
                        "overview": src.get("overview") or basic.get("overview") or "",
                        "poster_url": f"{IMG_W500}{poster_path}",
                        "backdrop_url": f"{IMG_W780}{backdrop_path}" if backdrop_path else ""
                    }
                    cache[str(mid)] = entry
                    all_movies.append(entry)
                    completed_in_lang += 1
                    if completed_in_lang % 50 == 0 or completed_in_lang == len(to_fetch):
                        print(f"    progress: {completed_in_lang}/{len(to_fetch)}", flush=True)

        # Save cache periodically
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"\n[INFO] Total cached items: {len(cache)}", flush=True)

    # Build DataFrame & clean
    df = pd.DataFrame(all_movies)
    df = df.drop_duplicates(subset=["tmdb_id"]).reset_index(drop=True)
    df = df[df["poster_url"].notna() & (df["poster_url"] != "")]

    # Save to data/movies_all.csv
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"[SUCCESS] Saved {len(df)} total multi-language movies to {OUTPUT_CSV}", flush=True)
    print("\nSummary by language:", flush=True)
    for lcode, count in df["lang"].value_counts().items():
        ind = LANGS.get(lcode, {}).get("industry", lcode)
        print(f"  {lcode.upper()} ({ind:<11}): {count} movies", flush=True)


if __name__ == "__main__":
    fetch_all_languages(max_pages_per_lang=25, max_workers=10)
