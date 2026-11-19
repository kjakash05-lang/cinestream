"""
collaborative.py
Item-based KNN and SVD Matrix Factorization collaborative filtering using MovieLens dataset.
Maps MovieLens movieId to tmdbId via data/links.csv.
Provides item-item similarity and personalized rating prediction with graceful fallback.
"""
import os
import pickle
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.neighbors import NearestNeighbors
from sklearn.decomposition import TruncatedSVD
from sklearn.metrics.pairwise import cosine_similarity

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
MODEL_DIR = os.path.join(ROOT, "models")
RATINGS_CSV = os.path.join(DATA_DIR, "ratings.csv")
LINKS_CSV = os.path.join(DATA_DIR, "links.csv")
COLLAB_MODEL_PKL = os.path.join(MODEL_DIR, "collab_model.pkl")

class CollaborativeRecommender:
    def __init__(self):
        self.item_knn = None
        self.svd = None
        self.movie_to_idx = {}
        self.idx_to_movie = {}
        self.tmdb_to_mid = {}
        self.mid_to_tmdb = {}
        self.item_item_sim = None
        self.global_mean = 3.5
        self.movie_means = {}
        self.loaded = False
        self._load_or_train()

    def _load_or_train(self):
        if os.path.exists(COLLAB_MODEL_PKL):
            try:
                with open(COLLAB_MODEL_PKL, "rb") as f:
                    data = pickle.load(f)
                    self.item_item_sim = data["item_item_sim"]
                    self.movie_to_idx = data["movie_to_idx"]
                    self.idx_to_movie = data["idx_to_movie"]
                    self.tmdb_to_mid = data["tmdb_to_mid"]
                    self.mid_to_tmdb = data["mid_to_tmdb"]
                    self.global_mean = data.get("global_mean", 3.5)
                    self.movie_means = data.get("movie_means", {})
                    self.loaded = True
                    print("[Collab] Loaded collaborative filtering model from cache.")
                    return
            except Exception as e:
                print(f"[Collab] Warning loading cache: {e}. Retraining...")

        self.train()

    def train(self):
        if not os.path.exists(RATINGS_CSV) or not os.path.exists(LINKS_CSV):
            print("[Collab] Warning: ratings.csv or links.csv not found.")
            return

        ratings_df = pd.read_csv(RATINGS_CSV)
        links_df = pd.read_csv(LINKS_CSV).dropna(subset=["tmdbId"])
        links_df["tmdbId"] = links_df["tmdbId"].astype(int)

        self.mid_to_tmdb = dict(zip(links_df["movieId"], links_df["tmdbId"]))
        self.tmdb_to_mid = dict(zip(links_df["tmdbId"], links_df["movieId"]))

        # Filter to movies with at least 5 ratings for quality
        movie_counts = ratings_df["movieId"].value_counts()
        valid_movies = movie_counts[movie_counts >= 5].index
        filtered_ratings = ratings_df[ratings_df["movieId"].isin(valid_movies)].copy()

        self.global_mean = float(filtered_ratings["rating"].mean())
        self.movie_means = filtered_ratings.groupby("movieId")["rating"].mean().to_dict()

        # Build user-item matrix
        users = sorted(filtered_ratings["userId"].unique())
        movies = sorted(filtered_ratings["movieId"].unique())

        user_to_idx = {u: i for i, u in enumerate(users)}
        self.movie_to_idx = {m: i for i, m in enumerate(movies)}
        self.idx_to_movie = {i: m for m, i in self.movie_to_idx.items()}

        rows = filtered_ratings["userId"].map(user_to_idx)
        cols = filtered_ratings["movieId"].map(self.movie_to_idx)
        vals = filtered_ratings["rating"].values

        R_sparse = csr_matrix((vals, (rows, cols)), shape=(len(users), len(movies)))

        # SVD on item matrix (movies as rows)
        # Transpose so rows are items (movies), cols are users
        item_user_mat = R_sparse.T.tocsr()
        n_comp = min(30, min(item_user_mat.shape) - 1)
        self.svd = TruncatedSVD(n_components=n_comp, random_state=42)
        item_factors = self.svd.fit_transform(item_user_mat)

        # Compute cosine similarity between item latent representations
        self.item_item_sim = cosine_similarity(item_factors)

        self.loaded = True

        os.makedirs(MODEL_DIR, exist_ok=True)
        try:
            with open(COLLAB_MODEL_PKL, "wb") as f:
                pickle.dump({
                    "item_item_sim": self.item_item_sim,
                    "movie_to_idx": self.movie_to_idx,
                    "idx_to_movie": self.idx_to_movie,
                    "tmdb_to_mid": self.tmdb_to_mid,
                    "mid_to_tmdb": self.mid_to_tmdb,
                    "global_mean": self.global_mean,
                    "movie_means": self.movie_means
                }, f)
            print("[Collab] Successfully trained and cached collaborative model.")
        except Exception as e:
            print(f"[Collab] Error saving model: {e}")

    def predict_user_rating(self, user_ratings: dict, tmdb_id: int):
        """
        Predicts rating (1.0 - 5.0) for a given tmdb_id based on user's known ratings.
        Returns None if tmdb_id is not present in collaborative dataset.
        """
        if not self.loaded or not self.item_item_sim is not None:
            return None

        # Resolve target movie
        target_mid = self.tmdb_to_mid.get(int(tmdb_id))
        if not target_mid or target_mid not in self.movie_to_idx:
            return None

        target_idx = self.movie_to_idx[target_mid]
        sim_vector = self.item_item_sim[target_idx]

        numerator = 0.0
        denominator = 0.0

        for r_id_str, user_score in user_ratings.items():
            try:
                r_id = int(r_id_str)
                # Could be tmdbId or movieId
                mid = self.tmdb_to_mid.get(r_id, r_id)
                if mid in self.movie_to_idx:
                    m_idx = self.movie_to_idx[mid]
                    sim = sim_vector[m_idx]
                    if sim > 0:
                        numerator += sim * float(user_score)
                        denominator += sim
            except Exception:
                continue

        if denominator > 0.05:
            pred = numerator / denominator
            return round(float(np.clip(pred, 1.0, 5.0)), 2)

        # Fallback to movie mean if known, else None
        if target_mid in self.movie_means:
            return round(float(self.movie_means[target_mid]), 2)
        return None

    def get_similar_movies(self, tmdb_id: int, top_n: int = 10):
        """Returns list of (tmdb_id, similarity_score) for movies similar via collaborative ratings."""
        if not self.loaded or self.item_item_sim is None:
            return []

        mid = self.tmdb_to_mid.get(int(tmdb_id))
        if not mid or mid not in self.movie_to_idx:
            return []

        idx = self.movie_to_idx[mid]
        sims = self.item_item_sim[idx].copy()
        sims[idx] = -1.0

        top_indices = np.argsort(sims)[::-1][:top_n]
        results = []
        for i in top_indices:
            other_mid = self.idx_to_movie[i]
            other_tmdb = self.mid_to_tmdb.get(other_mid)
            if other_tmdb:
                results.append((other_tmdb, float(sims[i])))
        return results
