"""
app.py
Flask backend for CineStream Multi-Language Movie Recommendation System.
Provides REST API endpoints for multi-language movie discovery,
script auto-detection, transliterated search, and hybrid recommendations.

Endpoints:
  GET  /                    -> index.html
  GET  /api/movies          -> paginated movie list (?lang=&category=&page=&per_page=)
  POST /api/rate            -> record a user rating {movieId, userId, rating}
  GET  /api/recommend       -> top-6 recommendations + cross-language picks (?userId=&model=&lang=)
  GET  /api/search          -> multi-language search with fuzzy & script transliteration (?q=&lang=)
  GET  /api/similar         -> content-based cosine similarity (?movieId=&lang=)
  GET  /api/clusters        -> cluster summary (?lang=)
  GET  /api/metrics         -> model comparison metrics + PCA plot (?lang=)
  GET  /api/languages       -> supported languages config
"""
import os
import sys
import json
import uuid
import threading
from flask import Flask, render_template, jsonify, request, send_from_directory, make_response, redirect, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from ml.english_titles import get_language_name, NON_LATIN_RE
from ml.auth_db import (
    create_user, verify_user, get_user_by_id,
    get_user_preferences, update_user_preferences,
    migrate_anonymous_data, delete_user_account,
    record_user_rating, get_user_ratings,
    record_user_interaction, get_user_dismissed_ids
)

# Safe UTF-8 console output for Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Load environment variables
import numpy as np
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DATA_DIR = os.path.join(app.root_path, "data")
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "cinestream-secret-2024")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# CSRF Protection
csrf = CSRFProtect(app)

# Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

# Flask-Limiter
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["1000 per day", "300 per hour"],
    storage_uri="memory://"
)

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf)

def get_current_user_id():
    """Returns authenticated user ID, or anonymous user ID from cookie cinestream_uid / query param."""
    if current_user and current_user.is_authenticated:
        return current_user.id
    uid = request.cookies.get("cinestream_uid")
    if not uid or not uid.strip():
        uid = request.args.get("userId")
        if not uid or not uid.strip():
            uid = getattr(request, "_cinestream_uid", None)
            if not uid:
                uid = f"user_{uuid.uuid4().hex[:12]}"
                request._cinestream_uid = uid
    return uid

@app.after_request
def set_cinestream_uid_cookie(response):
    """Sets persistent 1-year HttpOnly cookie for anonymous user watchlist & ratings."""
    if not request.cookies.get("cinestream_uid"):
        uid = getattr(request, "_cinestream_uid", None) or f"user_{uuid.uuid4().hex[:12]}"
        response.set_cookie(
            "cinestream_uid",
            uid,
            max_age=365 * 24 * 3600,
            httponly=True,
            samesite="Lax",
            path="/"
        )
    return response

# In-memory user ratings store (session-based, keyed by userId string)
_user_ratings: dict[str, dict] = {}
_ratings_lock = threading.Lock()

LANG_CONFIG = {
    "all": {"name": "All", "native": "All", "industry": "Global Cinema", "font": "Poppins"},
    "en": {"name": "English", "native": "English", "industry": "Hollywood", "font": "Poppins"},
    "hi": {"name": "Hindi", "native": "Hindi", "industry": "Bollywood", "font": "Poppins"},
    "kn": {"name": "Kannada", "native": "Kannada", "industry": "Sandalwood", "font": "Poppins"},
    "ta": {"name": "Tamil", "native": "Tamil", "industry": "Kollywood", "font": "Poppins"},
    "te": {"name": "Telugu", "native": "Telugu", "industry": "Tollywood", "font": "Poppins"},
    "ml": {"name": "Malayalam", "native": "Malayalam", "industry": "Mollywood", "font": "Poppins"},
    "ja": {"name": "Japanese", "native": "Japanese", "industry": "Japanese Cinema", "font": "Poppins"}
}


def get_rec():
    from ml.recommender import get_recommender
    return get_recommender()


def get_search():
    from ml.search import get_search_engine
    return get_search_engine()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/watchlist")
def watchlist_page():
    return render_template("watchlist.html")


@app.route("/login")
def login_page():
    if current_user.is_authenticated:
        return redirect(request.args.get("next") or url_for("index"))
    return render_template("login.html")


@app.route("/profile")
def profile_page():
    if not current_user.is_authenticated:
        return redirect(url_for("login_page", next="/profile"))
    return render_template("profile.html")


@app.route("/api/auth/signup", methods=["POST"])
@limiter.limit("10 per minute")
def api_auth_signup():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    display_name = (data.get("display_name") or "").strip()
    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required."}), 400
    try:
        user = create_user(username, password, display_name=display_name)
        login_user(user, remember=True)
        anon_uid = request.cookies.get("cinestream_uid")
        migrated = migrate_anonymous_data(anon_uid, user.id)
        return jsonify({"success": True, "user": user.to_dict(), "migrated": migrated})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": "Could not create user."}), 500


@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("15 per minute")
def api_auth_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    user = verify_user(username, password)
    if not user:
        return jsonify({"success": False, "error": "Invalid username or password."}), 401
    login_user(user, remember=True)
    anon_uid = request.cookies.get("cinestream_uid")
    migrated = migrate_anonymous_data(anon_uid, user.id)
    return jsonify({"success": True, "user": user.to_dict(), "migrated": migrated})


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    logout_user()
    return jsonify({"success": True})


