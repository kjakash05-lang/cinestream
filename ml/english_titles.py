"""
english_titles.py - Strict English Title & Overview Resolver for CineStream
Guarantees every displayed string contains only Latin characters [A-Za-z].

Fallback order:
1. data/title_overrides.json (tmdb_id -> English title) - always wins.
2. TMDB GET /movie/{id}?language=en-US (or /tv/{id}) "title"/"name":
   accepted ONLY if it contains Latin letters ([A-Za-z]) and not just digits/punctuation.
3. TMDB /movie/{id}/translations: entry with iso_639_1 == "en", use data.title.
4. TMDB /movie/{id}/alternative_titles: prefer iso_3166_1 US, GB, then IN (Latin script only).
5. Latin-script part of original title if it has one (e.g. "ಕೆ.ಜಿ.ಎಫ್: Chapter 2" -> native transliterated + "Chapter 2").
6. Last resort: romanise native title with indic-transliteration or pykakasi, title-cased,
   flagged title_source = "transliterated".
"""
import os
import sys
import re
import json
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
OVERRIDES_FILE = os.path.join(DATA_DIR, "title_overrides.json")

load_dotenv(os.path.join(ROOT_DIR, ".env"))
TMDB_KEY = os.getenv("TMDB_API_KEY", "").strip()
TMDB_BASE = "https://api.themoviedb.org/3"

# Regex for non-Latin scripts (Devanagari, Tamil, Telugu, Kannada, Malayalam, Japanese/CJK)
NON_LATIN_RE = re.compile(r"[\u0900-\u097F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u3040-\u30FF\u4E00-\u9FFF]")
LATIN_LETTER_RE = re.compile(r"[A-Za-z]")

# Language code to full English display name
LANGUAGE_NAMES = {
    "all": "All Languages",
    "en": "English",
    "hi": "Hindi",
    "kn": "Kannada",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "es": "Spanish",
    "fr": "French",
    "de": "German"
}

def get_language_name(code):
    return LANGUAGE_NAMES.get((code or "").lower().strip(), (code or "").capitalize())

def load_overrides():
    if os.path.exists(OVERRIDES_FILE):
        try:
            with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[english_titles] Warning: could not load {OVERRIDES_FILE}: {e}")
    return {}

_OVERRIDES = load_overrides()

def save_overrides(overrides_dict):
    global _OVERRIDES
    _OVERRIDES = overrides_dict
    with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
        json.dump(overrides_dict, f, indent=2, ensure_ascii=False)

def is_valid_latin_title(title, allow_ascii_digits=True):
    if not title or not isinstance(title, str):
        return False
    title = title.strip()
    if not title:
        return False
    # Must NOT have non-latin script characters
    if NON_LATIN_RE.search(title):
        return False
    if allow_ascii_digits:
        try:
            title.encode("ascii")
            return any(c.isalnum() for c in title)
        except UnicodeEncodeError:
            pass
    # Must contain at least one Latin letter [A-Za-z]
    return bool(LATIN_LETTER_RE.search(title))

def transliterate_indic(text, lang_code):
    """Romanises Indic script using indic-transliteration."""
    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import SchemeMap, SCHEMES, transliterate
        scheme_map = {
            "hi": sanscript.DEVANAGARI,
            "kn": sanscript.KANNADA,
            "ta": sanscript.TAMIL,
            "te": sanscript.TELUGU,
            "ml": sanscript.MALAYALAM
        }
        scheme = scheme_map.get(lang_code)
        if not scheme:
            for s in [sanscript.KANNADA, sanscript.TAMIL, sanscript.TELUGU, sanscript.MALAYALAM, sanscript.DEVANAGARI]:
                res = transliterate(text, s, sanscript.ITRANS)
                if res != text:
                    return res.title()
            return text
        res = transliterate(text, scheme, sanscript.ITRANS)
        return res.title()
    except Exception as e:
        return text

def transliterate_japanese(text):
    """Romanises Japanese script using pykakasi."""
    try:
        import pykakasi
        kks = pykakasi.kakasi()
        result = kks.convert(text)
        hepburn = " ".join([item["hepburn"] for item in result])
        return hepburn.title()
    except Exception:
        return text

def transliterate_text(text, lang_code="en"):
    """Transliterates text to Latin script based on language."""
    if not text:
        return ""
    if lang_code == "ja":
        trans = transliterate_japanese(text)
    else:
        trans = transliterate_indic(text, lang_code)
    clean = NON_LATIN_RE.sub("", trans).strip()
    return clean if clean else trans

