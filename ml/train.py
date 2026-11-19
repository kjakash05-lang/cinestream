"""
train.py - CineStream Multi-Modal ML Training Pipeline
Features:
1. Multi-modal rich feature engineering:
   - Multi-hot genres (weighted by FEATURE_WEIGHT_GENRES)
   - TF-IDF keywords with domain boosting (weighted by FEATURE_WEIGHT_KEYWORDS)
   - Top cast & director binary vectorization (weighted by FEATURE_WEIGHT_CAST, FEATURE_WEIGHT_DIRECTOR)
   - Categorical original language, decade, and runtime bands
   - TF-IDF overviews reduced via TruncatedSVD(50 dims) (weighted by FEATURE_WEIGHT_OVERVIEW_SVD)
2. Unsupervised K-Means:
   - Silhouette search across k=6..20 to discover optimal cluster count
   - Cluster naming from top genres + distinct top keywords
   - 2D PCA projection plot saved to static/images/pca_{lang}.png
3. Supervised Random Forest & KNN:
   - Evaluates Random Forest (WITH vs WITHOUT cluster)
   - Fits KNN regressor for user rating predictions
4. Per-language bundles: all, en, hi, kn, ta, te, ml
"""
import os
import sys
import argparse
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.decomposition import TruncatedSVD, PCA
from sklearn.preprocessing import StandardScaler, normalize
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor
from sklearn.neighbors import KNeighborsRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score, silhouette_score
import joblib

warnings.filterwarnings("ignore")

# Safe UTF-8 console output for Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
MODEL_DIR = os.path.join(ROOT_DIR, "models")
IMG_DIR = os.path.join(ROOT_DIR, "static", "images")
MOVIES_CSV = os.path.join(DATA_DIR, "movies_all.csv")

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(IMG_DIR, exist_ok=True)

sys.path.insert(0, ROOT_DIR)
import ml.config as cfg

LANG_NAMES = {
    "all": "All Languages",
    "en": "English (Hollywood)",
    "hi": "Hindi (Bollywood)",
    "kn": "Kannada (Sandalwood)",
    "ta": "Tamil (Kollywood)",
    "te": "Telugu (Tollywood)",
    "ml": "Malayalam (Mollywood)"
}

MYTHOLOGY_TERMS = {
    "mythology", "epic", "folklore", "ancient", "kingdom", "divine",
    "rama", "krishna", "hanuman", "shiva", "daiva", "forest", "curse",
    "boon", "superhero", "astraverse", "avatar", "dwaraka", "lanka"
}

def load_dataset(lang="all"):
    if not os.path.exists(MOVIES_CSV):
        raise FileNotFoundError(f"{MOVIES_CSV} not found! Run python ml/enrich_metadata.py first.")

    df = pd.read_csv(MOVIES_CSV)
    if lang != "all":
        df = df[df["lang"] == lang].copy()
    else:
        df = df.copy()

    df = df.dropna(subset=["genres", "vote_average", "year"]).reset_index(drop=True)
    if "movieId" not in df.columns and "tmdb_id" in df.columns:
        df["movieId"] = df["tmdb_id"]
    return df