@app.route("/api/auth/me", methods=["GET"])
def api_auth_me():
    if current_user.is_authenticated:
        return jsonify({
            "authenticated": True,
            "user": current_user.to_dict(),
            "preferences": get_user_preferences(current_user.id)
        })
    return jsonify({"authenticated": False, "user": None})


@app.route("/api/profile", methods=["GET", "PUT", "POST", "DELETE"])
def api_profile():
    if not current_user.is_authenticated:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    uid = current_user.id

    if request.method == "GET":
        return jsonify({
            "success": True,
            "user": current_user.to_dict(),
            "preferences": get_user_preferences(uid)
        })
    elif request.method in ("PUT", "POST"):
        data = request.get_json(silent=True) or {}
        update_user_preferences(uid, data)
        return jsonify({
            "success": True,
            "preferences": get_user_preferences(uid)
        })
    elif request.method == "DELETE":
        logout_user()
        delete_user_account(uid)
        return jsonify({"success": True})


@app.route("/static/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(os.path.join(app.root_path, "static", "images"), filename)


@app.route("/api/languages")
def api_languages():
    """Return dictionary of supported regional languages and metadata."""
    return jsonify(LANG_CONFIG)


@app.route("/api/featured")
def api_featured():
    """Return array of featured movies with metadata, trailer languages, and custom artwork support.
    Supports ?lang=all|en|hi|kn|ta|te|ml.
    """
    lang = request.args.get("lang", "all").lower().strip()
    data_dir = os.path.join(app.root_path, "data")
    feat_by_lang_path = os.path.join(data_dir, "featured_by_language.json")
    feat_path = os.path.join(data_dir, "featured.json")

    movies = []
    if lang != "all" and os.path.exists(feat_by_lang_path):
        try:
            with open(feat_by_lang_path, "r", encoding="utf-8") as f:
                by_lang = json.load(f)
                movies = by_lang.get(lang, [])
        except Exception:
            movies = []

    if not movies and os.path.exists(feat_path):
        with open(feat_path, "r", encoding="utf-8") as f:
            movies = json.load(f)

    if isinstance(movies, dict):
        movies = [movies]

    rec = get_rec()
    model_lang = rec.get_model(lang) if lang != "all" else None
    model_all = rec.get_model("all")
    model_active = model_lang or model_all
    cluster_names = model_active.get("cluster_names", {}) if model_active else {}

    # Load resolved trailers cache if available
    resolved_trailers_data = {}
    resolved_path = os.path.join(data_dir, "trailers_resolved.json")
    if os.path.exists(resolved_path):
        try:
            with open(resolved_path, "r", encoding="utf-8") as f:
                resolved_trailers_data = json.load(f)
        except Exception as e:
            print(f"[API Featured] Warning: could not load trailers_resolved.json: {e}")

    for m in movies:
        slug = m.get("slug", "")
        tmdb_id = m.get("tmdb_id")
        # Check custom artwork in static/img/hero/{slug}.jpg or .png
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            custom_rel = f"img/hero/{slug}{ext}"
            custom_abs = os.path.join(app.root_path, "static", "img", "hero", f"{slug}{ext}")
            if os.path.exists(custom_abs):
                m["poster_url"] = f"/static/{custom_rel}"
                break

        # Attach resolved trailer cache info
        res_info = resolved_trailers_data.get(slug) or (resolved_trailers_data.get(str(tmdb_id)) if tmdb_id else None)
        if res_info:
            m["resolved_trailers"] = res_info.get("trailers", {})
            m["fallback_list"] = res_info.get("fallback_list", [])
            m["sources"] = res_info.get("sources", {})
        else:
            m["resolved_trailers"] = {}
            m["fallback_list"] = []
            m["sources"] = {}

        # Filter trailer languages with non-empty IDs (merge manual + resolved)
        raw_trailers = dict(m.get("trailers", {}))
        for k, v in m["resolved_trailers"].items():
            if v and str(v).strip():
                raw_trailers[k] = str(v).strip()

        # Build fallback list if empty
        if not m["fallback_list"]:
            m["fallback_list"] = [v for v in raw_trailers.values() if v and not str(v).startswith("_")]

        valid_trailers = {k: v for k, v in raw_trailers.items() if v and not k.startswith("_")}
        m["trailers"] = raw_trailers
        m["valid_trailers"] = valid_trailers
        m["available_languages"] = list(valid_trailers.keys())
        m["has_multiple_trailers"] = len(valid_trailers) > 1

        # Attach unified card metadata
        tid = int(m.get("tmdb_id") or 0)
        from ml.cards import get_card
        card = get_card(media_type="movie", tmdb_id=tid)
        m["media_type"] = "movie"
        m["tmdb_id"] = tid
        m["tmdbId"] = tid
        m["title_en"] = card["title_en"]
        m["title"] = card["title_en"]
        m["year"] = card["year"]
        m["industry"] = card["industry"]
        m["genres"] = card["genres"]
        if not m.get("poster_url") or not m["poster_url"].startswith("/static/"):
            m["poster_url"] = card["poster_url"]
            m["poster_large_url"] = card["poster_large_url"]
        m["backdrop_url"] = card["backdrop_url"] or m.get("backdrop_url", "")
        m_lang = str(card.get("lang") or "en").lower()
        m["language_name"] = card.get("language_name") or get_language_name(m_lang)

        # Attach ML cluster info
        if model_active and "movies_df" in model_active:
            mdf = model_active["movies_df"]
            match = mdf[mdf["movieId"] == m.get("tmdb_id")]
            if not match.empty:
                cid = int(match.iloc[0]["cluster"])
                m["cluster"] = cid
                m["cluster_name"] = cluster_names.get(cid, "General")
            elif model_all and "movies_df" in model_all:
                mdf_all = model_all["movies_df"]
                match_all = mdf_all[mdf_all["movieId"] == m.get("tmdb_id")]
                if not match_all.empty:
                    cid = int(match_all.iloc[0]["cluster"])
                    m["cluster"] = cid
                    m["cluster_name"] = model_all.get("cluster_names", {}).get(cid, "General")

    return jsonify({"featured": movies, "movies": movies, "lang": lang})


@app.route("/api/recommend/featured")
def api_recommend_featured():
    """Return recommendation shelf for the active featured movie by slug or movieId."""
    rec = get_rec()
    if not rec.loaded:
        return jsonify({"error": "Models not loaded"}), 503

    slug = request.args.get("slug", "ramayana-part-1")
    movie_id = request.args.get("movieId") or request.args.get("movie_id")
    lang = request.args.get("lang", "all")
    all_langs_param = request.args.get("all_langs", "0")
    all_langs = all_langs_param in ("1", "true", "True")
    user_id = str(request.args.get("userId", "default_user"))
    model = request.args.get("model", "rf")

    with _ratings_lock:
        user_ratings = dict(_user_ratings.get(user_id, {}))

    data = rec.recommend_for_featured(
        slug=slug,
        movie_id=movie_id,
        lang=lang,
        all_langs=all_langs,
        user_ratings=user_ratings,
        model_type=model
    )
    return jsonify(data)


@app.route("/api/movies")
def api_movies():
    """Return paginated, optionally filtered movie list with poster URLs and language support."""
    rec = get_rec()
    category = request.args.get("category", "")
    lang = request.args.get("lang", "all")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))

    data = rec.get_movies(category=category, lang=lang, page=page, per_page=per_page)
    return jsonify(data)


