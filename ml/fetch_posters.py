"""
fetch_posters.py - CineStream TMDB Poster Fetcher
Fetches official posters and metadata for top-rated MovieLens movies using TMDB API.
Caches results to data/posters.json.
"""
import os
import re
import json
import time
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import requests
from dotenv import load_dotenv

# Bypass ISP DNS issues for api.themoviedb.org if needed
try:
    import urllib3.util.connection as urllib_conn
    _orig_create_connection = urllib_conn.create_connection

    def _safe_create_connection(address, *args, **kwargs):
        host, port = address
        if host == "api.themoviedb.org":
            # Real CloudFront IP for TMDB API
            return _orig_create_connection(("3.175.86.37", port), *args, **kwargs)
        return _orig_create_connection(address, *args, **kwargs)

    urllib_conn.create_connection = _safe_create_connection
except Exception:
    pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
CACHE_FILE = os.path.join(DATA_DIR, "posters.json")

load_dotenv(os.path.join(ROOT_DIR, ".env"))
TMDB_KEY = os.getenv("TMDB_API_KEY", "").strip()
TMDB_BASE = "https://api.themoviedb.org/3"
IMG_W500 = "https://image.tmdb.org/t/p/w500"
IMG_W780 = "https://image.tmdb.org/t/p/w780"


def clean_title_and_year(raw_title: str):
    """Extracts year and clean title from MovieLens format e.g. 'Toy Story (1995)'."""
    year_match = re.search(r"\((\d{4})\)$", raw_title.strip())
    year = year_match.group(1) if year_match else None
    clean_title = re.sub(r"\s*\(\d{4}\)\s*$", "", raw_title).strip()
    # Handle titles with ', The' or ', A'
    for suffix, prefix in [ (", The", "The "), (", A", "A "), (", An", "An ") ]:
        if clean_title.endswith(suffix):
            clean_title = prefix + clean_title[:-len(suffix)]
    return clean_title, year


def fetch_movie_from_tmdb(tmdb_id, title, year, max_retries=3):
    """Calls TMDB movie details endpoint, falling back to search."""
    session = requests.Session()
    
    # 1. Direct ID lookup
    if pd.notna(tmdb_id) and int(tmdb_id) > 0:
        url = f"{TMDB_BASE}/movie/{int(tmdb_id)}"
        params = {"api_key": TMDB_KEY, "language": "en-US"}
        for attempt in range(max_retries):
            try:
                resp = session.get(url, params=params, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("poster_path"):
                        return data
                elif resp.status_code == 429:
                    time.sleep(1.0 * (attempt + 1))
                elif resp.status_code == 404:
                    break
            except Exception:
                time.sleep(0.5)

    # 2. Search fallback
    search_url = f"{TMDB_BASE}/search/movie"
    params = {"api_key": TMDB_KEY, "query": title, "language": "en-US"}
    if year:
        params["year"] = str(year)
    
    for attempt in range(max_retries):
        try:
            resp = session.get(search_url, params=params, timeout=8)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                for item in results:
                    if item.get("poster_path"):
                        return item
            elif resp.status_code == 429:
                time.sleep(1.0 * (attempt + 1))
        except Exception:
            time.sleep(0.5)
            
    return None


def fetch_all_posters(top_n=300, max_workers=10):
    """Main worker to load top 300 movies and cache their posters."""
    if not TMDB_KEY or TMDB_KEY == "your_tmdb_api_key_here":
        print("[ERROR] TMDB_API_KEY is not configured in .env!")
        return

    # Load cache if existing
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"[INFO] Loaded {len(cache)} existing cached posters from {CACHE_FILE}")
        except Exception as e:
            print(f"[WARN] Could not parse cache: {e}")

    # Load datasets
    movies_df = pd.read_csv(os.path.join(DATA_DIR, "movies.csv"))
    ratings_df = pd.read_csv(os.path.join(DATA_DIR, "ratings.csv"))
    links_df = pd.read_csv(os.path.join(DATA_DIR, "links.csv"))

    # Top movies by rating count
    top_ratings = ratings_df.groupby("movieId").size().reset_index(name="rating_count")
    top_ratings = top_ratings.sort_values("rating_count", ascending=False).head(top_n)

    merged = top_ratings.merge(movies_df, on="movieId").merge(links_df, on="movieId")
    print(f"[INFO] Preparing to fetch posters for top {len(merged)} movies...")

    tasks = []
    to_fetch = []
    for _, row in merged.iterrows():
        mid = int(row["movieId"])
        mid_str = str(mid)
        # Skip if already cached with valid poster
        if mid_str in cache and cache[mid_str].get("poster_path"):
            continue
        clean_title, year = clean_title_and_year(str(row["title"]))
        to_fetch.append({
            "movieId": mid,
            "tmdbId": row.get("tmdbId"),
            "raw_title": str(row["title"]),
            "title": clean_title,
            "year": year
        })

    print(f"[INFO] {len(merged) - len(to_fetch)} already cached. Fetching {len(to_fetch)} missing movies with {max_workers} threads...")

    if not to_fetch:
        print("[SUCCESS] All top movies are already cached in data/posters.json!")
        return

    success_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {}
        for item in to_fetch:
            fut = executor.submit(fetch_movie_from_tmdb, item["tmdbId"], item["title"], item["year"])
            future_map[fut] = item
            time.sleep(0.04)  # Small spacing to avoid burst rate limits

        for future in as_completed(future_map):
            item = future_map[future]
            mid_str = str(item["movieId"])
            try:
                res = future.result()
                if res and res.get("poster_path"):
                    poster_path = res["poster_path"]
                    backdrop_path = res.get("backdrop_path")
                    cache[mid_str] = {
                        "movieId": item["movieId"],
                        "tmdbId": res.get("id", item.get("tmdbId")),
                        "title": item["title"],
                        "poster_path": poster_path,
                        "poster_url": f"{IMG_W500}{poster_path}",
                        "poster_large_url": f"{IMG_W780}{poster_path}",
                        "backdrop_path": backdrop_path,
                        "backdrop_url": f"{IMG_W780}{backdrop_path}" if backdrop_path else None,
                        "overview": res.get("overview", ""),
                        "release_year": item["year"] or (res.get("release_date", "")[:4] if res.get("release_date") else None),
                        "original_language": res.get("original_language", "en")
                    }
                    success_count += 1
                    print(f"  [+] ({success_count}/{len(to_fetch)}) {item['title']} -> {poster_path}")
                else:
                    print(f"  [-] No poster found for: {item['title']}")
            except Exception as e:
                print(f"  [!] Error fetching {item['title']}: {e}")

    # Write cache to data/posters.json
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"\n[SUCCESS] Saved {len(cache)} movie posters to {CACHE_FILE}")


if __name__ == "__main__":
    fetch_all_posters(top_n=300, max_workers=10)
