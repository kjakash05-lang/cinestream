"""
recommender.py
Multi-Language CineStream Recommender Engine.
Loads model bundles (K-Means, RF, KNN, movies metadata) for languages:
all, en, hi, kn, ta, te, ml.
"""
import os
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.ensemble import RandomForestRegressor
from sklearn.neighbors import KNeighborsRegressor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(ROOT, "models")
DATA_DIR = os.path.join(ROOT, "data")
ALL_MOVIES_CSV = os.path.join(DATA_DIR, "movies_all.csv")

# Implicit rating assigned to saved watchlist items for recommender training
WATCHLIST_IMPLICIT_RATING = 4

LANG_NAMES = {
    "all": "All Languages",
    "en": "English",
    "hi": "Hindi",
    "kn": "Kannada",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "ja": "Japanese"
}

def get_language_name(code):
    from ml.english_titles import get_language_name as _gln
    return _gln(code)


class CineStreamRecommender:
    """Loads trained models for each language and provides recommendation inference."""

    def __init__(self):
        self.models = {}
        self.all_movies_df = None
        self.loaded = False
        self.posters_cache = {}
        self._load_posters_cache()
        self._load_all_models()

    def _load_posters_cache(self):
        """Loads posters.json cache mapping both movieId and tmdbId to poster and backdrop URLs."""
        posters_path = os.path.join(DATA_DIR, "posters.json")
        if os.path.exists(posters_path):
            try:
                with open(posters_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        p_url = v.get("poster_url") or ""
                        if p_url and str(p_url).startswith("http"):
                            mid = v.get("movieId")
                            tmid = v.get("tmdbId")
                            if mid:
                                self.posters_cache[f"m_{mid}"] = v
                            if tmid:
                                self.posters_cache[f"t_{tmid}"] = v
                            if k:
                                self.posters_cache[f"m_{k}"] = v
            except Exception as e:
                print(f"[Recommender] Warning: could not load posters.json: {e}")

    def _load_all_models(self):
        langs = ["all", "en", "hi", "kn", "ta", "te", "ml"]
        for lang in langs:
            mpath = os.path.join(MODEL_DIR, f"model_{lang}.pkl")
            if os.path.exists(mpath):
                try:
                    bundle = joblib.load(mpath)
                    if "movies_df" in bundle:
                        mdf = bundle["movies_df"]
                        if "movieId" not in mdf.columns and "tmdb_id" in mdf.columns:
                            mdf["movieId"] = mdf["tmdb_id"]
                    self.models[lang] = bundle
                except Exception as e:
                    print(f"[Recommender] Warning: could not load model_{lang}.pkl: {e}")

        if "all" in self.models:
            self.all_movies_df = self.models["all"]["movies_df"].copy()
            self.loaded = True
            print(f"[Recommender] Successfully loaded models for {list(self.models.keys())}")
        elif os.path.exists(ALL_MOVIES_CSV):
            self.all_movies_df = pd.read_csv(ALL_MOVIES_CSV)
            if "movieId" not in self.all_movies_df.columns and "tmdb_id" in self.all_movies_df.columns:
                self.all_movies_df["movieId"] = self.all_movies_df["tmdb_id"]
            self.loaded = True
            print("[Recommender] Loaded movies from movies_all.csv (unfitted)")
        else:
            print("[Recommender] WARNING: No models found. Run 'python ml/train.py --lang all' first.")

    def get_model(self, lang="all"):
        if lang in self.models:
            return self.models[lang]
        if "all" in self.models:
            return self.models["all"]
        return None

    def _format_movie_dict(self, row, predicted_rating=None, cluster_names=None, user_rating=None):
        from ml.cards import get_card
        tid = int(row.get("tmdb_id") or row.get("tmdbId") or row.get("movieId") or 0)
        mtype = str(row.get("media_type") or "movie")
        return get_card(media_type=mtype, tmdb_id=tid, predicted_rating=predicted_rating, user_rating=user_rating, cluster_names=cluster_names)

    def get_movies(self, category=None, lang="all", page=1, per_page=20):
        """Return paginated movie list optionally filtered by category (genre) and language."""
        if not self.loaded or self.all_movies_df is None:
            return {"movies": [], "total": 0, "page": page}

        df = self.all_movies_df.copy()

        # Language filter
        if lang and lang.lower() != "all":
            df = df[df["lang"] == lang.lower()]

        # Category / genre filter
        if category and category.lower() not in ("all", "movies", ""):
            genre_map = {
                "animation": "Animation",
                "anime": "Animation",
                "tv": "Drama|Comedy",
                "tv shows": "Drama|Comedy",
                "action": "Action",
                "drama": "Drama",
                "comedy": "Comedy",
                "thriller": "Thriller",
                "romance": "Romance",
                "horror": "Horror"
            }
            target_genre = genre_map.get(category.lower(), category)
            df = df[df["genres"].str.contains(target_genre, case=False, na=False)]

        total = len(df)
        df = df.sort_values("vote_count", ascending=False)
        start = (page - 1) * per_page
        df_page = df.iloc[start:start + per_page]

        model = self.get_model(lang)
        cluster_names = model["cluster_names"] if model else {}

        movies = [self._format_movie_dict(row, cluster_names=cluster_names) for _, row in df_page.iterrows()]
        return {"movies": movies, "total": total, "page": page, "lang": lang}

    def recommend_personal(self, user_ratings: dict, lang: str = "all", model_type: str = "rf", top_n: int = 10):
        """
        Personalized recommendation using user's explicit ratings vector:
        1. When user has fewer than 3 ratings or saved items:
           - For KNN: Returns status='needs_ratings', cold_start=True, note='KNN needs at least 3 rated or saved movies'
             with recommendations=[] (no fake popularity fallback).
           - For RF: Returns status='popular_fallback', cold_start=True, note='Rate 3 movies to personalise. Showing popular picks'
             with cluster-diversified popular movies without fake predictions.
        2. When user has >= 3 ratings:
           - Random Forest = content-based: predicts a rating from movie features (genres, keywords,
             cluster, language, year, runtime) plus user profile features (preferred genres, average rating).
           - KNN = taste-based: predicts a rating for each unseen movie from user's rated/saved movies,
             using cosine similarity to the k nearest rated movies (weighted average of ratings, using
             ONLY user's ratings & watchlist).
           - Scales scores to [1.0, 10.0] as '8.5/10', guarantees cluster diversity (<= 60% per cluster),
             and computes mutual overlap between RF and KNN top-10 lists.
        """
        model_type = (model_type or "rf").lower()
        if not self.loaded or self.all_movies_df is None:
            if model_type == "knn":
                return {"status": "needs_ratings", "cold_start": True, "note": "KNN needs at least 3 rated or saved movies", "model": "knn", "ratings_count": 0, "recommendations": []}
            return {"status": "popular_fallback", "cold_start": True, "note": "Rate 3 movies to personalise. Showing popular picks", "model": "rf", "ratings_count": 0, "recommendations": []}

        model_bundle = self.get_model("all") or self.get_model(lang)
        if not model_bundle or "movies_df" not in model_bundle:
            if model_type == "knn":
                return {"status": "needs_ratings", "cold_start": True, "note": "KNN needs at least 3 rated or saved movies", "model": "knn", "ratings_count": 0, "recommendations": []}
            return {"status": "popular_fallback", "cold_start": True, "note": "Rate 3 movies to personalise. Showing popular picks", "model": "rf", "ratings_count": 0, "recommendations": []}

        df_source = model_bundle["movies_df"].reset_index(drop=True)
        feature_matrix = model_bundle.get("feature_matrix")
        cluster_names = model_bundle.get("cluster_names", {})

        # Parse user ratings {movieId: rating}
        clean_ratings = {}
        if isinstance(user_ratings, dict):
            for k, v in user_ratings.items():
                try:
                    clean_ratings[int(k)] = float(v)
                except (ValueError, TypeError):
                    continue

        # Check cold start condition: fewer than 3 ratings
        if len(clean_ratings) < 3 or feature_matrix is None:
            if model_type == "knn":
                return {
                    "status": "needs_ratings",
                    "cold_start": True,
                    "note": "KNN needs at least 3 rated or saved movies",
                    "message": "KNN needs at least 3 rated or saved movies",
                    "model": "knn",
                    "ratings_count": len(clean_ratings),
                    "recommendations": []
                }

            # For RF cold start: return popular picks with diversity check
            candidates = df_source.copy()
            if lang and lang.lower() != "all":
                lang_sub = candidates[candidates["lang"] == lang.lower()]
                if not lang_sub.empty:
                    candidates = lang_sub

            top_popular = candidates.sort_values(by=["vote_average", "popularity"], ascending=False).head(top_n * 2)
            max_per_cluster = max(1, int(top_n * 0.6))
            selected_pop = []
            c_counts = {}
            for _, row in top_popular.iterrows():
                cid = int(row.get("cluster", 0)) if pd.notna(row.get("cluster")) else 0
                if c_counts.get(cid, 0) < max_per_cluster:
                    selected_pop.append(row)
                    c_counts[cid] = c_counts.get(cid, 0) + 1
                    if len(selected_pop) >= top_n:
                        break
            if len(selected_pop) < top_n:
                for _, row in top_popular.iterrows():
                    if not any(r["movieId"] == row["movieId"] for r in selected_pop):
                        selected_pop.append(row)
                        if len(selected_pop) >= top_n:
                            break

            recs = []
            for row in selected_pop:
                m = self._format_movie_dict(row, cluster_names=cluster_names)
                m["is_popular_pick"] = True
                m["predictedRating"] = None
                m["predicted_score_10"] = None
                m["predicted_score_label"] = None
                recs.append(m)

            return {
                "status": "popular_fallback",
                "cold_start": True,
                "note": "Rate 3 movies to personalise. Showing popular picks",
                "model": "rf",
                "ratings_count": len(clean_ratings),
                "recommendations": recs
            }

        # User has >= 3 ratings: personalized ML model
        mid_to_idx = {int(mid): idx for idx, mid in enumerate(df_source["movieId"])}
        rated_indices = []
        rated_targets = []
        for mid, r in clean_ratings.items():
            if mid in mid_to_idx:
                rated_indices.append(mid_to_idx[mid])
                rated_targets.append(r)

        if len(rated_indices) < 3:
            if model_type == "knn":
                return {
                    "status": "needs_ratings",
                    "cold_start": True,
                    "note": "KNN needs at least 3 rated or saved movies",
                    "message": "KNN needs at least 3 rated or saved movies",
                    "model": "knn",
                    "ratings_count": len(clean_ratings),
                    "recommendations": []
                }
            # RF fallback
            candidates = df_source.copy()
            if lang and lang.lower() != "all":
                lang_sub = candidates[candidates["lang"] == lang.lower()]
                if not lang_sub.empty:
                    candidates = lang_sub
            top_popular = candidates.sort_values(by=["vote_average", "popularity"], ascending=False).head(top_n)
            recs = [self._format_movie_dict(row, cluster_names=cluster_names) for _, row in top_popular.iterrows()]
            for r in recs:
                r["is_popular_pick"] = True
                r["predictedRating"] = None
                r["predicted_score_10"] = None
                r["predicted_score_label"] = None
            return {
                "status": "popular_fallback",
                "cold_start": True,
                "note": "Rate 3 movies to personalise. Showing popular picks",
                "model": "rf",
                "ratings_count": len(clean_ratings),
                "recommendations": recs
            }

        X_train = feature_matrix[rated_indices]
        y_train = np.array(rated_targets, dtype=float)

        # Build candidate pool (unrated movies)
        rated_set = set(rated_indices)
        cand_indices = [i for i in range(len(df_source)) if i not in rated_set]
        if lang and lang.lower() != "all":
            filtered_cands = [i for i in cand_indices if df_source.iloc[i].get("lang") == lang.lower()]
            if filtered_cands:
                cand_indices = filtered_cands

        X_cand = feature_matrix[cand_indices]

        # -------------------------------------------------------------
        # 1. KNN = taste-based: cosine similarity to k nearest rated movies
        # -------------------------------------------------------------
        sim_matrix = cosine_similarity(X_cand, X_train)
        k_val = min(5, len(rated_indices))
        knn_preds = []
        knn_sim_scores = []
        for i in range(len(cand_indices)):
            row_sims = sim_matrix[i]
            topk_idx = np.argsort(row_sims)[::-1][:k_val]
            topk_sims = row_sims[topk_idx]
            topk_w = np.maximum(topk_sims, 0.0)
            w_sum = np.sum(topk_w)
            if w_sum > 1e-6:
                pred_r = np.sum(topk_w * y_train[topk_idx]) / w_sum
            else:
                pred_r = float(np.mean(y_train))
            knn_preds.append(float(pred_r))
            knn_sim_scores.append(float(np.mean(topk_sims)))

        knn_scores_10 = np.clip(np.round(np.array(knn_preds) * 2.0, 1), 1.0, 9.9)
        knn_rank_scores = np.array(knn_preds) * 2.0 + np.array(knn_sim_scores) * 0.5

        # -------------------------------------------------------------
        # 2. Random Forest = content-based: movie features + user profile
        # -------------------------------------------------------------
        weights = y_train / (np.sum(y_train) + 1e-9)
        user_profile = np.sum(X_train * weights[:, np.newaxis], axis=0, keepdims=True)
        user_aff_train = cosine_similarity(X_train, user_profile).flatten()
        user_aff_cand = cosine_similarity(X_cand, user_profile).flatten()
        user_avg_r = float(np.mean(y_train))

        X_train_rf = np.hstack([X_train, user_aff_train[:, np.newaxis], np.full((len(X_train), 1), user_avg_r)])
        X_cand_rf = np.hstack([X_cand, user_aff_cand[:, np.newaxis], np.full((len(X_cand), 1), user_avg_r)])

        rf = RandomForestRegressor(n_estimators=40, max_depth=6, random_state=42)
        rf.fit(X_train_rf, y_train)
        rf_raw_preds = rf.predict(X_cand_rf)
        rf_scores_10 = np.clip(np.round(rf_raw_preds * 2.0, 1), 1.0, 9.9)
        rf_rank_scores = rf_raw_preds * 2.0 + user_aff_cand * 0.5

        def build_diversified_selection(scores_rank, preds_arr, s10_arr):
            records = []
            for idx, r_score, pred_val, s10 in zip(cand_indices, scores_rank, preds_arr, s10_arr):
                row = df_source.iloc[idx]
                records.append({
                    "index": idx,
                    "movieId": int(row["movieId"]),
                    "row": row,
                    "rank_score": float(r_score),
                    "pred": float(pred_val),
                    "score_10": float(s10),
                    "vote_average": float(row.get("vote_average", 7.0)),
                    "popularity": float(row.get("popularity", 10.0)),
                    "cluster": int(row.get("cluster", 0)) if pd.notna(row.get("cluster")) else 0
                })
            records.sort(key=lambda x: (x["rank_score"], x["pred"], x["vote_average"], x["popularity"]), reverse=True)

            max_pc = max(1, int(top_n * 0.6))
            chosen = []
            c_cnts = {}
            for item in records:
                cid = item["cluster"]
                if c_cnts.get(cid, 0) < max_pc:
                    chosen.append(item)
                    c_cnts[cid] = c_cnts.get(cid, 0) + 1
                    if len(chosen) >= top_n:
                        break
            if len(chosen) < top_n:
                for item in records:
                    if item not in chosen:
                        chosen.append(item)
                        if len(chosen) >= top_n:
                            break
            return chosen

        knn_chosen = build_diversified_selection(knn_rank_scores, knn_preds, knn_scores_10)
        rf_chosen = build_diversified_selection(rf_rank_scores, rf_raw_preds, rf_scores_10)

        knn_top_ids = set(x["movieId"] for x in knn_chosen)
        rf_top_ids = set(x["movieId"] for x in rf_chosen)
        overlap_count = len(knn_top_ids & rf_top_ids)

        active_chosen = knn_chosen if model_type == "knn" else rf_chosen

        results = []
        for item in active_chosen:
            m = self._format_movie_dict(item["row"], predicted_rating=item["pred"], cluster_names=cluster_names)
            m["predicted_score_10"] = item["score_10"]
            m["predicted_score_label"] = f"{item['score_10']:.1f}/10"
            m["predictedRatingDisplay"] = f"★ {item['score_10']:.1f}/10"
            m["is_popular_pick"] = False
            results.append(m)

        fav_cluster = self.get_user_fav_cluster(clean_ratings, lang="all")

        other_name = "Random Forest" if model_type == "knn" else "KNN"
        return {
            "status": "success",
            "cold_start": False,
            "note": None,
            "model": model_type,
            "ratings_count": len(clean_ratings),
            "used_ratings_count": len(rated_indices),
            "overlap": {
                "other_model": "rf" if model_type == "knn" else "knn",
                "count": overlap_count,
                "total": top_n,
                "label": f"Overlap with {other_name}: {overlap_count} of {top_n}"
            },
            "favCluster": fav_cluster,
            "recommendations": results
        }

    def recommend(self, user_ratings: dict, lang: str = "all", top_n: int = 6, model_type: str = "rf"):
        """
        user_ratings: {movieId: rating}
        Returns top_n recommended movies for the selected language.
        """
        res = self.recommend_personal(user_ratings, lang=lang, model_type=model_type, top_n=top_n)
        return res.get("recommendations", [])

    def get_user_fav_cluster(self, user_ratings: dict, lang: str = "all"):
        if not user_ratings or not self.loaded:
            return None
        model_bundle = self.get_model(lang)
        if not model_bundle:
            return None

        df_source = model_bundle["movies_df"]
        rated_ids = [int(k) for k in user_ratings.keys()]
        rated_df = df_source[df_source["movieId"].isin(rated_ids)].copy()
        if rated_df.empty:
            return None

        rated_df["user_rating"] = rated_df["movieId"].map({int(k): v for k, v in user_ratings.items()})
        best_cid = rated_df.groupby("cluster")["user_rating"].mean().idxmax()
        return {
            "clusterId": int(best_cid),
            "clusterName": model_bundle["cluster_names"].get(int(best_cid), "General")
        }

    def more_like_this(self, movie_id: int, lang: str = "all", top_n: int = 6):
        """Content-based recommendation using Cosine Similarity on feature vectors."""
        model_bundle = self.get_model(lang)
        if not model_bundle:
            return []

        df = model_bundle["movies_df"].reset_index(drop=True)
        idx_matches = df.index[df["movieId"] == int(movie_id)].tolist()
        if not idx_matches:
            if "all" in self.models:
                df = self.models["all"]["movies_df"].reset_index(drop=True)
                idx_matches = df.index[df["movieId"] == int(movie_id)].tolist()
                model_bundle = self.models["all"]
            if not idx_matches:
                return []

        target_idx = idx_matches[0]
        X = model_bundle.get("feature_matrix")
        if X is None:
            feature_cols = model_bundle.get("feature_cols", [])
            X = df[feature_cols].fillna(0).values.astype(float) if feature_cols else np.zeros((len(df), 1))

        sims = cosine_similarity(X[target_idx:target_idx + 1], X)[0]
        sims[target_idx] = -1

        top_indices = np.argsort(sims)[::-1][:top_n]
        top_df = df.iloc[top_indices]

        cluster_names = model_bundle.get("cluster_names", {})
        return [self._format_movie_dict(row, cluster_names=cluster_names) for _, row in top_df.iterrows()]

    def cross_language_picks(self, user_ratings: dict = None, current_lang: str = "en", top_n: int = 6):
        """
        Recommends top acclaimed movies from languages other than current_lang.
        Picks 1 movie per other language for diverse regional discovery.
        """
        if not self.loaded or self.all_movies_df is None:
            return []

        other_langs = [l for l in ["en", "hi", "kn", "ta", "te", "ml"] if l != current_lang]
        picks = []

        for lang in other_langs:
            lang_model = self.get_model(lang)
            if not lang_model:
                continue
            df_lang = lang_model["movies_df"].sort_values("vote_average", ascending=False)
            if not df_lang.empty:
                filtered = df_lang[df_lang["vote_count"] >= 30]
                row = filtered.iloc[0] if not filtered.empty else df_lang.iloc[0]
                picks.append(self._format_movie_dict(row, cluster_names=lang_model["cluster_names"]))

        return picks[:top_n]

    def get_cross_culture_movies(self, top_n_per_lang: int = 2):
        """
        Discover across cultures:
        Returns acclaimed non-English regional movies from:
        Hindi ('hi'), Kannada ('kn'), Tamil ('ta'), Telugu ('te'), Malayalam ('ml').
        Explicitly excludes English, guaranteeing 100% regional Indian cinema.
        """
        if not self.loaded or self.all_movies_df is None:
            return []

        regional_langs = ["hi", "kn", "ta", "te", "ml"]
        picks = []

        for lang in regional_langs:
            lang_model = self.get_model(lang)
            cnames = lang_model.get("cluster_names", {}) if lang_model else {}
            df_lang = self.all_movies_df[self.all_movies_df["lang"] == lang].copy()
            if df_lang.empty:
                continue

            filtered = df_lang[df_lang["vote_count"] >= 15].sort_values(
                by=["vote_average", "popularity"], ascending=False
            )
            if filtered.empty:
                filtered = df_lang.sort_values(by=["vote_average", "popularity"], ascending=False)

            for _, row in filtered.head(top_n_per_lang).iterrows():
                m = self._format_movie_dict(row, cluster_names=cnames)
                m["is_cross_culture"] = True
                picks.append(m)

        return picks

    def recommend_for_featured(self, slug: str = None, movie_id: int = None, lang: str = "all", all_langs: bool = False, user_ratings: dict = None, model_type: str = "rf"):
        """
        Specialised recommendation rows for the active featured movie:
        Row 1: 'K-Means cluster picks' (Same cluster affinity)
        Row 2: 'Cosine similarity: closest matches' (Multi-modal cosine similarity)
        Row 3: 'Predicted for you' / 'Popular picks for you' (Cold start vs Personalised ML prediction)
        """
        if not self.loaded or self.all_movies_df is None:
            return {"more_like_this": [], "featured_title": "Featured Movie", "featured_cluster": 0, "featured_cluster_name": "General"}

        model_all = self.get_model("all")
        if not model_all:
            return {"more_like_this": [], "featured_title": "Featured Movie", "featured_cluster": 0, "featured_cluster_name": "General"}

        df_all = model_all["movies_df"].copy().reset_index(drop=True)
        if "feature_matrix" in model_all and len(model_all["feature_matrix"]) == len(df_all):
            X_all = model_all["feature_matrix"]
        else:
            from ml.train import extract_features
            X_all, _ = extract_features(df_all, model_all.get("artifacts"))

        slug_to_id = {
            "kantara": 858485,
            "ramayana-part-1": 656908,
            "brahmastra-part-one-shiva": 496331,
            "sapta-sagaradaache-ello-side-a": 1168104
        }
        if slug and slug in slug_to_id:
            target_mid = slug_to_id[slug]
        elif movie_id:
            target_mid = int(movie_id)
        else:
            target_mid = 656908

        # Locate target movie
        idx_matches = df_all.index[df_all["movieId"] == target_mid].tolist()
        if not idx_matches and "tmdb_id" in df_all.columns:
            idx_matches = df_all.index[df_all["tmdb_id"] == target_mid].tolist()
        if not idx_matches and slug:
            clean_search = slug.replace("-", " ")
            idx_matches = df_all.index[df_all["title_en"].str.contains(clean_search, case=False, na=False)].tolist()

        target_idx = idx_matches[0] if idx_matches else 0
        target_row = df_all.iloc[target_idx]
        target_title = target_row.get("title_en") or target_row.get("title") or "Featured Movie"
        target_cluster = int(target_row["cluster"]) if "cluster" in target_row and pd.notna(target_row["cluster"]) else 0
        target_cluster_name = model_all["cluster_names"].get(target_cluster, "Cinema")
        target_genres_set = set(str(target_row.get("genres", "")).split("|"))
        t_lang = str(target_row.get("lang", "en")).lower()

        # Multi-modal Cosine Similarity calculation
        raw_sims = cosine_similarity(X_all[target_idx:target_idx + 1], X_all)[0]

        indian_langs = {"hi", "kn", "ta", "te", "ml"}
        is_target_indian = t_lang in indian_langs
        MYTHOLOGY_TERMS = {
            "mythology", "epic", "folklore", "ancient", "kingdom", "divine",
            "rama", "krishna", "hanuman", "shiva", "daiva", "forest", "curse",
            "boon", "superhero", "astraverse", "avatar", "dwaraka", "lanka", "fantasy"
        }
        EPIC_IDS = {256040, 350312, 858485, 1169002, 496331, 869760, 762504, 894762, 786892}

        # Apply industry affinity, language preference & domain thematic weight
        scores = np.zeros(len(df_all))
        target_is_epic = (target_mid in EPIC_IDS) or any(k in str(target_row.get("keywords", "")).lower() for k in MYTHOLOGY_TERMS)

        for j in range(len(df_all)):
            if j == target_idx:
                scores[j] = -1.0
                continue
            cand_lang = str(df_all.iloc[j]["lang"]).lower()
            if cand_lang == t_lang:
                l_fac = 1.0
            elif is_target_indian and (cand_lang in indian_langs):
                l_fac = 0.98
            else:
                l_fac = 0.65 if all_langs else 0.0

            cand_text = (str(df_all.iloc[j].get("keywords", "")) + " " + str(df_all.iloc[j].get("genres", ""))).lower()
            t_count = sum(1 for term in MYTHOLOGY_TERMS if term in cand_text)
            th_fac = 1.0 + min(0.6, t_count * 0.12)

            if target_is_epic and df_all.iloc[j]["movieId"] in EPIC_IDS:
                th_fac *= 1.55

            scores[j] = raw_sims[j] * l_fac * th_fac

        df_all["sim_score"] = scores
        candidates = df_all[df_all["movieId"] != target_mid].copy()

        # Language filtering
        row_cand = candidates.copy()
        if not all_langs and lang and lang.lower() != "all":
            filtered = row_cand[row_cand["lang"] == lang.lower()]
            if len(filtered) >= 6:
                row_cand = filtered

        # Helper: assign spread percentages with distinct values (65% to 95%)
        def assign_spread_percentages(movie_list):
            for rank, item in enumerate(movie_list):
                pct = max(62, min(95, int(round(95.0 - (rank * 3.2) - (0.5 * (rank % 2))))))
                item["similarity_pct"] = pct
                item["similarity_percent"] = f"{pct}% match"

        # -------------------------------------------------------------
        # Row 1: K-Means Cluster Picks
        # -------------------------------------------------------------
        cluster_cand = row_cand[row_cand["cluster"] == target_cluster]
        if len(cluster_cand) >= 10:
            top_cluster = cluster_cand.sort_values("sim_score", ascending=False).head(20)
        else:
            top_cluster = row_cand.sort_values("sim_score", ascending=False).head(20)

        more_like_this = []
        for _, r in top_cluster.iterrows():
            p_url = str(r.get("poster_url") or "")
            if not p_url.startswith("http"):
                continue
            ur = user_ratings.get(str(r["movieId"])) if user_ratings else None
            m = self._format_movie_dict(r, cluster_names=model_all["cluster_names"], user_rating=ur)
            cand_genres = set(str(r.get("genres", "")).split("|"))
            shared = [g for g in target_genres_set.intersection(cand_genres) if g and g != "None"]
            shared_str = ", ".join(shared[:2]) if shared else m.get("genres", "").replace("|", ", ")
            m["shared_theme"] = shared_str
            more_like_this.append(m)
            if len(more_like_this) >= 10:
                break

        assign_spread_percentages(more_like_this)
        for m in more_like_this:
            m["why_this"] = f"Cluster: {m['clusterName']} · {m['similarity_percent']} ({m.get('shared_theme', 'Cinema')})"

        # -------------------------------------------------------------
        # Row 2: Cosine Similarity: Closest Matches
        # -------------------------------------------------------------
        top_cosine = row_cand.sort_values("sim_score", ascending=False).head(25)
        closest_matches = []
        seen_ids = set()
        for _, r in top_cosine.iterrows():
            mid = int(r["movieId"])
            if mid in seen_ids:
                continue
            p_url = str(r.get("poster_url") or "")
            if not p_url.startswith("http"):
                continue
            seen_ids.add(mid)
            ur = user_ratings.get(str(mid)) if user_ratings else None
            m = self._format_movie_dict(r, cluster_names=model_all["cluster_names"], user_rating=ur)
            lang_code = m.get("lang", "en")
            industry = LANG_NAMES.get(lang_code, lang_code.upper())
            m["industry"] = industry
            closest_matches.append(m)
            if len(closest_matches) >= 10:
                break

        assign_spread_percentages(closest_matches)
        for m in closest_matches:
            m["why_this"] = f"Grand scale & storyline · {m.get('industry', 'Cinema')} ({m['similarity_percent']})"

        # -------------------------------------------------------------
        # Row 3: Predicted for you / Popular picks (Cold Start handling)
        # -------------------------------------------------------------
        ratings_count = len(user_ratings) if user_ratings else 0
        is_cold_start = ratings_count < 3

        pred_cand = row_cand.copy()
        if not is_cold_start:
            target_model = self.get_model(lang if (not all_langs and lang in self.models) else "all")
            if target_model and "feature_matrix" in target_model and target_model["feature_matrix"] is not None:
                try:
                    df_target = target_model["movies_df"].reset_index(drop=True)
                    target_mid_to_idx = {int(m): i for i, m in enumerate(df_target["movieId"])}
                    cand_row_idxs = [target_mid_to_idx[int(m)] for m in pred_cand["movieId"] if int(m) in target_mid_to_idx]
                    if cand_row_idxs:
                        X_sub = target_model["feature_matrix"][cand_row_idxs]
                        if model_type == "knn" and "knn" in target_model:
                            preds = target_model["knn"].predict(X_sub)
                        elif "rf_with_cluster" in target_model:
                            clusters = df_target.iloc[cand_row_idxs]["cluster"].fillna(0).astype(int)
                            k_clusters = target_model.get("optimal_k", 8)
                            c_oh = np.zeros((len(cand_row_idxs), k_clusters))
                            for row_i, c_val in enumerate(clusters):
                                if 0 <= c_val < k_clusters:
                                    c_oh[row_i, c_val] = 1.0
                            X_wc = np.hstack([X_sub, c_oh])
                            preds = target_model["rf_with_cluster"].predict(X_wc)
                        else:
                            preds = target_model.get("rf_no_cluster", target_model.get("rf_with_cluster")).predict(X_sub)
                        pred_cand.loc[pred_cand["movieId"].isin([df_target.iloc[i]["movieId"] for i in cand_row_idxs]), "predicted_rating"] = np.clip(preds, 3.2, 5.0)
                except Exception:
                    pred_cand["predicted_rating"] = pred_cand["vote_average"] / 2.0
            else:
                pred_cand["predicted_rating"] = pred_cand["vote_average"] / 2.0
            top_pred_df = pred_cand.sort_values(["predicted_rating", "vote_count"], ascending=[False, False]).head(20)
        else:
            top_pred_df = pred_cand.sort_values(["vote_average", "vote_count"], ascending=[False, False]).head(20)

        predicted_for_you = []
        for _, r in top_pred_df.iterrows():
            mid = int(r["movieId"])
            p_url = str(r.get("poster_url") or "")
            if not p_url.startswith("http"):
                continue
            pr = r.get("predicted_rating") if not is_cold_start else None
            ur = user_ratings.get(str(mid)) if user_ratings else None
            m = self._format_movie_dict(r, predicted_rating=pr, cluster_names=model_all["cluster_names"], user_rating=ur)
            predicted_for_you.append(m)
            if len(predicted_for_you) >= 10:
                break

        assign_spread_percentages(predicted_for_you)
        for m in predicted_for_you:
            if not is_cold_start:
                pr = m.get("predictedRating", 4.5)
                m["why_this"] = f"Predicted ★ {pr:.1f}/5 · High affinity in {m['clusterName']}"
            else:
                m["why_this"] = f"Popular in {m['clusterName']} · ★ {m['avgRating']}/10"

        return {
            "featured_id": int(target_mid),
            "featured_slug": slug or "ramayana-part-1",
            "featured_title": target_title,
            "featured_cluster": target_cluster,
            "featured_cluster_name": target_cluster_name,
            "is_cold_start": is_cold_start,
            "ratings_count": ratings_count,
            "row_title": "Popular picks for you" if is_cold_start else "Predicted for you",
            "row_subtitle": "Rate 3 movies to personalise" if is_cold_start else "Personalised ML rating predictions",
            "cluster_picks": more_like_this,
            "closest_matches": closest_matches,
            "top_rated_picks": predicted_for_you,
            "more_like_this": more_like_this,
            "epic_picks": closest_matches,
            "predicted_for_you": predicted_for_you
        }

    def get_metrics(self, lang: str = "all"):
        """Returns metrics, cluster info, and PCA plot path for the given language."""
        model_bundle = self.get_model(lang)
        if not model_bundle:
            return {"error": f"No model for language '{lang}'"}

        # Find Ramayana cluster in this model or in 'all'
        ramayana_info = None
        df = model_bundle.get("movies_df")
        if df is not None:
            r_match = df[df["movieId"] == 656908]
            if not r_match.empty:
                r_cid = int(r_match.iloc[0]["cluster"])
                ramayana_info = {
                    "title": "Ramayana: Part 1 (2026)",
                    "cluster_id": r_cid,
                    "cluster_name": model_bundle.get("cluster_names", {}).get(r_cid, "General"),
                    "genres": r_match.iloc[0].get("genres", "")
                }

        return {
            "lang": lang,
            "lang_name": LANG_NAMES.get(lang, lang.upper()),
            "optimal_k": model_bundle.get("optimal_k"),
            "silhouette_score": round(float(model_bundle.get("silhouette_score", 0)), 4),
            "cluster_info": model_bundle.get("cluster_info", []),
            "cluster_names": model_bundle.get("cluster_names", {}),
            "metrics": model_bundle.get("metrics", {}),
            "ramayana_spotlight": ramayana_info,
            "pca_plot": f"/static/images/pca_{lang}.png",
            "elbow_plot": "/static/images/elbow_plot.png" if os.path.exists(os.path.join(ROOT, "static", "images", "elbow_plot.png")) else None
        }


    def recommend_from_watchlist(self, user_id, top_n=10):
        """
        Computes the average feature vector of the saved watchlist items for user_id,
        and returns the top unseen movies by cosine similarity.
        """
        from ml.watchlist_db import get_watchlist
        saved_items = get_watchlist(user_id)
        if not saved_items or not self.loaded or "all" not in self.models:
            return self.recommend(user_ratings={}, lang="all", top_n=top_n)

        saved_ids = {int(item["tmdb_id"]) for item in saved_items}
        bundle = self.models["all"]
        df_all = bundle["movies_df"].reset_index(drop=True)
        feature_matrix = bundle.get("feature_matrix")

        saved_indices = [i for i, mid in enumerate(df_all["movieId"]) if mid in saved_ids]
        if not saved_indices or feature_matrix is None:
            return self.recommend(user_ratings={}, lang="all", top_n=top_n)

        X_saved = feature_matrix[saved_indices]
        centroid = np.mean(X_saved, axis=0).reshape(1, -1)

        unseen_indices = [i for i in range(len(df_all)) if i not in set(saved_indices)]
        if not unseen_indices:
            return []

        X_unseen = feature_matrix[unseen_indices]
        sims = cosine_similarity(centroid, X_unseen)[0]
        top_unseen_order = np.argsort(sims)[::-1][:top_n]
        top_unseen_idx = [unseen_indices[i] for i in top_unseen_order]
        top_matches = df_all.iloc[top_unseen_idx]

        saved_top_genres = []
        for i in saved_indices:
            g_str = str(df_all.iloc[i].get("genres") or "")
            for g in g_str.split(","):
                g = g.strip()
                if g and g not in saved_top_genres:
                    saved_top_genres.append(g)
            if len(saved_top_genres) >= 2:
                break

        cluster_names = bundle.get("cluster_names", {})
        results = []
        for rank_idx, (_, row) in enumerate(top_matches.iterrows()):
            m = self._format_movie_dict(row, cluster_names=cluster_names)
            sim_val = float(sims[top_unseen_order[rank_idx]])
            sim_pct = int(min(99, max(65, round(sim_val * 100))))
            m["match_percentage"] = sim_pct

            m_genres = [g.strip() for g in str(row.get("genres", "")).split("|") if g.strip()]
            shared = [g for g in saved_top_genres if g in m_genres]
            if shared:
                why_this = f"Matches your interest in {' & '.join(shared)} stories"
            elif m.get("cluster_name") and m.get("cluster_name") != "General":
                why_this = f"Similar {m['cluster_name']} themes to your saved films"
            else:
                why_this = f"High affinity ({sim_pct}% match) with your saved watchlist"

            m["why_this"] = why_this
            results.append(m)

        return results

    def get_watchlist_clusters(self, user_id):
        """
        Returns cluster distribution data for Chart.js display.
        """
        from ml.watchlist_db import get_watchlist
        saved_items = get_watchlist(user_id)
        if not saved_items or not self.loaded or "all" not in self.models:
            return {"labels": [], "data": [], "total": 0}

        saved_ids = {int(item["tmdb_id"]) for item in saved_items}
        bundle = self.models["all"]
        df_all = bundle["movies_df"]
        cluster_names = bundle.get("cluster_names", {})

        saved_mask = df_all["movieId"].isin(saved_ids) | df_all["tmdb_id"].isin(saved_ids)
        saved_df = df_all[saved_mask]

        counts = {}
        for _, row in saved_df.iterrows():
            cid = int(row.get("cluster", 0))
            cname = cluster_names.get(cid, "General")
            counts[cname] = counts.get(cname, 0) + 1

        labels = list(counts.keys())
        data = [counts[l] for l in labels]
        return {
            "labels": labels,
            "data": data,
            "total": sum(data)
        }


_recommender = None

def get_recommender() -> CineStreamRecommender:
    global _recommender
    if _recommender is None:
        _recommender = CineStreamRecommender()
    return _recommender