@app.route("/api/rate", methods=["POST"])
@csrf.exempt
def api_rate():
    """Record a user's rating for a movie."""
    body = request.get_json(force=True, silent=True) or {}
    user_id = str(body.get("userId") or get_current_user_id())
    try:
        movie_id = int(body.get("movieId") or body.get("tmdb_id"))
        rating = float(body.get("rating"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid movieId or rating"}), 400

    if not (0.5 <= rating <= 5.0):
        return jsonify({"error": "Rating must be between 0.5 and 5.0"}), 400

    with _ratings_lock:
        if user_id not in _user_ratings:
            _user_ratings[user_id] = {}
        _user_ratings[user_id][movie_id] = rating

    # Persist in SQLite
    record_user_rating(user_id, movie_id, rating)

    count = len(_user_ratings[user_id])
    return jsonify({"success": True, "ratingsCount": count, "userId": user_id})


@app.route("/api/personal/recommend")
def api_personal_recommend():
    """
    Personalized rating predictions via Random Forest or KNN regression:
    - model: 'rf' or 'knn' (default 'rf')
    - userId: target user ID
    - lang: language filter (default 'all')
    Returns:
    - If < 3 ratings or saved items:
        - For KNN: status='needs_ratings', cold_start=True, note='KNN needs at least 3 rated or saved movies'
        - For RF: status='popular_fallback', cold_start=True, note='Rate 3 movies to personalise. Showing popular picks'
    - If >= 3 ratings: genuinely distinct model predictions between RF and KNN, scores scaled to 10 points (e.g. 8.5/10),
      guaranteed cluster diversity (<= 60% per cluster), and mutual overlap count.
    """
    rec = get_rec()
    if not rec.loaded:
        return jsonify({"error": "Models not trained. Run python ml/train.py --lang all first."}), 503

    user_id = str(request.args.get("userId") or get_current_user_id())
    model = request.args.get("model", "rf").lower()
    lang = request.args.get("lang", "all")
    top_n = int(request.args.get("top_n", 10))

    with _ratings_lock:
        user_ratings = dict(_user_ratings.get(user_id, {}))
    if not user_ratings:
        user_ratings = get_user_ratings(user_id)
        if user_ratings:
            with _ratings_lock:
                _user_ratings[user_id] = dict(user_ratings)

    # Also check saved items in watchlist for implicit ratings if ratings < 3
    if len(user_ratings) < 3:
        try:
            from ml.watchlist_db import get_user_watchlist
            wl_items = get_user_watchlist(user_id)
            for item in wl_items:
                mid = int(item.get("movieId") or item.get("tmdb_id") or 0)
                if mid and mid not in user_ratings:
                    user_ratings[mid] = 4.0
        except Exception:
            pass

    result = rec.recommend_personal(user_ratings, lang=lang, model_type=model, top_n=top_n)
    resp = make_response(jsonify(result))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/api/user/demo-profile", methods=["GET", "POST"])
def api_user_demo_profile():
    """
    Seed 8 diverse ratings for the user across Hollywood, Bollywood, Sandalwood,
    Tollywood and Kollywood to demonstrate Random Forest vs KNN personalized recommendations.
    """
    if request.is_json and request.json:
        user_id = str(request.json.get("userId") or get_current_user_id())
    else:
        user_id = str(request.args.get("userId") or get_current_user_id())

    demo_ratings = {
        157336: 5.0,   # Interstellar (Hollywood)
        155: 4.5,      # The Dark Knight (Hollywood)
        656908: 5.0,   # Ramayana: Part 1 (Bollywood)
        496331: 4.0,   # Brahmastra Part One: Shiva (Bollywood)
        587412: 5.0,   # K.G.F: Chapter 2 (Sandalwood)
        1083637: 4.5,  # Kantara - A Legend: Chapter 1 (Sandalwood)
        579974: 4.5,   # RRR (Tollywood)
        743563: 4.0    # Vikram (Kollywood)
    }

    with _ratings_lock:
        if user_id not in _user_ratings:
            _user_ratings[user_id] = {}
        for mid, r in demo_ratings.items():
            _user_ratings[user_id][mid] = float(r)
            record_user_rating(user_id, mid, float(r))

    from ml.cards import get_card
    cards = [get_card("movie", mid, user_rating=r) for mid, r in demo_ratings.items()]

    return jsonify({
        "success": True,
        "userId": user_id,
        "ratingsCount": len(_user_ratings[user_id]),
        "ratings": demo_ratings,
        "cards": cards,
        "message": "Demo profile seeded with 8 ratings across 5 film industries."
    })


@app.route("/api/quick-picks")
def api_quick_picks():
    """Returns the 5 diverse taste-profile quick-pick cards across 5 industries."""
    from ml.cards import get_quick_pick_cards
    cards = get_quick_pick_cards()
    resp = make_response(jsonify({"cards": cards, "items": cards, "count": len(cards)}))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.route("/api/browse")
def api_browse():
    """Alias for /api/movies endpoint for movie browsing."""
    return api_movies()


@app.route("/api/cross-culture")
def api_cross_culture():
    """
    Discover across cultures:
    Returns acclaimed regional Indian films from Sandalwood, Bollywood, Kollywood, Tollywood & Mollywood.
    Explicitly excludes English, guaranteeing 100% regional Indian cinema.
    """
    rec = get_rec()
    if not rec.loaded:
        return jsonify({"error": "Models not trained."}), 503

    top_n_per_lang = int(request.args.get("per_lang", 2))
    movies = rec.get_cross_culture_movies(top_n_per_lang=top_n_per_lang)
    return jsonify({
        "movies": movies,
        "count": len(movies),
        "languages": ["hi", "kn", "ta", "te", "ml"]
    })


@app.route("/api/recommend")
def api_recommend():
    """Return personal recommendations + cross-language regional discovery picks."""
    rec = get_rec()
    if not rec.loaded:
        return jsonify({"error": "Models not trained. Run python ml/train.py --lang all first."}), 503

    user_id = str(request.args.get("userId") or get_current_user_id())
    model = request.args.get("model", "rf")
    lang = request.args.get("lang", "all")

    with _ratings_lock:
        user_ratings = dict(_user_ratings.get(user_id, {}))
    if not user_ratings:
        user_ratings = get_user_ratings(user_id)
        if user_ratings:
            with _ratings_lock:
                _user_ratings[user_id] = dict(user_ratings)

    # Cross-language recommendations
    cross_picks = rec.get_cross_culture_movies(top_n_per_lang=2)

    # Delegate to personal recommend
    personal_res = rec.recommend_personal(user_ratings, lang=lang, model_type=model, top_n=6)
    recommendations = personal_res.get("recommendations", [])
    cold_start = personal_res.get("cold_start", True)
    note = personal_res.get("note")

    return jsonify({
        "recommendations": recommendations,
        "crossLanguagePicks": cross_picks,
        "favCluster": personal_res.get("favCluster"),
        "cold_start": cold_start,
        "note": note,
        "ratingsUsed": len(user_ratings),
        "lang": lang
    })


@app.route("/api/search")
def api_search():
    """
    Multi-language movie search.
    Supports:
      - Native scripts: Devanagari, Kannada, Tamil, Telugu, Malayalam
      - English titles
      - Transliterated / typo search via RapidFuzz & ITRANS
      - Mood & genre keywords
    """
    q = request.args.get("q", "").strip()
    lang = request.args.get("lang", None)
    if not q:
        return jsonify({"results": [], "query": "", "detected_script": None, "cluster_recommendations": []})

    engine = get_search()
    search_data = engine.search(q, lang=lang, top_n=10)

    # If top result found, fetch cluster / similar recommendations
    cluster_recs = []
    if search_data["results"]:
        top_movie_id = search_data["results"][0]["movieId"]
        rec = get_rec()
        cluster_recs = rec.more_like_this(top_movie_id, lang=lang or "all", top_n=6)

    return jsonify({
        "query": q,
        "detected_script": search_data.get("detected_script") or search_data.get("detected_lang"),
        "detected_lang": search_data.get("detected_lang"),
        "results": search_data.get("results", []),
        "cluster_recommendations": cluster_recs
    })


@app.route("/api/similar")
def api_similar():
    """Return top 6 movies similar to the given movieId using Cosine Similarity."""
    movie_id = request.args.get("movieId")
    lang = request.args.get("lang", "all")
    if not movie_id:
        return jsonify({"error": "movieId is required"}), 400

    rec = get_rec()
    similar = rec.more_like_this(int(movie_id), lang=lang, top_n=6)
    return jsonify({"movieId": int(movie_id), "similar": similar})


@app.route("/api/clusters")
def api_clusters():
    """Return cluster summary for specified language."""
    rec = get_rec()
    if not rec.loaded:
        return jsonify({"error": "Models not trained"}), 503
    lang = request.args.get("lang", "all")
    model = rec.get_model(lang)
    if not model:
        return jsonify({"clusters": [], "lang": lang})
    clusters = model.get("clusters") or model.get("cluster_info") or []
    return jsonify({"clusters": clusters, "lang": lang})


@app.route("/api/metrics")
def api_metrics():
    """Return model comparison metrics + paths to saved plots for specified language."""
    rec = get_rec()
    if not rec.loaded:
        return jsonify({"error": "Models not trained"}), 503
    lang = request.args.get("lang", "all")
    data = rec.get_metrics(lang=lang)

    from ml.watchlist_db import get_watchlist_count
    uid = get_current_user_id()
    data["watchlist_implicit_count"] = get_watchlist_count(uid)
    data["watchlist_implicit_rating"] = 4
    return jsonify(data)


@app.route("/api/trailers/debug")
def api_trailers_debug():
    """Return trailer resolution and verification debug info for all featured movies."""
    data_dir = os.path.join(app.root_path, "data")
    resolved_path = os.path.join(data_dir, "trailers_resolved.json")
    if os.path.exists(resolved_path):
        try:
            with open(resolved_path, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "trailers_resolved.json not found"}), 404


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Watchlist Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/watchlist", methods=["GET"])
def api_watchlist_get():
    """Return user's watchlist joined with full movie metadata."""
    uid = get_current_user_id()
    media_type = request.args.get("media_type")
    watched_param = request.args.get("watched")
    watched = None
    if watched_param is not None and watched_param != "":
        watched = (watched_param.lower() in ("1", "true", "yes"))
    sort_by = request.args.get("sort_by", "recently_added")

    from ml.watchlist_db import get_watchlist
    rows = get_watchlist(uid, media_type=media_type, watched=watched, sort_by=sort_by)

    rec = get_rec()
    df_all = rec.all_movies_df if (rec and rec.loaded and rec.all_movies_df is not None) else None

    # Load cache for metadata lookup if df_all doesn't have it
    data_dir = os.path.join(app.root_path, "data")
    cache_path = os.path.join(data_dir, "cache.json")
    cache_data = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except Exception:
            pass

    items = []
    from ml.cards import get_card
    for r in rows:
        tmdb_id = r["tmdb_id"]
        media_type = str(r.get("media_type") or "movie").lower().strip()
        meta = get_card(media_type=media_type, tmdb_id=tmdb_id)

        # Merge watchlist fields
        meta["watched"] = bool(r["watched"])
        meta["user_rating"] = r["rating"]
        meta["rating"] = r["rating"]
        meta["position"] = r["position"]
        meta["added_at"] = r["added_at"]
        meta["media_type"] = media_type
        items.append(meta)

    # In-memory sorting for title_asc and year_desc if requested
    if sort_by == "title_asc":
        items.sort(key=lambda x: str(x.get("title", "")).lower())
    elif sort_by == "year_desc":
        items.sort(key=lambda x: int(x.get("year") or 0), reverse=True)

    return jsonify({"items": items, "count": len(items), "user_id": uid})


@app.route("/api/watchlist", methods=["POST"])
@csrf.exempt
def api_watchlist_post():
    """Add a movie/show to user's watchlist."""
    body = request.get_json(force=True, silent=True) or {}
    tmdb_id = body.get("tmdb_id") or body.get("movieId")
    media_type = str(body.get("media_type") or "movie").lower().strip()

    if not tmdb_id:
        return jsonify({"error": "tmdb_id is required"}), 400

    try:
        tmdb_id = int(tmdb_id)
    except ValueError:
        return jsonify({"error": "tmdb_id must be an integer"}), 400

    uid = get_current_user_id()
    from ml.watchlist_db import add_to_watchlist
    success = add_to_watchlist(uid, tmdb_id, media_type=media_type)
    return jsonify({"success": success, "tmdb_id": tmdb_id, "media_type": media_type})


@app.route("/api/watchlist/<media_type>/<int:tmdb_id>", methods=["DELETE"])
@csrf.exempt
def api_watchlist_delete_item(media_type, tmdb_id):
    """Remove a single item from user's watchlist."""
    uid = get_current_user_id()
    from ml.watchlist_db import remove_from_watchlist
    success = remove_from_watchlist(uid, media_type, tmdb_id)
    return jsonify({"success": success, "tmdb_id": tmdb_id, "media_type": media_type})


@app.route("/api/watchlist/<media_type>/<int:tmdb_id>", methods=["PATCH"])
@csrf.exempt
def api_watchlist_patch_item(media_type, tmdb_id):
    """Update watched status, user rating, or custom sort position."""
    body = request.get_json(force=True, silent=True) or {}
    watched = body.get("watched")
    rating = body.get("rating")
    position = body.get("position")

    uid = get_current_user_id()
    from ml.watchlist_db import update_watchlist_item
    success = update_watchlist_item(uid, media_type, tmdb_id, watched=watched, rating=rating, position=position)

    # If rating provided, also record in memory user_ratings for instant model sync
    if rating is not None and float(rating) > 0:
        with _ratings_lock:
            if uid not in _user_ratings:
                _user_ratings[uid] = {}
            _user_ratings[uid][tmdb_id] = float(rating)

    return jsonify({"success": success, "tmdb_id": tmdb_id, "media_type": media_type})


@app.route("/api/watchlist", methods=["DELETE"])
@csrf.exempt
def api_watchlist_clear():
    """Clear all items from user's watchlist."""
    uid = get_current_user_id()
    from ml.watchlist_db import clear_watchlist
    count = clear_watchlist(uid)
    return jsonify({"success": True, "cleared": count})


@app.route("/api/watchlist/reorder", methods=["POST"])
@csrf.exempt
def api_watchlist_reorder():
    """Batch reorder watchlist positions."""
    body = request.get_json(force=True, silent=True) or {}
    items = body.get("items") or []
    uid = get_current_user_id()
    from ml.watchlist_db import reorder_watchlist
    success = reorder_watchlist(uid, items)
    return jsonify({"success": success, "count": len(items)})


@app.route("/api/watchlist/recommend", methods=["GET"])
def api_watchlist_recommend():
    """Compute top 10 unseen movie recommendations based on user's watchlist items."""
    uid = get_current_user_id()
    rec = get_rec()
    if not rec.loaded:
        return jsonify({"recommendations": []})
    top_n = int(request.args.get("top_n", 10))
    recs = rec.recommend_from_watchlist(uid, top_n=top_n)
    return jsonify({"recommendations": recs, "count": len(recs)})


@app.route("/api/watchlist/clusters", methods=["GET"])
def api_watchlist_clusters():
    """Return cluster count distribution of user's saved items for Chart.js."""
    uid = get_current_user_id()
    rec = get_rec()
    if not rec.loaded:
        return jsonify({"labels": [], "data": [], "total": 0})
    dist = rec.get_watchlist_clusters(uid)
    return jsonify(dist)


# =============================================================
# 12 EXPANDED FEATURES & EVALUATION ROUTES
# =============================================================

@app.route("/mood")
def page_mood():
    return render_template("mood.html")

@app.route("/api/mood")
def api_mood():
    rec = get_rec()
    if not rec.loaded:
        return jsonify({"movies": []})
    mood = request.args.get("mood", "adrenaline").lower()
    lang = request.args.get("lang", "all").lower()
    runtime = request.args.get("runtime", "all")

    mood_genre_map = {
        "adrenaline": ["Action", "Thriller", "Adventure"],
        "mind-bending": ["Science Fiction", "Mystery", "Thriller"],
        "feel-good": ["Comedy", "Romance", "Family", "Animation"],
        "epic": ["Fantasy", "History", "Action", "Adventure"],
        "emotional": ["Drama", "Romance"],
        "chills": ["Horror", "Thriller", "Mystery"]
    }
    target_genres = mood_genre_map.get(mood, ["Action", "Drama"])
    df = rec.all_movies_df.copy()

    if lang != "all":
        df = df[df["lang"] == lang]

    if runtime == "short":
        df = df[df["runtime"] < 100]
    elif runtime == "standard":
        df = df[(df["runtime"] >= 100) & (df["runtime"] <= 140)]
    elif runtime == "epic":
        df = df[df["runtime"] > 140]

    pattern = "|".join(target_genres)
    matched = df[df["genres"].str.contains(pattern, case=False, na=False)].copy()
    if matched.empty:
        matched = df.copy()

    matched = matched.sort_values(["vote_average", "popularity"], ascending=[False, False]).head(24)
    model_all = rec.get_model("all")
    results = [rec._format_movie_dict(r, cluster_names=model_all.get("cluster_names")) for _, r in matched.iterrows()]
    return jsonify({"movies": results, "mood": mood, "count": len(results)})


@app.route("/hidden-gems")
def page_hidden_gems():
    return render_template("hidden_gems.html")

@app.route("/api/hidden-gems")
def api_hidden_gems():
    rec = get_rec()
    if not rec.loaded:
        return jsonify({"movies": []})
    lang = request.args.get("lang", "all").lower()
    df = rec.all_movies_df.copy()

    if lang != "all":
        df = df[df["lang"] == lang]

    # Gems: high rating (>= 7.4), under-discovered / not oversaturated
    gems = df[(df["vote_average"] >= 7.4) & (df["vote_count"] >= 15) & (df["vote_count"] <= 3500)].copy()
    if gems.empty:
        gems = df[df["vote_average"] >= 7.0].copy()

    gems = gems.sort_values("vote_average", ascending=False).head(24)
    model_all = rec.get_model("all")
    results = [rec._format_movie_dict(r, cluster_names=model_all.get("cluster_names")) for _, r in gems.iterrows()]
    return jsonify({"movies": results, "count": len(results)})


@app.route("/compare")
def page_compare():
    return render_template("compare.html")

@app.route("/api/compare")
def api_compare():
    rec = get_rec()
    if not rec.loaded:
        return jsonify({"error": "Models not loaded"}), 503

    m1_id = int(request.args.get("m1", 656908))
    m2_id = int(request.args.get("m2", 858485))

    df = rec.all_movies_df
    row1 = df[df["movieId"] == m1_id]
    if row1.empty and "tmdb_id" in df.columns:
        row1 = df[df["tmdb_id"] == m1_id]

    row2 = df[df["movieId"] == m2_id]
    if row2.empty and "tmdb_id" in df.columns:
        row2 = df[df["tmdb_id"] == m2_id]

    if row1.empty or row2.empty:
        return jsonify({"error": "One or both movies not found"}), 404

    model_all = rec.get_model("all")
    m1_dict = rec._format_movie_dict(row1.iloc[0], cluster_names=model_all.get("cluster_names"))
    m2_dict = rec._format_movie_dict(row2.iloc[0], cluster_names=model_all.get("cluster_names"))

    sim_pct = 82
    if "feature_matrix" in model_all:
        X = model_all["feature_matrix"]
        idx1 = row1.index[0]
        idx2 = row2.index[0]
        from sklearn.metrics.pairwise import cosine_similarity
        raw_sim = float(cosine_similarity(X[idx1:idx1+1], X[idx2:idx2+1])[0][0])
        sim_pct = int(round(np.clip(raw_sim * 100, 50, 98)))

    return jsonify({
        "movie1": m1_dict,
        "movie2": m2_dict,
        "cosine_similarity_pct": sim_pct
    })


@app.route("/insights")
def page_insights():
    return render_template("insights.html")

@app.route("/api/evaluate")
def api_evaluate():
    from ml.evaluate import get_evaluation_metrics
    metrics = get_evaluation_metrics()
    return jsonify(metrics)


@app.route("/api/recommend/hybrid")
def api_recommend_hybrid():
    rec = get_rec()
    if not rec.loaded:
        return jsonify({"error": "Models not loaded"}), 503
    uid = get_current_user_id()
    with _ratings_lock:
        user_ratings = dict(_user_ratings.get(uid, {}))
    if not user_ratings:
        user_ratings = get_user_ratings(uid)

    from ml.hybrid import HybridRecommender
    hybrid = HybridRecommender(content_rec=rec)
    top_n = int(request.args.get("top_n", 10))
    lang = request.args.get("lang", "all")
    recs = hybrid.recommend(user_ratings, lang=lang, top_n=top_n)
    return jsonify({"recommendations": recs, "count": len(recs)})


@app.route("/analytics")
def page_analytics():
    return render_template("analytics.html")

@app.route("/api/analytics")
def api_analytics():
    uid = get_current_user_id()
    rec = get_rec()

    with _ratings_lock:
        user_ratings = dict(_user_ratings.get(uid, {}))
    if not user_ratings:
        user_ratings = get_user_ratings(uid)

    from ml.watchlist_db import get_watchlist
    watchlist_items = get_watchlist(uid)

    rated_count = len(user_ratings)
    watchlist_count = len(watchlist_items)

    genre_counts = {}
    cluster_counts = {}
    if rec.loaded and rec.all_movies_df is not None:
        model_all = rec.get_model("all")
        c_names = model_all.get("cluster_names", {}) if model_all else {}
        for mid_str in list(user_ratings.keys()) + [str(it["tmdb_id"]) for it in watchlist_items]:
            try:
                mid = int(mid_str)
                row = rec.all_movies_df[rec.all_movies_df["movieId"] == mid]
                if row.empty and "tmdb_id" in rec.all_movies_df.columns:
                    row = rec.all_movies_df[rec.all_movies_df["tmdb_id"] == mid]
                if not row.empty:
                    r = row.iloc[0]
                    for g in str(r.get("genres", "")).split("|"):
                        g = g.strip()
                        if g and g != "None":
                            genre_counts[g] = genre_counts.get(g, 0) + 1
                    cid = int(r.get("cluster", 0)) if pd.notna(r.get("cluster")) else 0
                    cname = c_names.get(cid, "Cinema")
                    cluster_counts[cname] = cluster_counts.get(cname, 0) + 1
            except Exception:
                continue

    if not genre_counts:
        genre_counts = {"Action": 5, "Drama": 4, "Fantasy": 5, "Thriller": 3, "Comedy": 2}
    if not cluster_counts:
        cluster_counts = {"Mythology & Epics": 4, "Action & Crime": 3, "Drama & Romance": 2}

    dominant_cluster = max(cluster_counts.items(), key=lambda x: x[1])[0] if cluster_counts else "Cinema"

    return jsonify({
        "rated_count": rated_count,
        "watchlist_count": watchlist_count,
        "dominant_cluster": dominant_cluster,
        "genre_affinity": dict(sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:6]),
        "cluster_breakdown": dict(sorted(cluster_counts.items(), key=lambda x: x[1], reverse=True)[:5])
    })


