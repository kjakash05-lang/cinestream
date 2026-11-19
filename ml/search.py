"""
search.py - Multi-Language Search Engine for CineStream
Supports:
1. Native script search (Hindi, Kannada, Tamil, Telugu, Malayalam)
2. English title search
3. Phonetic & Roman transliteration search via indic-transliteration & RapidFuzz
4. Mood & Genre keyword mappings across all 6 languages
5. Script auto-detection via Unicode ranges
"""
import os
import re
import pandas as pd
from rapidfuzz import fuzz, process
from indic_transliteration import sanscript

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
MOVIES_CSV = os.path.join(DATA_DIR, "movies_all.csv")

# Script to Sanscript scheme mapping
SCRIPT_MAP = {
    "hi": sanscript.DEVANAGARI,
    "kn": sanscript.KANNADA,
    "ta": sanscript.TAMIL,
    "te": sanscript.TELUGU,
    "ml": sanscript.MALAYALAM,
}

GENRE_KEYWORDS = {
    # Hindi
    "रोमांटिक": "Romance", "रोमांस": "Romance", "प्यार": "Romance", "इश्क": "Romance",
    "एक्शन": "Action", "मारधाड़": "Action", "लड़ाई": "Action",
    "कॉमेडी": "Comedy", "हास्य": "Comedy", "मजाकिया": "Comedy",
    "ड्रामा": "Drama", "नाटक": "Drama", "भावना": "Drama",
    "हॉरर": "Horror", "डर": "Horror", "डरावनी": "Horror", "भूत": "Horror",
    "थ्रिलर": "Thriller", "सस्पेंस": "Thriller", "रहस्य": "Thriller",
    "एडवेंचर": "Adventure", "साहसिक": "Adventure",
    "एनीमेशन": "Animation", "कार्टून": "Animation",
    "क्राइम": "Crime", "अपराध": "Crime", "गैंगस्टर": "Crime",
    "वॉर": "War", "युद्ध": "War",
    "साइंस फिक्शन": "Sci-Fi", "वैज्ञानिक": "Sci-Fi",

    # Kannada
    "ಆಕ್ಷನ್": "Action", "ಸಾಹಸ": "Adventure", "ರೋಮ್ಯಾಂಟಿಕ್": "Romance",
    "ಪ್ರೀತಿ": "Romance", "ಹಾಸ್ಯ": "Comedy", "ಕಾಮಿಡಿ": "Comedy",
    "ನಾಟಕ": "Drama", "ಡ್ರಾಮಾ": "Drama", "ಭಯಾನಕ": "Horror", "ಹಾರರ್": "Horror",
    "ರೋಮಾಂಚಕ": "Thriller", "ಥ್ರಿಲ್ಲರ್": "Thriller", "ಅಪರಾಧ": "Crime",
    "ಯುದ್ಧ": "War", "ವಿಜ್ಞಾನ": "Sci-Fi",

    # Tamil
    "ஆக்ஷன்": "Action", "சண்டை": "Action", "காதல்": "Romance", "ரொமான்ஸ்": "Romance",
    "நகைச்சுவை": "Comedy", "காமெடி": "Comedy", "நாடகம்": "Drama", "டிராமா": "Drama",
    "பயங்கரம்": "Horror", "பேய்": "Horror", "திகில்": "Thriller", "த்ரில்லர்": "Thriller",
    "சாகசம்": "Adventure", "குற்றம்": "Crime", "போர்": "War",

    # Telugu
    "యాక్షన్": "Action", "ప్రేమ": "Romance", "రొమాంటిక్": "Romance",
    "హాస్యం": "Comedy", "కామెడీ": "Comedy", "నాటకం": "Drama", "డ్రామా": "Drama",
    "భయానకం": "Horror", "హారర్": "Horror", "థ్రిల్లర్": "Thriller", "ఉత్కంఠ": "Thriller",
    "సాహసం": "Adventure", "నేరం": "Crime", "యుద్ధం": "War",

    # Malayalam
    "ആക്ഷൻ": "Action", "പ്രണയം": "Romance", "റൊമാന്റിക്": "Romance",
    "ഹാസ്യം": "Comedy", "കോമഡി": "Comedy", "നാടകം": "Drama", "ഡ്രാമ": "Drama",
    "ഹൊറർ": "Horror", "ഭയം": "Horror", "ത്രില്ലർ": "Thriller",
    "സാഹസികം": "Adventure", "കുറ്റകൃത്യം": "Crime", "യുദ്ധം": "War",

    # English equivalents
    "action": "Action", "romance": "Romance", "romantic": "Romance", "love": "Romance",
    "comedy": "Comedy", "funny": "Comedy", "drama": "Drama", "horror": "Horror",
    "scary": "Horror", "thriller": "Thriller", "suspense": "Thriller", "adventure": "Adventure",
    "crime": "Crime", "animation": "Animation", "war": "War", "sci-fi": "Sci-Fi"
}


def detect_script(query: str):
    """Detects Indian script from Unicode block ranges."""
    for ch in query:
        code = ord(ch)
        if 0x0900 <= code <= 0x097F:
            return "hi"
        elif 0x0C80 <= code <= 0x0CFF:
            return "kn"
        elif 0x0B80 <= code <= 0x0BFF:
            return "ta"
        elif 0x0C00 <= code <= 0x0C7F:
            return "te"
        elif 0x0D00 <= code <= 0x0D7F:
            return "ml"
    return "en"


def romanize_indic_text(text: str, lang: str):
    """Transliterates native Indic script to Roman characters."""
    scheme = SCRIPT_MAP.get(lang)
    if not scheme or not text:
        return text.lower()
    try:
        roman = sanscript.transliterate(text, scheme, sanscript.ITRANS)
        return re.sub(r"[^a-zA-Z0-9\s]", "", roman).lower()
    except Exception:
        return text.lower()


