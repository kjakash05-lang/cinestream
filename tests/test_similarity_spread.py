import unittest
from collections import Counter
from app import app

class TestSimilaritySpread(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_similarity_spread_and_diversity(self):
        res = self.client.get('/api/recommend/featured?slug=ramayana-part-1&all_langs=1')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('cluster_picks', data)
        self.assertIn('closest_matches', data)

        for shelf_key in ['cluster_picks', 'closest_matches', 'top_rated_picks']:
            items = data.get(shelf_key, [])
            self.assertGreaterEqual(len(items), 8, f"{shelf_key} should have at least 8 items")

            pcts = [m.get('similarity_pct', 0) for m in items[:10]]
            counts = Counter(pcts)
            max_dup = max(counts.values()) if counts else 0
            # Fails if >50% of top-10 results share identical match percent
            self.assertLessEqual(max_dup, 5, f"Too many identical match percentages in {shelf_key}: {pcts}")
            self.assertGreaterEqual(min(pcts), 60, f"Match percent below 60% in {shelf_key}")
            self.assertLessEqual(max(pcts), 96, f"Match percent above 96% in {shelf_key}")

    def test_ramayana_mythology_epics(self):
        res = self.client.get('/api/recommend/featured?slug=ramayana-part-1&all_langs=1')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        all_recs = data.get('closest_matches', []) + data.get('cluster_picks', [])
        all_titles = ' '.join(m.get('title_en', '') for m in all_recs).lower()

        epic_targets = ['kantara', 'brahmastra', 'hanu-man', 'baahubali', 'adipurush', 'karthikeya', 'tanhaji']
        matched = [ep for ep in epic_targets if ep in all_titles]
        print('Matched epics for Ramayana:', matched)
        self.assertGreaterEqual(len(matched), 3, f"Expected at least 3 mythology/epic matches, got: {matched}")

    def test_rating_scales(self):
        res = self.client.get('/api/recommend/featured?slug=ramayana-part-1&all_langs=1')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        for m in data.get('closest_matches', [])[:5]:
            self.assertIn('avgRatingDisplay', m)
            self.assertTrue(m['avgRatingDisplay'].endswith('/10'), f"TMDB rating should be /10 scale: {m['avgRatingDisplay']}")

    def test_cold_start_wording(self):
        res = self.client.get('/api/recommend/featured?slug=ramayana-part-1&userId=cold_user_999')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('is_cold_start'), 'Cold start should be True for user with <3 ratings')
        self.assertEqual(data.get('row_title'), 'Popular picks for you')
        self.assertIn('Rate 3 movies', data.get('row_subtitle', ''))

if __name__ == '__main__':
    unittest.main()