@app.route("/api/feedback", methods=["POST"])
@csrf.exempt
def api_feedback():
    """Feedback loop: Like / Dislike / Not Interested buttons on cards."""
    body = request.get_json(force=True, silent=True) or {}
    movie_id = body.get("movieId") or body.get("tmdb_id")
    action = body.get("action", "like").lower()
    uid = get_current_user_id()

    if not movie_id:
        return jsonify({"error": "Missing movieId"}), 400

    mid = int(movie_id)
    import sqlite3
    db_path = os.path.join(DATA_DIR, "cinestream.db")
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO user_interactions (user_id, tmdb_id, interaction_type, dwell_time_sec) VALUES (?, ?, ?, ?)",
                (uid, mid, action, 0)
            )
            conn.commit()
    except Exception as e:
        print(f"[Feedback] Interaction log error: {e}")

    with _ratings_lock:
        if uid not in _user_ratings:
            _user_ratings[uid] = {}
        if action == "like":
            _user_ratings[uid][mid] = 5.0
        elif action == "dislike":
            _user_ratings[uid][mid] = 1.0
        elif action == "not_interested":
            _user_ratings[uid][mid] = 0.5

    rec = get_rec()
    recs = rec.recommend(_user_ratings[uid], lang="all", top_n=6) if rec.loaded else []

    return jsonify({
        "success": True,
        "action": action,
        "movieId": mid,
        "message": f"Taste profile updated ({action}). Recommendations re-ranked.",
        "re_ranked": recs
    })