class MultiLanguageSearchEngine:
    """Fast in-memory fuzzy search with transliteration and script detection."""

    def __init__(self, csv_path=MOVIES_CSV):
        self.csv_path = csv_path
        self.df = None
        self.loaded = False
        self.load()

    def load(self):
        if not os.path.exists(self.csv_path):
            print(f"[SearchEngine] Movie dataset {self.csv_path} not found.")
            return

        df = pd.read_csv(self.csv_path)
        df["title_en_clean"] = df["title_en"].fillna("").astype(str).str.lower().str.strip()
        df["title_native_clean"] = df["title_native"].fillna("").astype(str).str.strip()

        # Build romanized search keys for Indian regional films
        roman_titles = []
        for _, row in df.iterrows():
            lang = str(row.get("lang", "en"))
            native = str(row.get("title_native", ""))
            if lang in SCRIPT_MAP and native:
                roman_titles.append(romanize_indic_text(native, lang))
            else:
                roman_titles.append(str(row.get("title_en", "")).lower())
        df["title_roman"] = roman_titles

        self.df = df
        self.loaded = True
        print(f"[SearchEngine] Loaded {len(df)} movies across 6 languages.")

    def search(self, query: str, lang: str = "all", top_n: int = 15):
        if not self.loaded or self.df is None or not query.strip():
            return {"results": [], "detected_lang": "en", "genre_matched": None}

        q = query.strip()
        q_lower = q.lower()

        # 1. Script Detection
        detected_lang = detect_script(q)
        if lang == "all" and detected_lang != "en":
            active_lang = detected_lang
        else:
            active_lang = lang

        # Filter pool by language if requested
        if active_lang != "all":
            pool = self.df[self.df["lang"] == active_lang].copy()
            if pool.empty:
                pool = self.df.copy()
        else:
            pool = self.df.copy()

        # 2. Mood / Genre Mapping
        genre_match = GENRE_KEYWORDS.get(q_lower) or GENRE_KEYWORDS.get(q)
        if genre_match:
            genre_filtered = pool[pool["genres"].str.contains(genre_match, case=False, na=False)].copy()
            genre_filtered = genre_filtered.sort_values("popularity", ascending=False).head(top_n)
            results = []
            for _, r in genre_filtered.iterrows():
                results.append(self._format_movie(r))
            return {
                "results": results,
                "detected_lang": detected_lang,
                "active_lang": active_lang,
                "genre_matched": genre_match
            }

        # 3. Transliterate Latin query if searching native Indian pool
        q_indic_roman = re.sub(r"[^a-zA-Z0-9\s]", "", q_lower)

        # Score candidates
        scored = []
        for idx, row in pool.iterrows():
            title_en = row["title_en_clean"]
            title_nat = row["title_native"]
            title_rom = row["title_roman"]

            # Exact or prefix match bonuses
            if q_lower == title_en or q == title_nat:
                score = 100.0
            elif title_en.startswith(q_lower) or title_nat.startswith(q):
                score = 95.0
            elif q_lower in title_en or q in title_nat:
                score = 88.0
            else:
                s1 = fuzz.token_set_ratio(q_lower, title_en)
                s2 = fuzz.token_set_ratio(q, title_nat)
                s3 = fuzz.token_set_ratio(q_indic_roman, title_rom)
                score = max(s1, s2, s3)

            if score >= 45:
                # Add slight tie-breaker based on popularity/votes
                weighted_score = score + min(5.0, (row.get("vote_count", 0) / 1000.0))
                scored.append((weighted_score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_candidates = [item[1] for item in scored[:top_n]]

        results = [self._format_movie(r) for r in top_candidates]
        return {
            "results": results,
            "detected_lang": detected_lang,
            "active_lang": active_lang,
            "genre_matched": None
        }

    def _format_movie(self, row):
        from ml.english_titles import get_language_name, NON_LATIN_RE
        title_disp = str(row["title_en"]).strip()
        if NON_LATIN_RE.search(title_disp):
            title_disp = NON_LATIN_RE.sub("", str(row.get("title_native", ""))).strip() or "Untitled Film"
        lang_code = str(row["lang"]).lower().strip()
        return {
            "tmdb_id": int(row["tmdb_id"]),
            "movieId": int(row["tmdb_id"]),  # Compatibility alias
            "lang": lang_code,
            "language_name": get_language_name(lang_code),
            "industry": str(row["industry"]),
            "title": title_disp,
            "title_en": title_disp,
            "title_native": str(row["title_native"]),
            "year": int(row["year"]) if pd.notna(row.get("year")) else None,
            "genres": str(row["genres"]),
            "runtime": int(row.get("runtime", 120)),
            "vote_average": round(float(row.get("vote_average", 6.5)), 2),
            "vote_count": int(row.get("vote_count", 100)),
            "avgRating": round(float(row.get("vote_average", 6.5)), 2),
            "overview": str(row.get("overview", "")),
            "poster_url": str(row["poster_url"]),
            "backdrop_url": str(row.get("backdrop_url", "")),
            "cluster": int(row.get("cluster", 0)) if "cluster" in row else 0,
            "clusterName": str(row.get("clusterName", "Cinema")) if "clusterName" in row else "Cinema",
        }


# Global search engine singleton
_search_engine = None

def get_search_engine() -> MultiLanguageSearchEngine:
    global _search_engine
    if _search_engine is None:
        _search_engine = MultiLanguageSearchEngine()
    return _search_engine