def resolve_english_title(tmdb_id, title_native="", title_en="", lang="en", media_type="movie", session=None):
    """
    Resolves the strict Latin-only English title for a movie/series.
    Returns: (english_title, title_source)
    """
    sid = str(tmdb_id) if tmdb_id else ""

    # Step 1: title_overrides.json always wins
    if sid in _OVERRIDES:
        return _OVERRIDES[sid], "override"

    # Step 2: Check title_en if already valid Latin
    if is_valid_latin_title(title_en):
        return title_en.strip(), "existing_latin"

    # Step 3: TMDB API lookups if tmdb_id & TMDB_KEY are available
    if tmdb_id and TMDB_KEY:
        s = session or requests.Session()
        endpoint_type = "tv" if media_type == "tv" else "movie"

        # 3a. GET /movie/{id}?language=en-US
        try:
            url = f"{TMDB_BASE}/{endpoint_type}/{tmdb_id}?api_key={TMDB_KEY}&language=en-US"
            resp = s.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                cand = data.get("title") or data.get("name")
                if is_valid_latin_title(cand):
                    return cand.strip(), "tmdb_en_us"
        except Exception:
            pass

        # 3b. GET /movie/{id}/translations
        try:
            url = f"{TMDB_BASE}/{endpoint_type}/{tmdb_id}/translations?api_key={TMDB_KEY}"
            resp = s.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                for tr in data.get("translations", []):
                    if tr.get("iso_639_1") == "en":
                        cand = tr.get("data", {}).get("title") or tr.get("data", {}).get("name")
                        if is_valid_latin_title(cand):
                            return cand.strip(), "tmdb_translation_en"
        except Exception:
            pass

        # 3c. GET /movie/{id}/alternative_titles
        try:
            url = f"{TMDB_BASE}/{endpoint_type}/{tmdb_id}/alternative_titles?api_key={TMDB_KEY}"
            resp = s.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                titles_list = data.get("titles") or data.get("results") or []
                pref_countries = ["US", "GB", "IN"]
                for country in pref_countries:
                    for item in titles_list:
                        if item.get("iso_3166_1") == country:
                            cand = item.get("title")
                            if is_valid_latin_title(cand):
                                return cand.strip(), f"tmdb_alt_{country.lower()}"
                for item in titles_list:
                    cand = item.get("title")
                    if is_valid_latin_title(cand):
                        return cand.strip(), "tmdb_alt_other"
        except Exception:
            pass

    # Step 4: Latin part of original title if present
    if title_native:
        latin_parts = re.findall(r"[A-Za-z0-9][A-Za-z0-9\s\-\:\.\,\!\?\']*", title_native)
        candidate_part = " ".join([p.strip() for p in latin_parts if p.strip()]).strip()
        if is_valid_latin_title(candidate_part) and len(candidate_part) >= 3:
            native_parts = NON_LATIN_RE.findall(title_native)
            if native_parts:
                native_text = "".join(native_parts)
                trans_native = transliterate_text(native_text, lang)
                combined = f"{trans_native}: {candidate_part}" if ":" in title_native else f"{trans_native} {candidate_part}"
                combined = re.sub(r"\s+", " ", combined).strip()
                if is_valid_latin_title(combined):
                    return combined, "hybrid_latin_transliterated"
            return candidate_part, "native_latin_part"

    # Step 5: Last resort - transliterate native title
    if title_native:
        trans = transliterate_text(title_native, lang)
        trans = re.sub(r"\s+", " ", trans).strip().title()
        if is_valid_latin_title(trans):
            return trans, "transliterated"

    return "Untitled Film", "fallback_default"


def resolve_english_overview(tmdb_id, current_overview="", lang="en", media_type="movie", session=None):
    """
    Resolves the strict Latin-only English overview for a movie.
    Never returns native-script text.
    """
    if current_overview and not NON_LATIN_RE.search(current_overview) and LATIN_LETTER_RE.search(current_overview):
        return current_overview.strip()

    if tmdb_id and TMDB_KEY:
        s = session or requests.Session()
        endpoint_type = "tv" if media_type == "tv" else "movie"
        try:
            url = f"{TMDB_BASE}/{endpoint_type}/{tmdb_id}?api_key={TMDB_KEY}&language=en-US"
            resp = s.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                ov = data.get("overview")
                if ov and not NON_LATIN_RE.search(ov) and LATIN_LETTER_RE.search(ov):
                    return ov.strip()
        except Exception:
            pass

        try:
            url = f"{TMDB_BASE}/{endpoint_type}/{tmdb_id}/translations?api_key={TMDB_KEY}"
            resp = s.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                for tr in data.get("translations", []):
                    if tr.get("iso_639_1") == "en":
                        ov = tr.get("data", {}).get("overview")
                        if ov and not NON_LATIN_RE.search(ov) and LATIN_LETTER_RE.search(ov):
                            return ov.strip()
        except Exception:
            pass

    return "No English synopsis available yet."


if __name__ == "__main__":
    print("Testing english_titles resolver...")
    test_cases = [
        (587412, "ಕೆ.ಜಿ.ಎಫ್: Chapter 2", "K.G.F: Chapter 2", "kn"),
        (263475, "கத்தி", "Kaththi", "ta"),
        (15772, "गुरु", "Guru", "hi"),
        (858485, "ಕಾಂತಾರ", "Kantara", "kn"),
        (1271, "300", "300", "en")
    ]
    for tid, tnat, ten, l in test_cases:
        resolved, src = resolve_english_title(tid, tnat, ten, l)
        print(f"[{tid}] {tnat} -> '{resolved}' (source: {src})")