"""
test_english_only.py - Backend Test Suite for Strict English Display
Validates that every API response contains zero characters in non-Latin scripts:
- Devanagari (0900-097F)
- Tamil (0B80-0BFF)
- Telugu (0C00-0C7F)
- Kannada (0C80-0CFF)
- Malayalam (0D00-0D7F)
- Japanese / CJK (3040-30FF, 4E00-9FFF)
"""
import os
import sys
import re
import json
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from app import app
from ml.english_titles import NON_LATIN_RE

# Non-Latin Unicode regex covering the required ranges
FORBIDDEN_UNICODE_RE = re.compile(
    r"[\u0900-\u097F"   # Devanagari
    r"\u0B80-\u0BFF"   # Tamil
    r"\u0C00-\u0C7F"   # Telugu
    r"\u0C80-\u0CFF"   # Kannada
    r"\u0D00-\u0D7F"   # Malayalam
    r"\u3040-\u30FF"   # Japanese Hiragana & Katakana
    r"\u4E00-\u9FFF]"  # CJK Unified Ideographs
)

class TestStrictEnglishOnly(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def assert_no_non_latin(self, text, context=""):
        if not text or not isinstance(text, str):
            return
        match = FORBIDDEN_UNICODE_RE.search(text)
        if match:
            bad_char = match.group(0)
            codepoint = f"U+{ord(bad_char):04X}"
            self.fail(
                f"Non-Latin character '{bad_char}' ({codepoint}) found in {context}: '{text[:80]}...'"
            )

    def check_movie_object(self, m, endpoint_context):
        # Fields that are rendered visually on the UI
        fields_to_check = [
            "title",
            "title_en",
            "language_name",
            "industry",
            "cluster_name",
            "clusterName",
            "overview",
            "genres",
            "genres_formatted",
            "badge_text",
            "why_this"
        ]
        for field in fields_to_check:
            val = m.get(field)
            if val is not None:
                self.assert_no_non_latin(str(val), f"{endpoint_context} -> {field}")

    def test_api_featured(self):
        """Test /api/featured across all languages."""
        for lang in ["all", "en", "hi", "kn", "ta", "te", "ml"]:
            res = self.client.get(f"/api/featured?lang={lang}")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            movies = data if isinstance(data, list) else (data.get("featured") or data.get("movies") or [])
            for m in movies:
                self.check_movie_object(m, f"/api/featured?lang={lang}")

    def test_api_movies_browse_tabs(self):
        """Test /api/movies across all browse categories."""
        categories = ["All", "Movies", "TV", "Animation", "Anime", "Action", "Drama"]
        for cat in categories:
            res = self.client.get(f"/api/movies?category={cat}&per_page=20")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            for m in data.get("movies", []):
                self.check_movie_object(m, f"/api/movies?category={cat}")

    def test_api_recommend(self):
        """Test /api/recommend response."""
        res = self.client.get("/api/recommend?model=rf&lang=all")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        for m in data.get("recommendations", []):
            self.check_movie_object(m, "/api/recommend")
        for m in data.get("cross_language_picks", []):
            self.check_movie_object(m, "/api/recommend (cross_language)")

    def test_api_search(self):
        """Test /api/search with both English and native query inputs."""
        queries = ["action", "kantara", "drama", "romance", "kgf", "comedy"]
        for q in queries:
            res = self.client.get(f"/api/search?q={q}")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            for m in data.get("results", []):
                self.check_movie_object(m, f"/api/search?q={q}")

    def test_api_watchlist_endpoints(self):
        """Test /api/watchlist and /api/watchlist/recommend."""
        # Add sample movie (Kantara: 858485)
        post_res = self.client.post("/api/watchlist", json={"tmdb_id": 858485, "media_type": "movie"})
        self.assertEqual(post_res.status_code, 200)

        # GET /api/watchlist
        res = self.client.get("/api/watchlist")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        for item in data.get("items", []):
            self.check_movie_object(item, "/api/watchlist")

        # GET /api/watchlist/recommend
        rec_res = self.client.get("/api/watchlist/recommend")
        self.assertEqual(rec_res.status_code, 200)
        rec_data = rec_res.get_json()
        for m in rec_data.get("recommendations", []):
            self.check_movie_object(m, "/api/watchlist/recommend")

        # Clean up
        self.client.delete("/api/watchlist")

    def test_api_languages(self):
        """Test /api/languages config has English-only display strings."""
        res = self.client.get("/api/languages")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        for lang, conf in data.items():
            self.assert_no_non_latin(conf.get("name"), f"/api/languages -> {lang} name")
            self.assert_no_non_latin(conf.get("native"), f"/api/languages -> {lang} native")
            self.assert_no_non_latin(conf.get("industry"), f"/api/languages -> {lang} industry")


if __name__ == "__main__":
    unittest.main()