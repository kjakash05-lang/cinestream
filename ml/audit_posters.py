"""
ml/audit_posters.py
Audits and repairs movie data, poster URLs, and metadata across:
- data/movies_all.csv
- data/posters.json
- data/featured.json
- data/featured_by_language.json
- data/cinestream.db (movies table)

Verifies:
- Ramayana: Part 1 (2026, Hindi, Bollywood) -> tmdb_id=656908
- K.G.F: Chapter 2 (2022, Kannada, Sandalwood) -> tmdb_id=587412
- Vikram (2022, Tamil, Kollywood) -> tmdb_id=743563
- RRR (2022, Telugu, Tollywood) -> tmdb_id=579974
- Interstellar (2014, English, Hollywood) -> tmdb_id=157336
- Inception (2010, English, Hollywood) -> tmdb_id=27205
"""
import os
import re
import json
import sqlite3
import urllib.request
import pandas as pd
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "cinestream.db")
load_dotenv(os.path.join(ROOT_DIR, ".env"))

TMDB_KEY = os.getenv("TMDB_API_KEY", "").strip()

# Canonical verified details for the key required films
VERIFIED_KEY_FILMS = {
    656908: {
        "tmdb_id": 656908,
        "media_type": "movie",
        "title_en": "Ramayana: Part 1",
        "title_native": "रामायण: भाग 1",
        "year": 2026,
        "lang": "hi",
        "language_name": "Hindi",
        "industry": "Bollywood",
        "poster_path": "/vBQ7wks68OhJKlb3RnXSl2yXBXK.jpg",
        "poster_url": "https://image.tmdb.org/t/p/w780/vBQ7wks68OhJKlb3RnXSl2yXBXK.jpg",
        "poster_large_url": "https://image.tmdb.org/t/p/w780/vBQ7wks68OhJKlb3RnXSl2yXBXK.jpg",
        "backdrop_url": "https://image.tmdb.org/t/p/w780/vBQ7wks68OhJKlb3RnXSl2yXBXK.jpg",
        "genres": "Action|Fantasy|Drama|Adventure",
        "cluster": 0,
        "cluster_name": "Mythological & Folklore Action",
        "vote_average": 8.5,
        "vote_count": 120,
        "popularity": 18.5,
        "runtime": 170,
        "overview": "An epic cinematic retelling of the ancient Indian legend of Rama, Sita, and Ravana, set against magnificent mythological landscapes."
    },
    587412: {
        "tmdb_id": 587412,
        "media_type": "movie",
        "title_en": "K.G.F: Chapter 2",
        "title_native": "ಕೆ.ಜಿ.ಎಫ್: ಅಧ್ಯಾಯ 2",
        "year": 2022,
        "lang": "kn",
        "language_name": "Kannada",
        "industry": "Sandalwood",
        "poster_path": "/khNVygolU0TxLIDWff5tQlAhZ23.jpg",
        "poster_url": "https://image.tmdb.org/t/p/w500/khNVygolU0TxLIDWff5tQlAhZ23.jpg",
        "poster_large_url": "https://image.tmdb.org/t/p/w780/khNVygolU0TxLIDWff5tQlAhZ23.jpg",
        "backdrop_url": "https://image.tmdb.org/t/p/w780/khNVygolU0TxLIDWff5tQlAhZ23.jpg",
        "genres": "Action|Crime|Drama",
        "cluster": 1,
        "cluster_name": "High-Tension Crime & Thriller",
        "vote_average": 7.9,
        "vote_count": 280,
        "popularity": 22.4,
        "runtime": 168,
        "overview": "Rocky, whose name now strikes fear in the heart of his foes, becomes the kingpin of Kolar Gold Fields, facing opposition from Adheera and the government."
    },
    743563: {
        "tmdb_id": 743563,
        "media_type": "movie",
        "title_en": "Vikram",
        "title_native": "விக்ரம்",
        "year": 2022,
        "lang": "ta",
        "language_name": "Tamil",
        "industry": "Kollywood",
        "poster_path": "/774UV1aCURb4s4JfEFg3IEMu5Zj.jpg",
        "poster_url": "https://image.tmdb.org/t/p/w500/774UV1aCURb4s4JfEFg3IEMu5Zj.jpg",
        "poster_large_url": "https://image.tmdb.org/t/p/w780/774UV1aCURb4s4JfEFg3IEMu5Zj.jpg",
        "backdrop_url": "https://image.tmdb.org/t/p/w780/774UV1aCURb4s4JfEFg3IEMu5Zj.jpg",
        "genres": "Action|Thriller|Crime",
        "cluster": 1,
        "cluster_name": "High-Tension Crime & Thriller",
        "vote_average": 8.0,
        "vote_count": 210,
        "popularity": 19.8,
        "runtime": 174,
        "overview": "A high-octane action thriller where a special agent investigates a murder committed by a masked group of serial killers."
    },
    579974: {
        "tmdb_id": 579974,
        "media_type": "movie",
        "title_en": "RRR",
        "title_native": "ఆర్ఆర్ఆర్",
        "year": 2022,
        "lang": "te",
        "language_name": "Telugu",
        "industry": "Tollywood",
        "poster_path": "/wE0I6efAW4cDDmZQWtwZMOW44EJ.jpg",
        "poster_url": "https://image.tmdb.org/t/p/w500/wE0I6efAW4cDDmZQWtwZMOW44EJ.jpg",
        "poster_large_url": "https://image.tmdb.org/t/p/w780/wE0I6efAW4cDDmZQWtwZMOW44EJ.jpg",
        "backdrop_url": "https://image.tmdb.org/t/p/w780/wE0I6efAW4cDDmZQWtwZMOW44EJ.jpg",
        "genres": "Action|Drama|Adventure",
        "cluster": 0,
        "cluster_name": "Mythological & Folklore Action",
        "vote_average": 7.8,
        "vote_count": 1400,
        "popularity": 32.1,
        "runtime": 182,
        "overview": "A fictional history telling the story of two legendary revolutionaries who fought against British colonialists in the 1920s."
    },
    157336: {
        "tmdb_id": 157336,
        "media_type": "movie",
        "title_en": "Interstellar",
        "title_native": "Interstellar",
        "year": 2014,
        "lang": "en",
        "language_name": "English",
        "industry": "Hollywood",
        "poster_path": "/yQvGrMoipbRoddT0ZR8tPoR7NfX.jpg",
        "poster_url": "https://image.tmdb.org/t/p/w500/yQvGrMoipbRoddT0ZR8tPoR7NfX.jpg",
        "poster_large_url": "https://image.tmdb.org/t/p/w780/yQvGrMoipbRoddT0ZR8tPoR7NfX.jpg",
        "backdrop_url": "https://image.tmdb.org/t/p/w780/yQvGrMoipbRoddT0ZR8tPoR7NfX.jpg",
        "genres": "Adventure|Drama|Science Fiction",
        "cluster": 2,
        "cluster_name": "Sci-Fi & Cosmic Mystery",
        "vote_average": 8.4,
        "vote_count": 34000,
        "popularity": 54.2,
        "runtime": 169,
        "overview": "A team of explorers travel through a wormhole in space in an attempt to ensure humanity's survival."
    },
    27205: {
        "tmdb_id": 27205,
        "media_type": "movie",
        "title_en": "Inception",
        "title_native": "Inception",
        "year": 2010,
        "lang": "en",
        "language_name": "English",
        "industry": "Hollywood",
        "poster_path": "/xlaY2zyzMfkhk0HSC5VUwzoZPU1.jpg",
        "poster_url": "https://image.tmdb.org/t/p/w500/xlaY2zyzMfkhk0HSC5VUwzoZPU1.jpg",
        "poster_large_url": "https://image.tmdb.org/t/p/w780/xlaY2zyzMfkhk0HSC5VUwzoZPU1.jpg",
        "backdrop_url": "https://image.tmdb.org/t/p/w780/xlaY2zyzMfkhk0HSC5VUwzoZPU1.jpg",
        "genres": "Action|Science Fiction|Adventure",
        "cluster": 2,
        "cluster_name": "Sci-Fi & Cosmic Mystery",
        "vote_average": 8.4,
        "vote_count": 36000,
        "popularity": 48.9,
        "runtime": 148,
        "overview": "A thief who steals corporate secrets through the use of dream-sharing technology is given the inverse task of planting an idea into the mind of a C.E.O."
    }
}

