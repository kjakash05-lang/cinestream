"""
ml/resolve_trailers.py
Resolves official, working YouTube trailers for featured CineStream movies.

Fallback order per movie & language:
1. Manual ID in data/featured.json trailers[lang] (verified against YouTube oEmbed)
2. TMDB GET /movie/{tmdb_id}/videos?language=en-US, then with include_video_language=en,hi,kn,ta,te,ml,null
   (filters: site="YouTube", type="Trailer" then "Teaser", prefer official=True, newest published_at)
3. YouTube Data API v3 search (if YOUTUBE_API_KEY exists in .env):
   query "{title} {year} official trailer", videoEmbeddable=true, type=video
4. Caches results in data/trailers_resolved.json with "source" and "verified": false flags.
5. Prints a comprehensive terminal report of all resolved trailers.
"""

import os
import sys
import json
import socket
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

socket.setdefaulttimeout(4)

# Ensure stdout handles UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
FEATURED_PATH = os.path.join(DATA_DIR, "featured.json")
FEATURED_LANG_PATH = os.path.join(DATA_DIR, "featured_by_language.json")
RESOLVED_PATH = os.path.join(DATA_DIR, "trailers_resolved.json")

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "8265bd1679663a7ea12ac168da84d2e8")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

LANGUAGES = ["hi", "kn", "ta", "te", "ml", "en"]
LANG_NAMES = {
    "hi": "Hindi",
    "kn": "Kannada",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "en": "English"
}

def verify_youtube_video(video_id: str) -> bool:
    """Verifies if a YouTube video ID actually exists and is viewable via oEmbed."""
    if not video_id or len(video_id) < 5 or video_id.startswith("_"):
        return False
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False

def fetch_tmdb_videos(tmdb_id: int):
    """Fetches video records from TMDB with both language-specific and inclusive parameters."""
    if not TMDB_API_KEY or not tmdb_id:
        return []
    
    videos = []
    seen_keys = set()
    
    urls = [
        f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos?api_key={TMDB_API_KEY}&language=en-US",
        f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos?api_key={TMDB_API_KEY}&include_video_language=en,hi,kn,ta,te,ml,null",
        f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos?api_key={TMDB_API_KEY}"
    ]
    
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for v in data.get("results", []):
                    key = v.get("key")
                    if key and key not in seen_keys and v.get("site") == "YouTube":
                        seen_keys.add(key)
                        videos.append(v)
        except Exception:
            continue
            
    return videos

def filter_best_tmdb_video(videos, lang_code=None):
    candidates = []
    for v in videos:
        if v.get("site") != "YouTube":
            continue
        v_lang = (v.get("iso_639_1") or "").lower()
        v_type = v.get("type", "")
        v_name = (v.get("name") or "").lower()
        
        if lang_code:
            lang_match = (v_lang == lang_code)
            lang_name = LANG_NAMES.get(lang_code, "").lower()
            if not lang_match and lang_name and lang_name in v_name:
                lang_match = True
            if not lang_match:
                continue
        
        if v_type not in ["Trailer", "Teaser", "Clip"]:
            continue
            
        score = 0
        if v_type == "Trailer":
            score += 100
        elif v_type == "Teaser":
            score += 50
            
        if v.get("official") is True:
            score += 30
            
        pub = v.get("published_at", "")
        candidates.append((score, pub, v))
        
    if not candidates:
        return None
        
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]

