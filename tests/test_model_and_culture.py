"""
test_model_and_culture.py
Validates the 6 critical fixes:
1. Model dropdown: RF vs KNN return genuinely different ordered top-10 for a user with 5+ ratings.
   Cold start (<3 ratings) returns "Rate 3 movies to personalise. Showing popular picks".
2. Cross-language row: /api/cross-culture returns >= 70% non-English movies with language chips.
3. Cluster diversity: <= 60% of cards in personal recommendations share the same cluster name.
4. Scale formatting: predicted scores formatted as X.X/10.
"""
import pytest
from app import app, _user_ratings, _ratings_lock

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        yield c

class TestModelAndCulture:
    def test_cold_start_note_and_picks(self, client):
        """User with < 3 ratings receives cold start note and popular picks without fake numbers."""
        uid = "test_user_cold_start_123"
        with _ratings_lock:
            _user_ratings[uid] = {656908: 5.0}  # Only 1 rating

        res = client.get(f"/api/personal/recommend?userId={uid}&model=rf")
        assert res.status_code == 200
        data = res.get_json()

        assert data.get("cold_start") is True
        assert data.get("note") == "Rate 3 movies to personalise. Showing popular picks"
        assert len(data.get("recommendations", [])) > 0
        for m in data["recommendations"]:
            assert m.get("is_popular_pick") is True
            assert m.get("predictedRating") is None

    def test_rf_and_knn_return_genuinely_different_top_10(self, client):
        """
        User who has rated 5 movies gets genuinely DIFFERENT ordered top-10 lists from RF and KNN.
        Fails if RF and KNN return identical ordered top-10.
        """
        uid = "test_user_divergence_456"
        # 5 distinct ratings across genres
        with _ratings_lock:
            _user_ratings[uid] = {
                284053: 5.0,  # Thor: Ragnarok (Action/Adventure)
                508947: 4.5,  # Turning Red (Animation)
                597: 1.0,     # Titanic (Romance/Drama)
                155: 5.0,     # The Dark Knight (Action/Crime)
                680: 2.0      # Pulp Fiction (Crime)
            }

        res_rf = client.get(f"/api/personal/recommend?userId={uid}&model=rf&top_n=10")
        assert res_rf.status_code == 200
        data_rf = res_rf.get_json()
        assert data_rf.get("cold_start") is False

        res_knn = client.get(f"/api/personal/recommend?userId={uid}&model=knn&top_n=10")
        assert res_knn.status_code == 200
        data_knn = res_knn.get_json()
        assert data_knn.get("cold_start") is False

        top_rf_ids = [m["movieId"] for m in data_rf.get("recommendations", [])[:10]]
        top_knn_ids = [m["movieId"] for m in data_knn.get("recommendations", [])[:10]]

        assert len(top_rf_ids) == 10
        assert len(top_knn_ids) == 10
        # CRITICAL TEST: Must NOT be identical ordered list
        assert top_rf_ids != top_knn_ids, "Random Forest and KNN returned identical top 10 rankings!"

    def test_cross_culture_row_non_english_percentage(self, client):
        """
        /api/cross-culture must return Hindi, Kannada, Tamil, Telugu, and Malayalam movies.
        At least 70% of the items must be non-English.
        """
        res = client.get("/api/cross-culture")
        assert res.status_code == 200
        data = res.get_json()
        movies = data.get("movies", [])
        assert len(movies) >= 5

        regional_langs = {"hi", "kn", "ta", "te", "ml"}
        non_english_count = sum(1 for m in movies if m.get("lang") in regional_langs and m.get("lang") != "en")
        total = len(movies)
        ratio = non_english_count / total

        assert ratio >= 0.70, f"Expected >= 70% non-English movies, got {ratio * 100:.1f}%"
        # In our implementation it should be 100% regional
        for m in movies:
            assert m.get("lang") != "en", f"English movie found in cross-culture row: {m.get('title')}"

    def test_cluster_diversity_cap(self, client):
        """
        Cluster names must be rich and diverse:
        No single cluster name can account for > 60% of the shown recommendation cards.
        """
        uid = "test_user_diversity_789"
        with _ratings_lock:
            _user_ratings[uid] = {
                284053: 5.0,
                508947: 4.0,
                597: 3.5,
                155: 4.5,
                680: 3.0
            }

        res = client.get(f"/api/personal/recommend?userId={uid}&model=rf&top_n=10")
        assert res.status_code == 200
        data = res.get_json()
        recs = data.get("recommendations", [])
        assert len(recs) == 10

        cluster_counts = {}
        for m in recs:
            cname = m.get("clusterName") or m.get("cluster_name") or "General"
            cluster_counts[cname] = cluster_counts.get(cname, 0) + 1

        total = len(recs)
        for cname, count in cluster_counts.items():
            pct = count / total
            assert pct <= 0.60, f"Cluster '{cname}' accounts for {pct*100:.1f}% of cards, exceeding 60% cap!"

    def test_score_scale_labeling(self, client):
        """Predicted scores are labeled as X.X/10 and star ratings as Your rating: X/5."""
        uid = "test_user_scale_101"
        with _ratings_lock:
            _user_ratings[uid] = {
                284053: 5.0,  # Thor: Ragnarok
                597: 4.0,     # Titanic
                155: 2.0      # The Dark Knight
            }

        res = client.get(f"/api/personal/recommend?userId={uid}&model=rf&top_n=5")
        assert res.status_code == 200
        data = res.get_json()
        assert data.get("cold_start") is False
        recs = data.get("recommendations", [])
        assert len(recs) > 0

        for m in recs:
            s10 = m.get("predicted_score_10")
            assert s10 is not None
            assert 1.0 <= s10 <= 10.0
            assert m.get("predicted_score_label") == f"{s10:.1f}/10"
            assert "/10" in m.get("predictedRatingDisplay", "")

    def test_knn_zero_ratings_explicit_needs_ratings(self, client):
        """For a user with 0 ratings, model=knn returns an explicit 'needs_ratings' status, not a popularity list."""
        uid = "test_user_zero_ratings_999"
        with _ratings_lock:
            _user_ratings[uid] = {}

        res = client.get(f"/api/personal/recommend?userId={uid}&model=knn")
        assert res.status_code == 200
        data = res.get_json()

        assert data.get("status") == "needs_ratings"
        assert data.get("model") == "knn"
        assert data.get("cold_start") is True
        assert data.get("note") == "KNN needs at least 3 rated or saved movies"
        assert len(data.get("recommendations", [])) == 0, "KNN cold start must NOT return a popularity list!"

    def test_seeded_8_ratings_rf_vs_knn_overlap_below_8_of_10(self, client):
        """
        For a user with 8 seeded ratings, /api/personal/recommend?model=rf and ?model=knn
        return different ordered top-10 lists with overlap below 8 of 10, and each response includes
        'model' matching the request.
        """
        uid = "test_user_seeded_8_demo"
        # Seed demo profile via endpoint
        res_seed = client.post("/api/user/demo-profile", json={"userId": uid})
        assert res_seed.status_code == 200
        seed_data = res_seed.get_json()
        assert seed_data.get("success") is True
        assert seed_data.get("ratingsCount") == 8

        # 1. Fetch RF
        res_rf = client.get(f"/api/personal/recommend?userId={uid}&model=rf&top_n=10")
        assert res_rf.status_code == 200
        data_rf = res_rf.get_json()
        assert data_rf.get("model") == "rf"
        assert data_rf.get("status") == "success"
        assert data_rf.get("cold_start") is False
        rf_recs = data_rf.get("recommendations", [])
        assert len(rf_recs) == 10
        rf_top10_ids = [m["movieId"] for m in rf_recs]

        # 2. Fetch KNN
        res_knn = client.get(f"/api/personal/recommend?userId={uid}&model=knn&top_n=10")
        assert res_knn.status_code == 200
        data_knn = res_knn.get_json()
        assert data_knn.get("model") == "knn"
        assert data_knn.get("status") == "success"
        assert data_knn.get("cold_start") is False
        knn_recs = data_knn.get("recommendations", [])
        assert len(knn_recs) == 10
        knn_top10_ids = [m["movieId"] for m in knn_recs]

        # 3. Assert different rankings
        assert rf_top10_ids != knn_top10_ids, "RF and KNN top-10 must not be identical!"

        # 4. Assert overlap strictly below 8 of 10
        overlap = len(set(rf_top10_ids) & set(knn_top10_ids))
        assert overlap < 8, f"Expected overlap strictly below 8 of 10, got {overlap}/10!"

        # 5. Verify overlap metadata in API responses
        assert data_rf.get("overlap", {}).get("count") == overlap
        assert data_knn.get("overlap", {}).get("count") == overlap
        assert f"{overlap} of 10" in data_rf["overlap"]["label"]
        assert f"{overlap} of 10" in data_knn["overlap"]["label"]