def extract_features(df, artifacts=None):
    """
    Extracts rich multi-modal feature blocks, scales and weights them according to ml/config.py.
    """
    is_train = artifacts is None
    if is_train:
        artifacts = {}

    N = len(df)

    # 1. Genres
    if is_train:
        all_genres = sorted(list(set(
            g.strip() for g_str in df["genres"].dropna()
            for g in str(g_str).split("|") if g.strip() and g.strip().lower() != "none"
        )))
        artifacts["all_genres"] = all_genres
    else:
        all_genres = artifacts["all_genres"]

    genre_mat = np.zeros((N, len(all_genres)))
    for i, g in enumerate(all_genres):
        genre_mat[:, i] = df["genres"].str.contains(g, regex=False, na=False).astype(float)
    genre_mat *= cfg.FEATURE_WEIGHT_GENRES

    # 2. Keywords
    if is_train:
        try:
            tfidf_kw = TfidfVectorizer(max_features=160, token_pattern=r"(?u)\b[\w-]+\b")
            kw_mat_raw = tfidf_kw.fit_transform(df["keywords"].fillna("")).toarray().astype(float)
            artifacts["tfidf_kw"] = tfidf_kw
        except ValueError:
            tfidf_kw = None
            kw_mat_raw = np.zeros((N, 1), dtype=float)
            artifacts["tfidf_kw"] = None
    else:
        tfidf_kw = artifacts.get("tfidf_kw")
        if tfidf_kw is not None:
            kw_mat_raw = tfidf_kw.transform(df["keywords"].fillna("")).toarray().astype(float)
        else:
            kw_mat_raw = np.zeros((N, 1), dtype=float)

    # Apply domain term boosting
    kw_mat = kw_mat_raw.copy()
    if tfidf_kw is not None:
        kw_names = tfidf_kw.get_feature_names_out()
        for idx, name in enumerate(kw_names):
            if name in MYTHOLOGY_TERMS:
                kw_mat[:, idx] *= 3.5
    kw_mat *= float(cfg.FEATURE_WEIGHT_KEYWORDS)

    # 3. Cast
    if is_train:
        try:
            vec_cast = CountVectorizer(max_features=80, binary=True)
            cast_mat = vec_cast.fit_transform(df["cast"].fillna("")).toarray().astype(float)
            artifacts["vec_cast"] = vec_cast
        except ValueError:
            artifacts["vec_cast"] = None
            cast_mat = np.zeros((N, 1), dtype=float)
    else:
        vec_cast = artifacts.get("vec_cast")
        if vec_cast is not None:
            cast_mat = vec_cast.transform(df["cast"].fillna("")).toarray().astype(float)
        else:
            cast_mat = np.zeros((N, 1), dtype=float)
    cast_mat *= float(cfg.FEATURE_WEIGHT_CAST)

    # 4. Director
    if is_train:
        try:
            vec_dir = CountVectorizer(max_features=40, binary=True)
            dir_mat = vec_dir.fit_transform(df["director"].fillna("")).toarray().astype(float)
            artifacts["vec_dir"] = vec_dir
        except ValueError:
            artifacts["vec_dir"] = None
            dir_mat = np.zeros((N, 1), dtype=float)
    else:
        vec_dir = artifacts.get("vec_dir")
        if vec_dir is not None:
            dir_mat = vec_dir.transform(df["director"].fillna("")).toarray().astype(float)
        else:
            dir_mat = np.zeros((N, 1), dtype=float)
    dir_mat *= float(cfg.FEATURE_WEIGHT_DIRECTOR)

    # 5. Language
    if is_train:
        langs = sorted(df["lang"].dropna().unique().tolist())
        artifacts["langs"] = langs
    else:
        langs = artifacts["langs"]

    lang_mat = np.zeros((N, len(langs)))
    for i, l in enumerate(langs):
        lang_mat[:, i] = (df["lang"] == l).astype(float)
    lang_mat *= float(cfg.FEATURE_WEIGHT_LANGUAGE)

    # 6. Decade
    year = pd.to_numeric(df["year"], errors="coerce").fillna(2010).values
    dec_mat = np.zeros((N, 5))
    dec_mat[:, 0] = (year >= 2020).astype(float)
    dec_mat[:, 1] = ((year >= 2010) & (year < 2020)).astype(float)
    dec_mat[:, 2] = ((year >= 2000) & (year < 2010)).astype(float)
    dec_mat[:, 3] = ((year >= 1990) & (year < 2000)).astype(float)
    dec_mat[:, 4] = (year < 1990).astype(float)
    dec_mat *= float(cfg.FEATURE_WEIGHT_DECADE)

    # 7. Runtime band
    rt = pd.to_numeric(df["runtime"], errors="coerce").fillna(120).values
    rt_mat = np.zeros((N, 4))
    rt_mat[:, 0] = (rt < 90).astype(float)
    rt_mat[:, 1] = ((rt >= 90) & (rt <= 120)).astype(float)
    rt_mat[:, 2] = ((rt > 120) & (rt <= 150)).astype(float)
    rt_mat[:, 3] = (rt > 150).astype(float)
    rt_mat *= float(cfg.FEATURE_WEIGHT_RUNTIME)

    # 8. Overview TF-IDF with TruncatedSVD(50)
    if is_train:
        try:
            tfidf_ov = TfidfVectorizer(max_features=3000, stop_words="english")
            ov_tfidf = tfidf_ov.fit_transform(df["overview"].fillna(""))
            n_features = ov_tfidf.shape[1]
            n_comp = min(cfg.SVD_COMPONENTS, max(2, min(N - 1, n_features - 1)))
            if n_comp >= 2 and n_features > n_comp:
                svd_ov = TruncatedSVD(n_components=n_comp, random_state=42)
                ov_svd_raw = svd_ov.fit_transform(ov_tfidf)
                scaler_ov = StandardScaler()
                ov_svd = scaler_ov.fit_transform(ov_svd_raw)
                artifacts["tfidf_ov"] = tfidf_ov
                artifacts["svd_ov"] = svd_ov
                artifacts["scaler_ov"] = scaler_ov
            else:
                ov_svd = np.zeros((N, 1), dtype=float)
                artifacts["tfidf_ov"] = None
                artifacts["svd_ov"] = None
                artifacts["scaler_ov"] = None
        except ValueError:
            ov_svd = np.zeros((N, 1), dtype=float)
            artifacts["tfidf_ov"] = None
            artifacts["svd_ov"] = None
            artifacts["scaler_ov"] = None
    else:
        tfidf_ov = artifacts.get("tfidf_ov")
        svd_ov = artifacts.get("svd_ov")
        scaler_ov = artifacts.get("scaler_ov")
        if tfidf_ov is not None and svd_ov is not None and scaler_ov is not None:
            ov_tfidf = tfidf_ov.transform(df["overview"].fillna(""))
            ov_svd_raw = svd_ov.transform(ov_tfidf)
            ov_svd = scaler_ov.transform(ov_svd_raw)
        else:
            ov_svd = np.zeros((N, 1), dtype=float)

    ov_svd *= float(cfg.FEATURE_WEIGHT_OVERVIEW_SVD)

    # Combine all blocks
    X_full = np.hstack([genre_mat, kw_mat, cast_mat, dir_mat, lang_mat, dec_mat, rt_mat, ov_svd])
    X_norm = normalize(X_full, norm="l2")

    return X_norm, artifacts

