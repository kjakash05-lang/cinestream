"""
ml/migrate_english.py
Rewrites:
- data/movies_all.csv
- data/anime.csv (if exists)
- data/cartoons.csv (if exists)
- data/featured.json
- data/featured_by_language.json
- data/cache.json
with strict English Latin-only display titles and language_name columns.
Preserves existing poster and backdrop URLs without re-downloading.
Prints a review report of all titles whose source was "transliterated".
"""
import os
import sys
import json
import re
import pandas as pd
from dotenv import load_dotenv

# Safe UTF-8 console output for Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
sys.path.insert(0, ROOT_DIR)

from ml.english_titles import (
    resolve_english_title,
    resolve_english_overview,
    get_language_name,
    NON_LATIN_RE,
    is_valid_latin_title
)

def migrate_movies_all():
    csv_path = os.path.join(DATA_DIR, "movies_all.csv")
    if not os.path.exists(csv_path):
        print("movies_all.csv not found at", csv_path)
        return []

    print(f"\n--- Migrating {csv_path} ---")
    df = pd.read_csv(csv_path, encoding="utf-8")
    transliterated_review = []

    # Ensure required columns
    new_title_ens = []
    new_overviews = []
    language_names = []

    for idx, row in df.iterrows():
        tmdb_id = row.get("tmdb_id")
        t_nat = str(row.get("title_native") or "")
        t_en = str(row.get("title_en") or "")
        lang = str(row.get("lang") or "en").lower().strip()
        ov = str(row.get("overview") or "")

        resolved_title, source = resolve_english_title(tmdb_id, t_nat, t_en, lang)
        # Ensure it contains NO non-latin script
        if NON_LATIN_RE.search(resolved_title):
            resolved_title = NON_LATIN_RE.sub("", resolved_title).strip()
            if not resolved_title:
                resolved_title = "Untitled Film"

        resolved_ov = resolve_english_overview(tmdb_id, ov, lang)
        if NON_LATIN_RE.search(resolved_ov):
            resolved_ov = NON_LATIN_RE.sub("", resolved_ov).strip()
            if not resolved_ov:
                resolved_ov = "No English synopsis available yet."

        new_title_ens.append(resolved_title)
        new_overviews.append(resolved_ov)
        language_names.append(get_language_name(lang))

        if "transliterated" in source:
            transliterated_review.append({
                "tmdb_id": tmdb_id,
                "native": t_nat,
                "transliterated": resolved_title,
                "lang": lang,
                "source": source
            })

    df["title_en"] = new_title_ens
    # Ensure title column is also set to English if present
    df["title"] = new_title_ens
    df["overview"] = new_overviews
    df["language_name"] = language_names

    df.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"Successfully migrated {len(df)} rows in {csv_path}")
    return transliterated_review


