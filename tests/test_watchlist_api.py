import json
import unittest
from app import app

class TestWatchlistAPI(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_watchlist_lifecycle(self):
        # 1. Access /watchlist page
        res = self.client.get("/watchlist")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"My Watchlist", res.data)
        self.assertIn("cinestream_uid", res.headers.get("Set-Cookie", ""))

        # 2. Add movie to watchlist
        add_res = self.client.post("/api/watchlist", json={
            "tmdb_id": 587412,
            "media_type": "movie"
        })
        self.assertEqual(add_res.status_code, 200)
        data = add_res.get_json()
        self.assertTrue(data["success"])

        # Add second movie
        self.client.post("/api/watchlist", json={
            "tmdb_id": 858485,
            "media_type": "movie"
        })

        # 3. GET /api/watchlist
        get_res = self.client.get("/api/watchlist")
        self.assertEqual(get_res.status_code, 200)
        wl_data = get_res.get_json()
        self.assertGreaterEqual(wl_data["count"], 2)
        titles = [it["title"] for it in wl_data["items"]]
        print("Watchlist items in test:", titles)
        for t in titles:
            self.assertTrue(all(ord(c) < 128 for c in t if c.isalnum()), f"Non-ASCII title found: {t}")

        # 4. PATCH movie watched and rating
        patch_res = self.client.patch("/api/watchlist/movie/587412", json={
            "watched": 1,
            "rating": 5.0
        })
        self.assertEqual(patch_res.status_code, 200)

        # 5. POST /api/watchlist/reorder
        reorder_res = self.client.post("/api/watchlist/reorder", json={
            "items": [
                {"tmdb_id": 858485, "media_type": "movie", "position": 0},
                {"tmdb_id": 587412, "media_type": "movie", "position": 1}
            ]
        })
        self.assertEqual(reorder_res.status_code, 200)

        # 6. GET /api/watchlist/recommend
        rec_res = self.client.get("/api/watchlist/recommend?top_n=5")
        self.assertEqual(rec_res.status_code, 200)
        rec_data = rec_res.get_json()
        self.assertIn("recommendations", rec_data)
        if rec_data["recommendations"]:
            first_rec = rec_data["recommendations"][0]
            self.assertIn("match_percentage", first_rec)
            self.assertIn("why_this", first_rec)
            print("Top watchlist recommendation:", first_rec["title_en"], f"({first_rec['match_percentage']}% match) - {first_rec['why_this']}")

        # 7. GET /api/watchlist/clusters
        cluster_res = self.client.get("/api/watchlist/clusters")
        self.assertEqual(cluster_res.status_code, 200)
        c_data = cluster_res.get_json()
        self.assertIn("labels", c_data)
        self.assertIn("data", c_data)
        print("Watchlist clusters:", c_data)

        # 8. DELETE single item
        del_one = self.client.delete("/api/watchlist/movie/858485")
        self.assertEqual(del_one.status_code, 200)

        # 9. DELETE all items
        del_all = self.client.delete("/api/watchlist")
        self.assertEqual(del_all.status_code, 200)
        clear_data = del_all.get_json()
        self.assertTrue(clear_data["success"])

if __name__ == "__main__":
    unittest.main()