def train_kmeans(df, X_norm, lang="all", k_min=cfg.KMEANS_K_MIN, k_max=cfg.KMEANS_K_MAX):
    """
    Fits K-Means searching across k=6..20 with Silhouette Score.
    Generates rich, distinct cluster names combining top genres and distinctive keywords.
    """
    n_samples = len(df)
    eff_k_min = max(3, min(k_min, n_samples // 10))
    eff_k_max = min(k_max, max(eff_k_min + 1, n_samples // 6))
    k_range = list(range(eff_k_min, eff_k_max + 1))
    if len(k_range) < 2:
        k_range = [3, 4]

    inertias = []
    sil_scores = []
    sample_size = min(1200, n_samples)

    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_norm)
        inertias.append(km.inertia_)
        sil = silhouette_score(X_norm, labels, sample_size=sample_size)
        sil_scores.append(sil)

    best_idx = int(np.argmax(sil_scores))
    optimal_k = k_range[best_idx]
    best_sil = sil_scores[best_idx]

    # Final KMeans fit
    kmeans = KMeans(n_clusters=optimal_k, random_state=42, n_init=10)
    df["cluster"] = kmeans.fit_predict(X_norm)

    # Distinct cluster naming: top 2 genres + top distinctive keywords
    cluster_names = {}
    cluster_info = []

    for cid in range(optimal_k):
        mask = df["cluster"] == cid
        sub_df = df[mask]

        # Top genres
        genre_counts = {}
        for g_str in sub_df["genres"].dropna():
            for g in str(g_str).split("|"):
                g = g.strip()
                if g and g.lower() != "none":
                    genre_counts[g] = genre_counts.get(g, 0) + 1
        sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)
        top_genres = [g[0] for g in sorted_genres[:2]]
        genre_label = " & ".join(top_genres) if top_genres else "Cinema"

        # Distinct keywords
        kw_counts = {}
        for k_str in sub_df["keywords"].dropna():
            for kw in str(k_str).split("|"):
                kw = kw.strip().title()
                if kw and len(kw) > 2 and kw not in genre_label:
                    kw_counts[kw] = kw_counts.get(kw, 0) + 1
        sorted_kws = sorted(kw_counts.items(), key=lambda x: x[1], reverse=True)
        top_kws = [k[0] for k in sorted_kws[:2]]
        kw_label = f" ({', '.join(top_kws)})" if top_kws else ""

        cname = f"{genre_label}{kw_label}"
        cluster_names[cid] = cname
        cluster_info.append({
            "id": cid,
            "name": cname,
            "count": int(mask.sum()),
            "top_genres": [g[0] for g in sorted_genres[:4]]
        })

    # Save PCA plot
    pca = PCA(n_components=2, random_state=42)
    coords_2d = pca.fit_transform(X_norm)
    var_exp = pca.explained_variance_ratio_

    fig, ax = plt.subplots(figsize=(9, 6))
    fig.patch.set_facecolor("#0f0f12")
    ax.set_facecolor("#1a1a1f")
    ax.tick_params(colors="#aaa")
    for spine in ax.spines.values():
        spine.set_color("#333")

    colors = plt.cm.tab20(np.linspace(0, 1, optimal_k))
    for cid in range(optimal_k):
        mask = df["cluster"].values == cid
        ax.scatter(coords_2d[mask, 0], coords_2d[mask, 1], c=[colors[cid]], alpha=0.6, s=18,
                   label=f"C{cid}: {cluster_names[cid][:24]}")

    title_label = LANG_NAMES.get(lang, lang.upper())
    ax.set_title(f"{title_label} - Movie Clusters (PCA 2D)", color="white", fontsize=12, pad=10)
    ax.set_xlabel(f"PC1 ({var_exp[0]*100:.1f}% var)", color="#aaa")
    ax.set_ylabel(f"PC2 ({var_exp[1]*100:.1f}% var)", color="#aaa")
    ax.legend(loc="upper right", framealpha=0.35, labelcolor="white", facecolor="#1a1a1f",
              edgecolor="#333", fontsize=7.5, ncol=2)
    plt.tight_layout()
    pca_file = os.path.join(IMG_DIR, f"pca_{lang}.png")
    plt.savefig(pca_file, dpi=110, bbox_inches="tight", facecolor="#0f0f12")
    plt.close()

    return kmeans, optimal_k, best_sil, cluster_names, cluster_info

def train_supervised(df, X_norm, lang="all"):
    """
    Trains Random Forest Regressors (With vs Without Cluster) and KNN Regressor.
    """
    N = len(df)
    y = df["vote_average"].fillna(7.0).values.astype(float)

    cluster_one_hot = np.zeros((N, len(df["cluster"].unique())))
    for i, c in enumerate(df["cluster"]):
        cluster_one_hot[i, c] = 1.0

    X_wc = np.hstack([X_norm, cluster_one_hot])
    X_nc = X_norm

    indices = np.arange(N)
    np.random.seed(42)
    np.random.shuffle(indices)
    split_pt = int(0.8 * N)
    train_idx, test_idx = indices[:split_pt], indices[split_pt:]

    Xwc_train, Xwc_test = X_wc[train_idx], X_wc[test_idx]
    Xnc_train, Xnc_test = X_nc[train_idx], X_nc[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    # Scaler for KNN
    scaler = StandardScaler()
    Xwc_train_s = scaler.fit_transform(Xwc_train)
    Xwc_test_s = scaler.transform(Xwc_test)

    # 1. Random Forest WITH Cluster
    rf_wc = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
    rf_wc.fit(Xwc_train, y_train)
    preds_rf_wc = rf_wc.predict(Xwc_test)
    m_rf_wc = {
        "rmse": round(float(np.sqrt(mean_squared_error(y_test, preds_rf_wc))), 4),
        "mae": round(float(mean_absolute_error(y_test, preds_rf_wc)), 4),
        "r2": round(float(r2_score(y_test, preds_rf_wc)), 4)
    }

    # 2. Random Forest WITHOUT Cluster
    rf_nc = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
    rf_nc.fit(Xnc_train, y_train)
    preds_rf_nc = rf_nc.predict(Xnc_test)
    m_rf_nc = {
        "rmse": round(float(np.sqrt(mean_squared_error(y_test, preds_rf_nc))), 4),
        "mae": round(float(mean_absolute_error(y_test, preds_rf_nc)), 4),
        "r2": round(float(r2_score(y_test, preds_rf_nc)), 4)
    }

    # 3. KNN Regressor
    knn = KNeighborsRegressor(n_neighbors=min(10, max(3, len(y_train) - 1)), weights="distance", n_jobs=-1)
    knn.fit(Xwc_train_s, y_train)
    preds_knn = knn.predict(Xwc_test_s)
    m_knn = {
        "rmse": round(float(np.sqrt(mean_squared_error(y_test, preds_knn))), 4),
        "mae": round(float(mean_absolute_error(y_test, preds_knn)), 4),
        "r2": round(float(r2_score(y_test, preds_knn)), 4)
    }

    metrics = {
        "rf_with_cluster": m_rf_wc,
        "rf_no_cluster": m_rf_nc,
        "knn_with_cluster": m_knn
    }

    return rf_wc, rf_nc, knn, scaler, metrics

def train_language(lang="all"):
    print(f"\n{'='*60}")
    print(f"Training CineStream Pipeline for: {LANG_NAMES.get(lang, lang.upper())} ({lang})")
    print(f"{'='*60}")

    df = load_dataset(lang)
    print(f"Dataset size: {len(df)} movies")

    # Feature extraction
    X_norm, artifacts = extract_features(df)
    print(f"Feature matrix shape: {X_norm.shape}")

    # K-Means clustering
    kmeans, optimal_k, best_sil, cluster_names, cluster_info = train_kmeans(df, X_norm, lang=lang)
    print(f"K-Means Optimal k: {optimal_k} (Silhouette Score: {best_sil:.4f})")
    for c in cluster_info[:5]:
        print(f"  C{c['id']}: {c['name']} ({c['count']} movies)")

    # Supervised models
    rf_wc, rf_nc, knn, scaler, metrics = train_supervised(df, X_norm, lang=lang)
    print("Random Forest (With Cluster):", metrics["rf_with_cluster"])
    print("Random Forest (No Cluster):  ", metrics["rf_no_cluster"])
    print("KNN Regressor (With Cluster):", metrics["knn_with_cluster"])

    # Bundle packaging
    bundle = {
        "lang": lang,
        "lang_name": LANG_NAMES.get(lang, lang.upper()),
        "movies_df": df,
        "feature_matrix": X_norm,
        "artifacts": artifacts,
        "kmeans": kmeans,
        "optimal_k": optimal_k,
        "silhouette_score": best_sil,
        "cluster_names": cluster_names,
        "clusters": cluster_info,
        "rf_with_cluster": rf_wc,
        "rf_no_cluster": rf_nc,
        "knn": knn,
        "scaler": scaler,
        "metrics": metrics,
        "pca_plot": f"/static/images/pca_{lang}.png"
    }

    out_path = os.path.join(MODEL_DIR, f"model_{lang}.pkl")
    joblib.dump(bundle, out_path, compress=3)
    print(f"[SUCCESS] Saved model bundle to: {out_path} ({os.path.getsize(out_path)/1024:.1f} KB)")
    return bundle

def main():
    parser = argparse.ArgumentParser(description="Train CineStream ML models.")
    parser.add_argument("--lang", default="all", choices=["all", "en", "hi", "kn", "ta", "te", "ml"],
                        help="Language model to train ('all' trains global and all regional languages)")
    args = parser.parse_args()

    if args.lang == "all":
        # Train global 'all' plus each regional language
        for l in ["all", "en", "hi", "kn", "ta", "te", "ml"]:
            try:
                train_language(l)
            except Exception as e:
                print(f"[ERROR] Failed training {l}: {e}")
    else:
        train_language(args.lang)

if __name__ == "__main__":
    main()