def search_youtube_api(title: str, year: int, lang_name: str = ""):
    if not YOUTUBE_API_KEY:
        return None
        
    query = f"{title} {year} official trailer {lang_name}".strip()
    encoded = urllib.parse.quote(query)
    url = (
        f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={encoded}"
        f"&type=video&videoEmbeddable=true&maxResults=3&key={YOUTUBE_API_KEY}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for item in data.get("items", []):
                vid = item.get("id", {}).get("videoId")
                item_title = item.get("snippet", {}).get("title", "").lower()
                clean_title = title.lower().split(":")[0].strip()
                if vid and clean_title in item_title:
                    return {
                        "key": vid,
                        "name": item.get("snippet", {}).get("title"),
                        "source": "youtube_api"
                    }
    except Exception:
        pass
    return None

def resolve_movie_trailers(movie: dict):
    slug = movie.get("slug", "")
    title = movie.get("title", "")
    year = movie.get("year", 2024)
    tmdb_id = movie.get("tmdb_id")
    default_lang = movie.get("default_lang", "hi")
    
    manual_trailers = movie.get("trailers", {})
    resolved = {
        "slug": slug,
        "title": title,
        "year": year,
        "tmdb_id": tmdb_id,
        "default_lang": default_lang,
        "trailers": {},
        "fallback_list": [],
        "sources": {},
        "verified": False,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    tmdb_videos = fetch_tmdb_videos(tmdb_id) if tmdb_id else []
    
    for l in LANGUAGES:
        lang_name = LANG_NAMES.get(l, "")
        chosen_id = None
        source = None
        
        # 1. Manual ID from featured.json
        manual_id = manual_trailers.get(l)
        if manual_id and str(manual_id).strip() and not str(manual_id).startswith("_"):
            manual_id = str(manual_id).strip()
            if verify_youtube_video(manual_id):
                chosen_id = manual_id
                source = "manual_featured_json"
        
        # 2. TMDB video match
        if not chosen_id and tmdb_videos:
            best_tmdb = filter_best_tmdb_video(tmdb_videos, lang_code=l)
            if best_tmdb and best_tmdb.get("key"):
                t_key = best_tmdb["key"]
                if verify_youtube_video(t_key):
                    chosen_id = t_key
                    source = f"tmdb_api_{best_tmdb.get('type', 'trailer').lower()}"
                    
        # 3. YouTube API search
        if not chosen_id:
            yt_res = search_youtube_api(title, year, lang_name)
            if yt_res and yt_res.get("key"):
                chosen_id = yt_res["key"]
                source = "youtube_data_api"
                
        if chosen_id:
            resolved["trailers"][l] = chosen_id
            resolved["sources"][l] = source
            if chosen_id not in resolved["fallback_list"]:
                resolved["fallback_list"].append(chosen_id)
                
    if not resolved["fallback_list"] and tmdb_videos:
        general_best = filter_best_tmdb_video(tmdb_videos, lang_code=None)
        if general_best and general_best.get("key"):
            t_key = general_best["key"]
            if verify_youtube_video(t_key):
                resolved["trailers"][default_lang] = t_key
                resolved["sources"][default_lang] = "tmdb_api_general"
                resolved["fallback_list"].append(t_key)
                
    return resolved

def resolve_all():
    print("=" * 70, flush=True)
    print(" CINESTREAM TRAILER RESOLVER (TMDB + Manual + YouTube Fallback)", flush=True)
    print("=" * 70, flush=True)
    
    featured_movies = []
    if os.path.exists(FEATURED_PATH):
        with open(FEATURED_PATH, "r", encoding="utf-8") as f:
            featured_movies = json.load(f)
            
    extra_movies = []
    if os.path.exists(FEATURED_LANG_PATH):
        with open(FEATURED_LANG_PATH, "r", encoding="utf-8") as f:
            by_lang = json.load(f)
            for l, mov_list in by_lang.items():
                for m in mov_list:
                    if not any(fm.get("slug") == m.get("slug") for fm in featured_movies):
                        extra_movies.append(m)
                        
    # Process the 4 main hero movies first, then remaining
    all_targets = featured_movies + extra_movies
    print(f"Resolving trailers concurrently for {len(all_targets)} movies...\n", flush=True)
    
    resolved_db = {}
    if os.path.exists(RESOLVED_PATH):
        try:
            with open(RESOLVED_PATH, "r", encoding="utf-8") as f:
                resolved_db = json.load(f)
        except Exception:
            resolved_db = {}
            
    report_rows = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_movie = {executor.submit(resolve_movie_trailers, m): m for m in all_targets}
        for future in as_completed(future_to_movie):
            m = future_to_movie[future]
            slug = m.get("slug")
            try:
                res = future.result()
                resolved_db[slug] = res
                langs_found = list(res["trailers"].keys())
                status = "OK" if langs_found else "NO TRAILER"
                report_rows.append({
                    "title": m.get("title", slug),
                    "slug": slug,
                    "status": status,
                    "count": len(langs_found),
                    "langs": ", ".join(langs_found) if langs_found else "None",
                    "primary": res["trailers"].get(res["default_lang"]) or (res["fallback_list"][0] if res["fallback_list"] else "NONE")
                })
                print(f"✓ [{status}] {m.get('title')}: {len(langs_found)} audio langs ({', '.join(langs_found) if langs_found else 'None'})", flush=True)
            except Exception as e:
                print(f"✗ Failed {slug}: {e}", flush=True)
                
    # Save complete DB
    with open(RESOLVED_PATH, "w", encoding="utf-8") as f:
        json.dump(resolved_db, f, indent=2, ensure_ascii=False)
        
    print("\n" + "=" * 70, flush=True)
    print(" TRAILER RESOLUTION REPORT SUMMARY", flush=True)
    print("=" * 70, flush=True)
    print(f"{'Movie Title':<32} | {'Status':<10} | {'Langs':<18} | {'Primary Trailer'}", flush=True)
    print("-" * 70, flush=True)
    report_rows.sort(key=lambda r: (0 if r["status"] == "OK" else 1, r["title"]))
    for r in report_rows:
        print(f"{r['title'][:30]:<32} | {r['status']:<10} | {r['langs']:<18} | {r['primary']}", flush=True)
    print("=" * 70, flush=True)
    print(f"Results saved to: {RESOLVED_PATH}\n", flush=True)
    return resolved_db

if __name__ == "__main__":
    resolve_all()
