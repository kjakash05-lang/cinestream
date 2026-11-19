"""
test_regression.py - Comprehensive CineStream Endpoint & Multi-Feature Regression Suite
Validates status codes, JSON payload integrity, and 100% Latin-character display rules.
"""
import json
import pytest
from app import app
from ml.english_titles import NON_LATIN_RE

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        yield c

class TestCineStreamRegression:
    def test_pages_load(self, client):
        for route in ["/", "/watchlist", "/login"]:
            res = client.get(route)
            assert res.status_code == 200, f"Route {route} failed with status {res.status_code}"

    def test_api_languages(self, client):
        res = client.get("/api/languages")
        assert res.status_code == 200
        data = res.get_json()
        assert "all" in data
        assert "en" in data
        assert "kn" in data

    def test_api_featured_latin_only(self, client):
        for lang in ["all", "en", "hi", "kn", "ta", "te", "ml"]:
            res = client.get(f"/api/featured?lang={lang}")
            assert res.status_code == 200
            payload = res.get_json()
            movies = payload if isinstance(payload, list) else payload.get("featured", payload.get("movies", []))
            assert isinstance(movies, list)
            for m in movies:
                title = m.get("title", "")
                assert not NON_LATIN_RE.search(title), f"Non-Latin title in featured ({lang}): {title}"

    def test_api_movies_latin_only(self, client):
        res = client.get("/api/movies?lang=all&page=1&per_page=15")
        assert res.status_code == 200
        data = res.get_json()
        assert "movies" in data
        for m in data["movies"]:
            title = m.get("title", "")
            assert not NON_LATIN_RE.search(title), f"Non-Latin title in browse movies: {title}"

    def test_api_recommend_latin_only(self, client):
        res = client.get("/api/recommend?lang=all")
        assert res.status_code == 200
        data = res.get_json()
        assert "recommendations" in data
        for m in data["recommendations"]:
            title = m.get("title", "")
            assert not NON_LATIN_RE.search(title), f"Non-Latin title in recommendations: {title}"

    def test_api_clusters_and_metrics(self, client):
        res = client.get("/api/clusters?lang=all")
        assert res.status_code == 200
        cdata = res.get_json()
        assert "clusters" in cdata

        res = client.get("/api/metrics?lang=all")
        assert res.status_code == 200
        mdata = res.get_json()
        assert "metrics" in mdata

    def test_auth_me_anonymous(self, client):
        res = client.get("/api/auth/me")
        assert res.status_code == 200
        data = res.get_json()
        assert data["authenticated"] is False
        assert data["user"] is None