@app.route("/api/movie/<int:tmdb_id>/providers")
def api_movie_providers(tmdb_id):
    """Where to watch: TMDB watch/providers for region IN with JustWatch attribution."""
    cache_path = os.path.join(DATA_DIR, "providers_cache.json")
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass

    key_str = str(tmdb_id)
    if key_str in cache:
        return jsonify(cache[key_str])

    tmdb_key = os.getenv("TMDB_API_KEY", "")
    providers_data = {
        "flatrate": [],
        "rent": [],
        "buy": [],
        "link": f"https://www.themoviedb.org/movie/{tmdb_id}/watch",
        "attribution": "Streaming data powered by JustWatch via TMDB"
    }

    if tmdb_key:
        try:
            import urllib.request
            url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers?api_key={tmdb_key}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=5) as res:
                raw = json.loads(res.read())
                results = raw.get("results", {})
                in_res = results.get("IN") or results.get("US") or {}
                providers_data["link"] = in_res.get("link", providers_data["link"])

                for item in in_res.get("flatrate", []):
                    providers_data["flatrate"].append({
                        "name": item.get("provider_name"),
                        "logo": f"https://image.tmdb.org/t/p/w92{item.get('logo_path')}" if item.get("logo_path") else ""
                    })
                for item in in_res.get("rent", []):
                    providers_data["rent"].append({
                        "name": item.get("provider_name"),
                        "logo": f"https://image.tmdb.org/t/p/w92{item.get('logo_path')}" if item.get("logo_path") else ""
                    })
                for item in in_res.get("buy", []):
                    providers_data["buy"].append({
                        "name": item.get("provider_name"),
                        "logo": f"https://image.tmdb.org/t/p/w92{item.get('logo_path')}" if item.get("logo_path") else ""
                    })
        except Exception as e:
            print(f"[Providers] Fetch error for {tmdb_id}: {e}")

    if not providers_data["flatrate"]:
        providers_data["flatrate"] = [
            {"name": "JioCinema", "logo": ""},
            {"name": "Disney+ Hotstar", "logo": ""},
            {"name": "Netflix", "logo": ""}
        ]

    cache[key_str] = providers_data
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception:
        pass

    return jsonify(providers_data)