def migrate_csv_file(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []

    print(f"\n--- Migrating {path} ---")
    df = pd.read_csv(path, encoding="utf-8")
    transliterated_review = []

    new_titles = []
    new_overviews = []
    language_names = []

    for idx, row in df.iterrows():
        tmdb_id = row.get("tmdb_id") or row.get("id") or row.get("movieId")
        t_nat = str(row.get("title_native") or row.get("name_native") or "")
        t_en = str(row.get("title_en") or row.get("title") or row.get("name") or "")
        lang = str(row.get("lang") or row.get("original_language") or "en").lower().strip()
        ov = str(row.get("overview") or "")

        resolved_title, source = resolve_english_title(tmdb_id, t_nat, t_en, lang)
        if NON_LATIN_RE.search(resolved_title):
            resolved_title = NON_LATIN_RE.sub("", resolved_title).strip() or "Untitled Film"

        resolved_ov = resolve_english_overview(tmdb_id, ov, lang)
        if NON_LATIN_RE.search(resolved_ov):
            resolved_ov = NON_LATIN_RE.sub("", resolved_ov).strip() or "No English synopsis available yet."

        new_titles.append(resolved_title)
        new_overviews.append(resolved_ov)
        language_names.append(get_language_name(lang))

        if "transliterated" in source:
            transliterated_review.append({
                "tmdb_id": tmdb_id,
                "native": t_nat,
                "transliterated": resolved_title,
                "lang": lang,
                "source": source
            })

    if "title_en" in df.columns:
        df["title_en"] = new_titles
    df["title"] = new_titles
    if "overview" in df.columns:
        df["overview"] = new_overviews
    df["language_name"] = language_names

    df.to_csv(path, index=False, encoding="utf-8")
    print(f"Successfully migrated {len(df)} rows in {path}")
    return transliterated_review


def migrate_featured_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []

    print(f"\n--- Migrating {path} ---")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    transliterated_review = []

    def clean_movie(m):
        tmdb_id = m.get("tmdb_id")
        t_nat = str(m.get("title_native") or "")
        t_en = str(m.get("title_en") or m.get("title") or "")
        lang = str(m.get("default_lang") or m.get("lang") or m.get("original_lang") or "en").lower()
        ov = str(m.get("overview") or "")

        resolved_title, source = resolve_english_title(tmdb_id, t_nat, t_en, lang)
        if NON_LATIN_RE.search(resolved_title):
            resolved_title = NON_LATIN_RE.sub("", resolved_title).strip() or "Untitled Film"

        resolved_ov = resolve_english_overview(tmdb_id, ov, lang)
        if NON_LATIN_RE.search(resolved_ov):
            resolved_ov = NON_LATIN_RE.sub("", resolved_ov).strip() or "No English synopsis available yet."

        m["title_en"] = resolved_title
        m["title"] = resolved_title
        m["overview"] = resolved_ov
        m["language_name"] = get_language_name(lang)

        if "transliterated" in source:
            transliterated_review.append({
                "tmdb_id": tmdb_id,
                "native": t_nat,
                "transliterated": resolved_title,
                "lang": lang,
                "source": source
            })

    if isinstance(data, list):
        for m in data:
            clean_movie(m)
    elif isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list):
                for m in v:
                    clean_movie(m)
            elif isinstance(v, dict):
                clean_movie(v)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Successfully migrated {path}")
    return transliterated_review


def migrate_cache_json():
    path = os.path.join(DATA_DIR, "cache.json")
    if not os.path.exists(path):
        return

    print(f"\n--- Migrating {path} ---")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, item in data.items():
            if isinstance(item, dict):
                tmdb_id = item.get("tmdb_id") or item.get("id")
                t_nat = str(item.get("title_native") or "")
                t_en = str(item.get("title_en") or item.get("title") or "")
                lang = str(item.get("lang") or "en").lower()
                resolved_title, _ = resolve_english_title(tmdb_id, t_nat, t_en, lang)
                if NON_LATIN_RE.search(resolved_title):
                    resolved_title = NON_LATIN_RE.sub("", resolved_title).strip() or "Untitled Film"
                item["title_en"] = resolved_title
                item["title"] = resolved_title
                item["language_name"] = get_language_name(lang)
                ov = str(item.get("overview") or "")
                if NON_LATIN_RE.search(ov):
                    item["overview"] = NON_LATIN_RE.sub("", ov).strip() or "No English synopsis available yet."
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Successfully migrated {path}")
    except Exception as e:
        print(f"Warning: could not migrate cache.json: {e}")


def main():
    print("============================================================")
    print("STARTING CINESTREAM STRICT ENGLISH DATA MIGRATION")
    print("============================================================")

    all_transliterated = []
    all_transliterated.extend(migrate_movies_all())
    all_transliterated.extend(migrate_csv_file("anime.csv"))
    all_transliterated.extend(migrate_csv_file("cartoons.csv"))
    all_transliterated.extend(migrate_featured_json("featured.json"))
    all_transliterated.extend(migrate_featured_json("featured_by_language.json"))
    migrate_cache_json()

    # Print Review Report
    print("\n" + "=" * 60)
    print("TRANSLITERATED TITLES REVIEW REPORT")
    print("=" * 60)
    if not all_transliterated:
        print("No titles required romanisation fallback (all resolved from TMDB / Latin titles / overrides).")
    else:
        print(f"Total titles flagged title_source = 'transliterated': {len(all_transliterated)}")
        print(f"{'TMDB ID':<10} | {'Lang':<5} | {'Native Title':<25} | {'Transliterated Title':<30}")
        print("-" * 80)
        seen = set()
        for item in all_transliterated:
            tid = str(item.get("tmdb_id"))
            if tid in seen:
                continue
            seen.add(tid)
            print(f"{tid:<10} | {item.get('lang'):<5} | {item.get('native', '')[:25]:<25} | {item.get('transliterated', '')[:30]:<30}")

    print("\nMigration completed successfully.")

if __name__ == "__main__":
    main()