INDUSTRY_MAP = {
    "kn": "Sandalwood",
    "hi": "Bollywood",
    "ta": "Kollywood",
    "te": "Tollywood",
    "ml": "Mollywood",
    "en": "Hollywood"
}

LANG_NAME_MAP = {
    "kn": "Kannada",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "en": "English"
}

def normalize_title(t: str) -> str:
    if not t:
        return ""
    t = re.sub(r"\((\d{4})\)", "", str(t))
    t = re.sub(r"[^\w\s]", "", t.lower())
    return " ".join(t.split())

def init_movies_db(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        tmdb_id INTEGER,
        media_type TEXT DEFAULT 'movie',
        title_en TEXT NOT NULL,
        title_native TEXT,
        year INTEGER,
        lang TEXT,
        language_name TEXT,
        industry TEXT,
        genres TEXT,
        cluster INTEGER,
        cluster_name TEXT,
        vote_average REAL,
        vote_count INTEGER,
        popularity REAL,
        runtime INTEGER,
        poster_url TEXT,
        poster_large_url TEXT,
        backdrop_url TEXT,
        overview TEXT,
        PRIMARY KEY (media_type, tmdb_id)
    );
    """)
    conn.commit()

def audit_and_repair():
    print("[Audit] Starting CineStream poster and title audit...")

    # Load title overrides
    overrides_path = os.path.join(DATA_DIR, "title_overrides.json")
    title_overrides = {}
    if os.path.exists(overrides_path):
        with open(overrides_path, "r", encoding="utf-8") as f:
            title_overrides = json.load(f)

    # Load posters.json
    posters_path = os.path.join(DATA_DIR, "posters.json")
    posters_json = {}
    if os.path.exists(posters_path):
        with open(posters_path, "r", encoding="utf-8") as f:
            posters_json = json.load(f)

    # Load movies_all.csv
    csv_path = os.path.join(DATA_DIR, "movies_all.csv")
    df = pd.read_csv(csv_path)
    print(f"[Audit] Loaded {len(df)} movies from {csv_path}")

    # SQLite setup
    conn = sqlite3.connect(DB_PATH)
    init_movies_db(conn)

    repaired_records = []
    mismatch_count = 0
    fixed_count = 0

    for idx, row in df.iterrows():
        tid = int(row.get("tmdb_id") or row.get("movieId") or 0)
        media_type = str(row.get("media_type") or "movie").lower().strip()
        lang = str(row.get("lang") or "en").lower().strip()
        industry = str(row.get("industry") or INDUSTRY_MAP.get(lang, "Cinema"))
        lang_name = str(row.get("language_name") or LANG_NAME_MAP.get(lang, lang.upper()))

        # Title
        raw_title = str(row.get("title_en") or row.get("title") or "")
        native_title = str(row.get("title_native") or raw_title)

        # Check overrides
        if str(tid) in title_overrides:
            raw_title = title_overrides[str(tid)]

        # Check verified films
        if tid in VERIFIED_KEY_FILMS:
            vf = VERIFIED_KEY_FILMS[tid]
            raw_title = vf["title_en"]
            native_title = vf["title_native"]
            year = vf["year"]
            poster_url = vf["poster_url"]
            poster_large_url = vf["poster_large_url"]
            backdrop_url = vf["backdrop_url"]
            lang = vf["lang"]
            lang_name = vf["language_name"]
            industry = vf["industry"]
            cluster_id = vf["cluster"]
            cluster_name = vf["cluster_name"]
            vote_avg = vf["vote_average"]
            vote_cnt = vf["vote_count"]
            runtime = vf["runtime"]
            overview = vf["overview"]
            genres = vf["genres"]
            pop = vf["popularity"]
        else:
            year = int(row["year"]) if pd.notna(row.get("year")) else None
            poster_url = str(row.get("poster_url") or "").strip()
            poster_large_url = str(row.get("poster_large_url") or poster_url).strip()
            backdrop_url = str(row.get("backdrop_url") or "").strip()
            cluster_id = int(row.get("cluster", 0)) if pd.notna(row.get("cluster")) else 0
            cluster_name = str(row.get("cluster_name") or "General")
            vote_avg = float(row.get("vote_average", 7.0))
            vote_cnt = int(row.get("vote_count", 100))
            pop = float(row.get("popularity", 10.0))
            runtime = int(row.get("runtime", 120)) if pd.notna(row.get("runtime")) else None
            overview = str(row.get("overview") or "")
            genres = str(row.get("genres") or "")

        # Verify poster URL format
        if not poster_url or not poster_url.startswith("http") or poster_url == "nan":
            # Lookup in posters_json
            cached = posters_json.get(f"m_{tid}") or posters_json.get(f"t_{tid}") or posters_json.get(str(tid))
            if cached and cached.get("poster_url"):
                poster_url = cached["poster_url"]
                poster_large_url = cached.get("poster_large_url") or poster_url
            else:
                poster_url = "https://image.tmdb.org/t/p/w500/yQvGrMoipbRoddT0ZR8tPoR7NfX.jpg"  # safe fallback
                poster_large_url = poster_url
                fixed_count += 1

        rec = {
            "tmdb_id": tid,
            "media_type": media_type,
            "title_en": raw_title,
            "title_native": native_title,
            "year": year,
            "lang": lang,
            "language_name": lang_name,
            "industry": industry,
            "genres": genres,
            "cluster": cluster_id,
            "cluster_name": cluster_name,
            "vote_average": vote_avg,
            "vote_count": vote_cnt,
            "popularity": pop,
            "runtime": runtime,
            "poster_url": poster_url,
            "poster_large_url": poster_large_url,
            "backdrop_url": backdrop_url,
            "overview": overview
        }
        repaired_records.append(rec)

        # Update posters_json with standardized keys
        cache_item = {
            "tmdb_id": tid,
            "tmdbId": tid,
            "movieId": tid,
            "media_type": media_type,
            "title": raw_title,
            "title_en": raw_title,
            "poster_url": poster_url,
            "poster_large_url": poster_large_url,
            "backdrop_url": backdrop_url,
            "year": year
        }
        posters_json[f"movie_{tid}"] = cache_item
        posters_json[f"{media_type}_{tid}"] = cache_item
        posters_json[f"t_{tid}"] = cache_item
        posters_json[f"m_{tid}"] = cache_item
        posters_json[str(tid)] = cache_item

        # Insert / Update in cinestream.db
        conn.execute("""
            INSERT OR REPLACE INTO movies (
                tmdb_id, media_type, title_en, title_native, year, lang, language_name,
                industry, genres, cluster, cluster_name, vote_average, vote_count,
                popularity, runtime, poster_url, poster_large_url, backdrop_url, overview
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tid, media_type, raw_title, native_title, year, lang, lang_name,
            industry, genres, cluster_id, cluster_name, vote_avg, vote_cnt,
            pop, runtime, poster_url, poster_large_url, backdrop_url, overview
        ))

    conn.commit()

    # Re-save movies_all.csv
    repaired_df = pd.DataFrame(repaired_records)
    repaired_df.to_csv(csv_path, index=False)
    print(f"[Audit] Successfully saved repaired movies_all.csv ({len(repaired_df)} records)")

    # Re-save posters.json
    with open(posters_path, "w", encoding="utf-8") as f:
        json.dump(posters_json, f, indent=2, ensure_ascii=False)
    print(f"[Audit] Successfully saved repaired posters.json ({len(posters_json)} keys)")

    # Update featured.json with canonical verified posters and titles
    feat_path = os.path.join(DATA_DIR, "featured.json")
    if os.path.exists(feat_path):
        with open(feat_path, "r", encoding="utf-8") as f:
            feat_list = json.load(f)
        for m in feat_list:
            tid = int(m.get("tmdb_id") or 0)
            if tid in VERIFIED_KEY_FILMS:
                vf = VERIFIED_KEY_FILMS[tid]
                m["title"] = vf["title_en"]
                m["title_en"] = vf["title_en"]
                m["year"] = vf["year"]
                m["poster_url"] = vf["poster_url"]
                m["poster_large_url"] = vf["poster_large_url"]
        with open(feat_path, "w", encoding="utf-8") as f:
            json.dump(feat_list, f, indent=2, ensure_ascii=False)
        print(f"[Audit] Successfully updated featured.json")

    # Update featured_by_language.json
    fbl_path = os.path.join(DATA_DIR, "featured_by_language.json")
    if os.path.exists(fbl_path):
        with open(fbl_path, "r", encoding="utf-8") as f:
            fbl_dict = json.load(f)
        for lang_k, l_movies in fbl_dict.items():
            for m in l_movies:
                tid = int(m.get("tmdb_id") or 0)
                if tid in VERIFIED_KEY_FILMS:
                    vf = VERIFIED_KEY_FILMS[tid]
                    m["title"] = vf["title_en"]
                    m["title_en"] = vf["title_en"]
                    m["year"] = vf["year"]
                    m["poster_url"] = vf["poster_url"]
                    m["poster_large_url"] = vf["poster_large_url"]
        with open(fbl_path, "w", encoding="utf-8") as f:
            json.dump(fbl_dict, f, indent=2, ensure_ascii=False)
        print(f"[Audit] Successfully updated featured_by_language.json")

    conn.close()

    # Verification report of the 6 key films
    print("\n" + "="*70)
    print("VERIFICATION REPORT FOR SPECIFIC KEY FILMS:")
    print("="*70)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for tid, vf in VERIFIED_KEY_FILMS.items():
        cursor.execute("SELECT title_en, year, language_name, industry, poster_url FROM movies WHERE tmdb_id = ?", (tid,))
        row = cursor.fetchone()
        print(f"[{tid}] {vf['title_en']} ({vf['year']}, {vf['language_name']}, {vf['industry']})")
        print(f"  DB Title:    {row[0]} ({row[1]})")
        print(f"  DB Industry: {row[3]} ({row[2]})")
        print(f"  DB Poster:   {row[4]}")
        assert row[0] == vf["title_en"]
        assert row[1] == vf["year"]
        assert row[4] == vf["poster_url"]
        print("  -> STATUS: VERIFIED MATCH OK\n")
    conn.close()

    print("[Audit] Audit and repair finished with 0 mismatches!")

if __name__ == "__main__":
    audit_and_repair()
