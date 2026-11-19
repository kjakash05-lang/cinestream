"""
tests/test_posters_and_cards.py
Audits single source of truth for posters and movie cards across CineStream endpoints.
"""
import os
import json
import pytest
from app import app
from ml.cards import get_card, get_quick_pick_cards

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

def test_key_films_posters_and_metadata():
    """Verify the 6 audited films return accurate metadata and posters."""
    targets = [
        ("movie", 656908, "Ramayana: Part 1", "Bollywood", "vBQ7wks68OhJKlb3RnXSl2yXBXK"),
        ("movie", 587412, "K.G.F: Chapter 2", "Sandalwood", "khNVygolU0TxLIDWff5tQlAhZ23"),
        ("movie", 743563, "Vikram", "Kollywood", "774UV1aCURb4s4JfEFg3IEMu5Zj"),
        ("movie", 579974, "RRR", "Tollywood", "wE0I6efAW4cDDmZQWtwZMOW44EJ"),
        ("movie", 157336, "Interstellar", "Hollywood", "yQvGrMoipbRoddT0ZR8tPoR7NfX"),
        ("movie", 27205, "Inception", "Hollywood", "xlaY2zyzMfkhk0HSC5VUwzoZPU1"),
    ]
    for mtype, tmdb_id, title_part, industry, poster_frag in targets:
        card = get_card(mtype, tmdb_id)
        assert card is not None, f"Card missing for {tmdb_id}"
        assert title_part.lower() in card["title_en"].lower(), f"Title mismatch: {card['title_en']} vs {title_part}"
        assert card["industry"] == industry, f"Industry mismatch: {card['industry']} vs {industry}"
        assert poster_frag in card["poster_url"], f"Poster mismatch for {card['title_en']}: {card['poster_url']}"
        assert card["tmdb_id"] == tmdb_id
        assert card["media_type"] == mtype

def test_quick_picks_endpoint(client):
    """Verify /api/quick-picks returns all 5 diverse industry cards with valid posters."""
    res = client.get("/api/quick-picks")
    assert res.status_code == 200
    data = res.get_json()
    assert "items" in data
    assert len(data["items"]) == 5
    for item in data["items"]:
        assert item["tmdb_id"] > 0
        assert item["poster_url"].startswith("https://image.tmdb.org/t/p/")
        # Must match get_card single source of truth
        canon = get_card(item["media_type"], item["tmdb_id"])
        assert canon["poster_url"] == item["poster_url"]
        assert canon["title_en"] == item["title_en"]

def test_endpoints_card_consistency(client):
    """Verify cards returned across various endpoints match get_card single source of truth."""
    endpoints = [
        "/api/browse?per_page=10",
        "/api/recommend?userId=test_user&model=rf",
        "/api/personal/recommend?userId=test_user&model=rf",
        "/api/mood?mood=Action-Packed",
        "/api/search?q=action",
        "/api/featured",
        "/api/quick-picks"
    ]

    for ep in endpoints:
        res = client.get(ep)
        assert res.status_code == 200, f"Endpoint {ep} failed with {res.status_code}"
        data = res.get_json()

        # Extract card lists depending on endpoint schema
        cards = []
        if isinstance(data, list):
            cards = data
        elif isinstance(data, dict):
            for key in ["items", "movies", "recommendations", "results", "featured"]:
                if key in data and isinstance(data[key], list):
                    cards.extend(data[key])

        for c in cards[:5]:
            if not isinstance(c, dict):
                continue
            tmdb_id = c.get("tmdb_id") or c.get("tmdbId")
            media_type = c.get("media_type") or "movie"
            if tmdb_id:
                canon = get_card(media_type, int(tmdb_id))
                if canon:
                    assert canon["tmdb_id"] == int(tmdb_id)
                    assert canon["media_type"] == media_type
                    # If endpoint provides poster_url, ensure it matches canon
                    if c.get("poster_url"):
                        assert c["poster_url"] == canon["poster_url"]
