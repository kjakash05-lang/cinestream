"""
model.py - CineStream Unified Machine Learning Engine
Combines Unsupervised Learning (K-Means Clustering) and
Supervised Learning (KNN Regressor + Random Forest Regressor)
for personalized movie recommendations.

Features:
1. Data cleaning & One-Hot Genre Encoding
2. Unsupervised: K-Means clustering with Elbow Method, Silhouette Score, PCA 2D Projection
3. Cluster naming based on top-2 dominant genres
4. Supervised: KNN & Random Forest rating prediction
5. Performance comparison: WITH vs WITHOUT cluster feature (RMSE, MAE, R²)
6. Personalized recommendation logic (predicts unrated movies, top 6 returned)
7. Artifact persistence with joblib

Run directly:
    python model.py
"""

import os
import sys
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import KNeighborsRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score, silhouette_score
import joblib

warnings.filterwarnings("ignore")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT_DIR, "data")
MODEL_DIR = os.path.join(ROOT_DIR, "models")
IMG_DIR = os.path.join(ROOT_DIR, "static", "images")


class CineStreamMLModel:
    """Complete CineStream Machine Learning Architecture."""

    def __init__(self, data_dir=DATA_DIR, model_dir=MODEL_DIR, img_dir=IMG_DIR):
        self.data_dir = data_dir
        self.model_dir = model_dir
        self.img_dir = img_dir
        os.makedirs(self.model_dir, exist_ok=True)
        os.makedirs(self.img_dir, exist_ok=True)

        self.movies_df = None
        self.ratings_df = None
        self.genre_list = []
        self.kmeans = None
        self.optimal_k = None
        self.cluster_names = {}
        self.cluster_info = []
        self.sil_info = []

        self.knn = None
        self.rf = None
        self.scaler = None
        self.feature_cols = []
        self.feature_cols_no_cluster = []
        self.metrics = {}
        self.movie_meta = None
        self.is_trained = False

    # -------------------------------------------------------------------------
    # 1. DATA PREPARATION & CLEANING
    # -------------------------------------------------------------------------
    def load_and_preprocess_data(self):
        """Loads MovieLens datasets, handles nulls/duplicates and encodes genres."""
        movies_path = os.path.join(self.data_dir, "movies.csv")
        ratings_path = os.path.join(self.data_dir, "ratings.csv")

        if not os.path.exists(movies_path) or not os.path.exists(ratings_path):
            print("[INFO] Dataset not found in data/. Downloading automatically...")
            sys.path.insert(0, self.data_dir)
            from download_data import download_dataset
            download_dataset()

        print("[1/5] Cleaning and preprocessing data...")
        movies = pd.read_csv(movies_path).dropna().drop_duplicates(subset="movieId")
        ratings = pd.read_csv(ratings_path).dropna().drop_duplicates()

        # Extract year and clean title
        movies["year"] = movies["title"].str.extract(r"\((\d{4})\)$").astype(float)
        movies["title_clean"] = movies["title"].str.replace(r"\s*\(\d{4}\)\s*$", "", regex=True).str.strip()

        # One-hot encode genres
        all_genres = set()
        for g in movies["genres"]:
            all_genres.update(g.split("|"))
        all_genres.discard("(no genres listed)")
        self.genre_list = sorted(list(all_genres))

        for genre in self.genre_list:
            movies[genre] = movies["genres"].str.contains(genre, regex=False).astype(int)

        self.movies_df = movies
        self.ratings_df = ratings
        print(f"  Loaded {len(movies):,} movies and {len(ratings):,} ratings across {len(self.genre_list)} genres.")
        return movies, ratings

    # -------------------------------------------------------------------------
    # 2. UNSUPERVISED: K-MEANS CLUSTERING & PCA VISUALIZATION
    # -------------------------------------------------------------------------
    def train_unsupervised_kmeans(self, k_min=2, k_max=15):
        """Runs Elbow Method & Silhouette Analysis, fits optimal K-Means, and projects via PCA."""
        print("\n[2/5] Training Unsupervised Model: K-Means Clustering...")
        X_genres = self.movies_df[self.genre_list].values

        k_range = range(k_min, k_max + 1)
        inertias = []
        sil_scores = []

        print("  Evaluating K values using Inertia (Elbow) and Silhouette Scores...")
        for k in k_range:
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(X_genres)
            inertias.append(km.inertia_)
            sil_scores.append(silhouette_score(X_genres, labels, sample_size=min(2000, len(self.movies_df))))

        # Determine optimal k by highest silhouette score
        best_idx = int(np.argmax(sil_scores))
        self.optimal_k = list(k_range)[best_idx]
        print(f"  Optimal k selected: {self.optimal_k} (Silhouette Score: {sil_scores[best_idx]:.4f})")

        # Plot Elbow and Silhouette curves
        self._plot_elbow_and_silhouette(k_range, inertias, sil_scores, self.optimal_k)

        # Fit final K-Means
        self.kmeans = KMeans(n_clusters=self.optimal_k, random_state=42, n_init=10)
        self.movies_df["cluster"] = self.kmeans.fit_predict(X_genres)

        # Name each cluster by its top-2 dominant genres
        self.cluster_names = {}
        self.cluster_info = []
        for cid in range(self.optimal_k):
            mask = self.movies_df["cluster"] == cid
            genre_totals = self.movies_df.loc[mask, self.genre_list].sum().sort_values(ascending=False)
            top2 = list(genre_totals.head(2).index)
            name = " + ".join(top2)
            self.cluster_names[cid] = name
            self.cluster_info.append({
                "id": cid,
                "name": name,
                "top_genres": list(genre_totals.head(5).index),
                "count": int(mask.sum())
            })
            print(f"  Cluster {cid:02d}: '{name}' ({mask.sum()} movies)")

        # 2D PCA Visualization
        self._plot_pca_projection(X_genres, self.movies_df["cluster"].values)

        self.sil_info = [
            {"k": int(k), "silhouette": round(float(s), 4), "inertia": round(float(inn), 2)}
            for k, s, inn in zip(k_range, sil_scores, inertias)
        ]
        return self.kmeans

    def _plot_elbow_and_silhouette(self, k_range, inertias, sil_scores, optimal_k):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
        fig.patch.set_facecolor("#0f0f12")
        for ax in (ax1, ax2):
            ax.set_facecolor("#1a1a1f")
            ax.tick_params(colors="#aaa")
            for spine in ax.spines.values():
                spine.set_color("#333")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)

        ax1.plot(list(k_range), inertias, "o-", color="#f9e27d", lw=2, ms=6)
        ax1.axvline(optimal_k, color="#f9e27d", ls="--", alpha=0.6, label=f"k={optimal_k}")
        ax1.set_title("Elbow Method (Inertia)", color="white", fontsize=12, pad=10)
        ax1.set_xlabel("Number of Clusters (k)", color="#aaa")
        ax1.set_ylabel("Inertia", color="#aaa")
        ax1.legend(facecolor="#1a1a1f", labelcolor="white", edgecolor="#333")

        ax2.plot(list(k_range), sil_scores, "s-", color="#7de8f9", lw=2, ms=6)
        ax2.axvline(optimal_k, color="#7de8f9", ls="--", alpha=0.6, label=f"Optimal k={optimal_k}")
        ax2.set_title("Silhouette Score", color="white", fontsize=12, pad=10)
        ax2.set_xlabel("Number of Clusters (k)", color="#aaa")
        ax2.set_ylabel("Silhouette Score", color="#aaa")
        ax2.legend(facecolor="#1a1a1f", labelcolor="white", edgecolor="#333")

        plt.tight_layout()
        elbow_path = os.path.join(self.img_dir, "elbow_plot.png")
        plt.savefig(elbow_path, dpi=120, bbox_inches="tight", facecolor="#0f0f12")
        plt.close()
        print(f"  Elbow & Silhouette plot saved to {elbow_path}")

    def _plot_pca_projection(self, X_genres, labels):
        pca = PCA(n_components=2, random_state=42)
        coords_2d = pca.fit_transform(X_genres)
        var_exp = pca.explained_variance_ratio_

        fig, ax = plt.subplots(figsize=(10, 6.5))
        fig.patch.set_facecolor("#0f0f12")
        ax.set_facecolor("#1a1a1f")
        ax.tick_params(colors="#aaa")
        for spine in ax.spines.values():
            spine.set_color("#333")

        colors = plt.cm.tab20(np.linspace(0, 1, self.optimal_k))
        for cid in range(self.optimal_k):
            mask = labels == cid
            ax.scatter(coords_2d[mask, 0], coords_2d[mask, 1], c=[colors[cid]], alpha=0.55, s=16,
                       label=f"C{cid}: {self.cluster_names[cid]}")

        ax.set_title("Movie Clusters - PCA 2D Projection", color="white", fontsize=13, pad=12)
        ax.set_xlabel(f"PC1 ({var_exp[0]*100:.1f}% variance)", color="#aaa")
        ax.set_ylabel(f"PC2 ({var_exp[1]*100:.1f}% variance)", color="#aaa")
        ax.legend(loc="upper right", framealpha=0.35, labelcolor="white",
                  facecolor="#1a1a1f", edgecolor="#333", fontsize=7.5, ncol=2)
        plt.tight_layout()
        pca_path = os.path.join(self.img_dir, "cluster_pca.png")
        plt.savefig(pca_path, dpi=120, bbox_inches="tight", facecolor="#0f0f12")
        plt.close()
        print(f"  PCA 2D projection saved to {pca_path}")

    # -------------------------------------------------------------------------
    # 3. SUPERVISED LEARNING: FEATURE MATRIX & REGRESSOR TRAINING
    # -------------------------------------------------------------------------
    def build_feature_matrix(self):
        """Constructs features combining user statistics, movie statistics, genres, and cluster IDs."""
        print("\n[3/5] Engineering features for Supervised Learning...")
        movie_stats = self.ratings_df.groupby("movieId")["rating"].agg(
            movie_avg_rating="mean",
            movie_rating_count="count"
        ).reset_index()

        user_stats = self.ratings_df.groupby("userId")["rating"].agg(
            user_avg_rating="mean"
        ).reset_index()

        merged = self.ratings_df.merge(self.movies_df[["movieId", "cluster"] + self.genre_list], on="movieId")
        merged = merged.merge(movie_stats, on="movieId")
        merged = merged.merge(user_stats, on="userId")

        self.feature_cols = self.genre_list + ["cluster", "movie_avg_rating", "movie_rating_count", "user_avg_rating"]
        self.feature_cols_no_cluster = self.genre_list + ["movie_avg_rating", "movie_rating_count", "user_avg_rating"]

        X = merged[self.feature_cols].values.astype(float)
        X_nc = merged[self.feature_cols_no_cluster].values.astype(float)
        y = merged["rating"].values.astype(float)

        print(f"  Dataset: {X.shape[0]:,} samples | Features with Cluster: {X.shape[1]} | Features without Cluster: {X_nc.shape[1]}")
        return X, X_nc, y, movie_stats

    def train_and_evaluate_supervised_models(self, X, X_nc, y):
        """Trains KNN and Random Forest Regressors, comparing With vs Without Cluster Feature."""
        print("\n[4/5] Training Supervised Models (KNN & Random Forest)...")

        # Deterministic split for fair side-by-side comparison
        indices = np.arange(len(y))
        np.random.seed(42)
        np.random.shuffle(indices)
        split_point = int(0.8 * len(indices))
        train_idx, test_idx = indices[:split_point], indices[split_point:]

        X_train, X_test = X[train_idx], X[test_idx]
        Xnc_train, Xnc_test = X_nc[train_idx], X_nc[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        # Feature Scaling for KNN
        self.scaler = StandardScaler()
        X_train_s = self.scaler.fit_transform(X_train)
        X_test_s = self.scaler.transform(X_test)

        scaler_nc = StandardScaler()
        Xnc_train_s = scaler_nc.fit_transform(Xnc_train)
        Xnc_test_s = scaler_nc.transform(Xnc_test)

        self.metrics = {}

        # 1. KNN Regressor WITH cluster
        print("  Training KNN Regressor (WITH cluster feature)...")
        self.knn = KNeighborsRegressor(n_neighbors=10, weights="distance", n_jobs=-1)
        self.knn.fit(X_train_s, y_train)
        self.metrics["knn_with_cluster"] = self._compute_metrics(self.knn, X_test_s, y_test, "KNN (With Cluster)")

        # 2. KNN Regressor WITHOUT cluster
        print("  Training KNN Regressor (WITHOUT cluster feature)...")
        knn_nc = KNeighborsRegressor(n_neighbors=10, weights="distance", n_jobs=-1)
        knn_nc.fit(Xnc_train_s, y_train)
        self.metrics["knn_no_cluster"] = self._compute_metrics(knn_nc, Xnc_test_s, y_test, "KNN (No Cluster)")

        # 3. Random Forest Regressor WITH cluster
        print("  Training Random Forest (WITH cluster feature)...")
        self.rf = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=-1)
        self.rf.fit(X_train, y_train)
        self.metrics["rf_with_cluster"] = self._compute_metrics(self.rf, X_test, y_test, "Random Forest (With Cluster)")

        # 4. Random Forest Regressor WITHOUT cluster
        print("  Training Random Forest (WITHOUT cluster feature)...")
        rf_nc = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=-1)
        rf_nc.fit(Xnc_train, y_train)
        self.metrics["rf_no_cluster"] = self._compute_metrics(rf_nc, Xnc_test, y_test, "Random Forest (No Cluster)")

        return self.metrics

    def _compute_metrics(self, model, X_test, y_test, label):
        preds = model.predict(X_test)
        rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
        mae = float(mean_absolute_error(y_test, preds))
        r2 = float(r2_score(y_test, preds))
        print(f"    {label:<32} -> RMSE: {rmse:.4f} | MAE: {mae:.4f} | R²: {r2:.4f}")
        return {"rmse": round(rmse, 4), "mae": round(mae, 4), "r2": round(r2, 4)}

    # -------------------------------------------------------------------------
    # 4. PERSISTENCE (SAVE / LOAD ARTIFACTS)
    # -------------------------------------------------------------------------
    def save(self, movie_stats_df):
        """Saves trained models, scalers, and metadata to disk via joblib."""
        print("\n[5/5] Saving model artifacts to models/ directory...")
        joblib.dump(self.kmeans, os.path.join(self.model_dir, "kmeans.pkl"))
        joblib.dump(self.knn, os.path.join(self.model_dir, "knn_regressor.pkl"))
        joblib.dump(self.rf, os.path.join(self.model_dir, "rf_regressor.pkl"))
        joblib.dump(self.scaler, os.path.join(self.model_dir, "scaler.pkl"))

        meta_df = self.movies_df[["movieId", "title_clean", "title", "year", "genres", "cluster"] + self.genre_list].copy()
        meta_df = meta_df.merge(movie_stats_df, on="movieId", how="left")
        meta_df["movie_avg_rating"] = meta_df["movie_avg_rating"].fillna(3.0)
        meta_df["movie_rating_count"] = meta_df["movie_rating_count"].fillna(0)

        metadata = {
            "genre_list": self.genre_list,
            "feature_cols": self.feature_cols,
            "optimal_k": self.optimal_k,
            "cluster_names": self.cluster_names,
            "cluster_info": self.cluster_info,
            "sil_info": self.sil_info,
            "metrics": self.metrics,
        }

        joblib.dump(metadata, os.path.join(self.model_dir, "metadata.pkl"))
        joblib.dump(meta_df, os.path.join(self.model_dir, "movie_meta.pkl"))
        self.movie_meta = meta_df
        self.is_trained = True
        print("  All artifacts saved successfully.")

    def load(self):
        """Loads all pre-trained models and metadata from disk."""
        self.kmeans = joblib.load(os.path.join(self.model_dir, "kmeans.pkl"))
        self.knn = joblib.load(os.path.join(self.model_dir, "knn_regressor.pkl"))
        self.rf = joblib.load(os.path.join(self.model_dir, "rf_regressor.pkl"))
        self.scaler = joblib.load(os.path.join(self.model_dir, "scaler.pkl"))

        metadata = joblib.load(os.path.join(self.model_dir, "metadata.pkl"))
        self.genre_list = metadata["genre_list"]
        self.feature_cols = metadata["feature_cols"]
        self.cluster_names = metadata["cluster_names"]
        self.cluster_info = metadata["cluster_info"]
        self.sil_info = metadata.get("sil_info", [])
        self.metrics = metadata["metrics"]
        self.movie_meta = joblib.load(os.path.join(self.model_dir, "movie_meta.pkl"))
        self.is_trained = True
        print("[INFO] CineStreamMLModel loaded successfully from disk.")

    # -------------------------------------------------------------------------
    # 5. INFERENCE & RECOMMENDATIONS
    # -------------------------------------------------------------------------
    def recommend(self, user_ratings: dict, top_n: int = 6, model: str = "rf"):
        """
        Predicts ratings for unrated movies for a given user.
        user_ratings: {movieId (int): rating (float)}
        Returns top_n recommended movies with predicted rating and cluster name.
        """
        if not self.is_trained:
            self.load()

        rated_ids = {int(k) for k in user_ratings.keys()}
        candidates = self.movie_meta[~self.movie_meta["movieId"].isin(rated_ids)].copy().reset_index(drop=True)

        if candidates.empty:
            return []

        user_avg = float(np.mean(list(user_ratings.values()))) if user_ratings else 3.0
        candidates["user_avg_rating"] = user_avg

        X_cand = candidates[self.feature_cols].fillna(0).values.astype(float)

        if model == "knn":
            X_scaled = self.scaler.transform(X_cand)
            preds = self.knn.predict(X_scaled)
        else:
            preds = self.rf.predict(X_cand)

        candidates["predicted_rating"] = preds
        top_candidates = candidates.nlargest(top_n, "predicted_rating")

        recommendations = []
        for _, row in top_candidates.iterrows():
            cid = int(row["cluster"])
            recommendations.append({
                "movieId": int(row["movieId"]),
                "title": str(row["title_clean"]),
                "year": int(row["year"]) if pd.notna(row.get("year")) else None,
                "genres": str(row["genres"]),
                "cluster": cid,
                "clusterName": self.cluster_names.get(cid, "General"),
                "predictedRating": round(float(row["predicted_rating"]), 2),
                "avgRating": round(float(row["movie_avg_rating"]), 2),
            })
        return recommendations


# -----------------------------------------------------------------------------
# MAIN CLI EXECUTION
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 70)
    print(" CINESTREAM MACHINE LEARNING PIPELINE")
    print("=" * 70)
    model = CineStreamMLModel()
    model.load_and_preprocess_data()
    model.train_unsupervised_kmeans(k_min=2, k_max=15)
    X, X_nc, y, movie_stats = model.build_feature_matrix()
    model.train_and_evaluate_supervised_models(X, X_nc, y)
    model.save(movie_stats)
    print("\n[SUCCESS] Model training and evaluation completed successfully!")
