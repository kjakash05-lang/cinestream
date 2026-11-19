"""
hybrid.py
Hybrid Recommender Engine blending Content-Based (Random Forest / KNN multi-modal)
and Collaborative Filtering (Item-KNN + SVD) with weights from ml/config.py.
Includes automatic fallback to content-only when collaborative data is absent.
"""
import os
import numpy as np
import pandas as pd
import ml.config as cfg
from ml.collaborative import CollaborativeRecommender

class HybridRecommender:
    def __init__(self, content_rec=None, collab_rec=None):
        self.content_rec = content_rec
        self.collab_rec = collab_rec or CollaborativeRecommender()
        self.w_content = getattr(cfg, "HYBRID_CONTENT_WEIGHT", 0.55)
        self.w_collab = getattr(cfg, "HYBRID_COLLAB_WEIGHT", 0.45)

    def set_content_recommender(self, content_rec):
        self.content_rec = content_rec

    def recommend(self, user_ratings: dict, lang: str = "all", top_n: int = 10, model_type: str = "rf"):
        """
        Produces blended hybrid recommendations for user_ratings.
        Falls back to content-only if collaborative rating is unavailable.
        """
        if not self.content_rec:
            from ml.recommender import CineStreamRecommender
            self.content_rec = CineStreamRecommender()

        # Get base content candidates
        content_results = self.content_rec.recommend(user_ratings, lang=lang, top_n=top_n * 2, model_type=model_type)
        if not content_results:
            data = self.content_rec.get_movies(category="all", lang=lang, page=1, per_page=top_n)
            content_results = data.get("movies", [])

        hybrid_list = []
        for m in content_results:
            mid = m.get("movieId") or m.get("tmdbId") or m.get("tmdb_id")
            content_pred = float(m.get("predictedRating") or (m.get("avgRating", 7.0) / 2.0))
            collab_pred = self.collab_rec.predict_user_rating(user_ratings, mid) if self.collab_rec else None

            if collab_pred is not None:
                final_score = (self.w_content * content_pred) + (self.w_collab * collab_pred)
                mode = f"Hybrid ({int(self.w_content*100)}% Content + {int(self.w_collab*100)}% Collab)"
            else:
                final_score = content_pred
                mode = "Content-Based (Cold-start fallback)"

            final_score = round(float(np.clip(final_score, 1.0, 5.0)), 2)
            m_copy = dict(m)
            m_copy["hybrid_score"] = final_score
            m_copy["predictedRating"] = final_score
            m_copy["predicted_rating"] = final_score
            m_copy["content_score"] = round(content_pred, 2)
            m_copy["collab_score"] = round(collab_pred, 2) if collab_pred is not None else None
            m_copy["hybrid_mode"] = mode
            m_copy["why_this"] = f"{mode} · Predicted ★ {final_score:.1f}/5 ({m_copy.get('clusterName', 'Cinema')})"
            hybrid_list.append(m_copy)

        hybrid_list.sort(key=lambda x: x["hybrid_score"], reverse=True)
        return hybrid_list[:top_n]