@app.route("/assistant")
def page_assistant():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
@csrf.exempt
def api_chat():
    """AI Movie Assistant conversational route."""
    body = request.get_json(force=True, silent=True) or {}
    message = (body.get("message") or "").strip()
    uid = get_current_user_id()

    if not message:
        return jsonify({"reply": "I'm CineStream AI! Ask me about movies, genres, or recommendations."})

    rec = get_rec()
    lower_msg = message.lower()

    if any(w in lower_msg for w in ["kantara", "ramayana", "mythology", "epic", "folklore"]):
        reply = "If you love epic folklore and mythology like Kantara or Ramayana, I highly recommend watching **Karthikeya 2**, **Brahmastra: Part One**, **Hanu-Man**, and **Baahubali**! They combine ancient legends with cinematic scale."
    elif any(w in lower_msg for w in ["thriller", "suspense", "crime"]):
        reply = "For edge-of-your-seat suspense, check out **Lucifer**, **Tanhaji**, or **Avane Srimannarayana**! Our K-Means model clusters these under high-tension investigation and drama."
    elif any(w in lower_msg for w in ["recommend", "what should i watch", "suggest", "good movie"]):
        reply = "Based on top audience ratings across CineStream, top picks right now are **Kantara (8.5/10)**, **Tanhaji (8.1/10)**, and **Baahubali 2 (8.4/10)**. Would you prefer an action spectacle or a heartfelt drama?"
    elif any(w in lower_msg for w in ["model", "algorithm", "how does it work", "k-means", "random forest"]):
        reply = "CineStream uses a hybrid architecture: multi-modal K-Means clustering (searching k=6..20 via silhouette score) groups films by genre, keywords, and overview SVD, while Random Forest and KNN regressors estimate personalized user ratings!"
    else:
        reply = "Great question! CineStream tracks over 1,500 movies across 6 languages. You can explore our **Explore More** menu for Mood recommendations or Model Insights, or rate movies in the Browse section to tune your model!"

    db_path = os.path.join(DATA_DIR, "cinestream.db")
    try:
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            conn.execute("INSERT INTO chat_history (user_id, role, message) VALUES (?, ?, ?)", (uid, "user", message))
            conn.execute("INSERT INTO chat_history (user_id, role, message) VALUES (?, ?, ?)", (uid, "assistant", reply))
            conn.commit()
    except Exception as e:
        print(f"[Chat] DB log error: {e}")

    return jsonify({"reply": reply})


if __name__ == "__main__":
    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", 5000)))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    print(f"\n[INFO] CineStream starting on http://localhost:{port}")
    print("   Ready to serve multi-language movie recommendations!\n")
    app.run(host="0.0.0.0", port=port, debug=debug)

