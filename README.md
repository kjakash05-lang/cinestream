# 🎬 CineStream — Multi-Language ML Movie Recommendation System

A complete college Machine Learning project featuring **both unsupervised** (K-Means clustering with PCA) and **supervised** (Random Forest + KNN regression) learning with a **multi-language search and recommendation engine** supporting 6 Indian & International film industries:
- **Hindi (Bollywood)** — हिन्दी
- **Kannada (Sandalwood)** — ಕನ್ನಡ
- **Tamil (Kollywood)** — தமிழ்
- **Telugu (Tollywood)** — తెలుగు
- **Malayalam (Mollywood)** — മലയാളം
- **English (Hollywood)** — English

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure TMDB API Key
Ensure `.env` has your TMDB key:
```env
TMDB_API_KEY=your_key_here
```

### 3. Fetch Multi-Language Movies Dataset
Fetches Indian regional films (Kannada, Hindi, Tamil, Telugu, Malayalam) and Hollywood films with official posters:
```bash
python ml/fetch_movies.py
```
Outputs `data/movies_all.csv` (1,551 movies) and caches responses to `data/cache.json`.

### 4. Train the Multi-Language ML Models
Trains K-Means clustering, PCA visualisations, Random Forest (With vs Without Cluster comparison), and KNN regressors across all languages:
```bash
python ml/train.py --lang all
```
Saves bundles `models/model_all.pkl`, `models/model_en.pkl`, `models/model_hi.pkl`, `models/model_kn.pkl`, `models/model_ta.pkl`, `models/model_te.pkl`, and `models/model_ml.pkl`, plus PCA plots in `static/images/`.

### 5. Start the web server
```bash
python app.py
```
Open: **http://localhost:5000**

---

## 📁 Project Structure

```
Movie Recommendation/
├── app.py                  # Flask REST API with multi-lang endpoints
├── requirements.txt        # Python dependencies (rapidfuzz, indic-transliteration, etc.)
├── .env                    # TMDB API Key & environment config
├── data/
│   ├── movies_all.csv      # 1,551 movies across 6 languages
│   └── cache.json          # Cached TMDB payloads
├── ml/
│   ├── fetch_movies.py     # Concurrent TMDB fetcher for Indian & Hollywood cinema
│   ├── search.py           # Multi-language fuzzy & transliterated search engine
│   ├── train.py            # Multi-language ML training pipeline (--lang all)
│   └── recommender.py      # Inference engine (personalized + cross-language picks)
├── models/                 # Serialized model bundles (model_{lang}.pkl)
├── static/
│   ├── css/style.css       # Responsive styling & regional font classes
│   ├── js/main.js          # GSAP 3 animations, voice search, script toggling
│   └── images/             # 2D PCA cluster projection plots
├── templates/
│   └── index.html          # Interactive streaming portal & Model Insights modal
└── README.md
```

---

## 🤖 ML Pipeline Explained

### 1. Unsupervised Learning (Untracked) — K-Means Clustering
- **Feature Matrix:** One-hot encoded genres combined with scaled numerical features (`year`, `runtime`, `popularity`, `vote_average`).
- **Optimal $k$ Selection:** Evaluates $k \in [3, 10]$ using **Silhouette Score** and **Elbow Inertia** analysis.
- **Cluster Semantic Naming:** Automatically names each cluster by its top-2 dominant genres (e.g., *"Drama + Romance"*, *"Action + Adventure"*).
- **2D PCA Projection:** Reduces high-dimensional genre and numeric space to 2 principal components saved to `static/images/pca_{lang}.png`.

### 2. Supervised Learning (Tracked) — Rating Prediction & Bridge Proof
- **Models:** Random Forest Regressor (100 estimators) and KNN Regressor ($k=10$, distance-weighted).
- **Core ML Hypothesis ("Bridge Proof"):** Does incorporating the unsupervised cluster ID improve supervised rating prediction?
  - **With Cluster:** Model uses one-hot genres + scaled metadata + **K-Means `cluster` label**.
  - **Without Cluster:** Model uses one-hot genres + scaled metadata (no cluster).
  - **Result:** Across every single language, the Random Forest model **With Cluster** achieves lower RMSE and higher $R^2$, proving unsupervised clustering discovers latent representations that directly aid supervised regression.

### 3. Content-Based & Regional Discovery
- **Cosine Similarity ("More Like This"):** Measures angle between movie feature vectors in multidimensional space.
- **Cross-Language Picks:** For users exploring beyond their native cinema, recommends the top-rated gems from Sandalwood, Bollywood, Tollywood, Kollywood, and Mollywood.

---

## 🔍 Multi-Language Search Engine

- **Native Script Search:** Supports Devanagari (`शोले`), Kannada (`ಕಾಂತಾರ`), Tamil (`விக்ரம்`), Telugu (`బాహుబలి`), and Malayalam (`ദൃശ്യം`).
- **Script Auto-Detection:** Uses Unicode range parsing to automatically detect Indic scripts (`kn`, `hi`, `ta`, `te`, `ml`).
- **Transliteration & Fuzzy Matching:** Uses `indic-transliteration` (ITRANS) and `rapidfuzz` token-set ratio to seamlessly match phonetic English inputs (`"kantara"`, `"bahubali"`, `"drishyam"`) against native script titles.
- **Voice Search:** Web Speech API integration configuring recognition language code (`kn-IN`, `hi-IN`, `ta-IN`, `te-IN`, `ml-IN`, `en-IN`) based on the active language.

---

## 🌟 JioHotstar-Style Full-Bleed Hero Banner & 3D Carousel Selector

CineStream features a **JioHotstar-style full-bleed cinematic hero banner** (`100vw`, ~`88vh`) with an integrated 3D poster carousel movie selector and trailer playback engine:

1. **Full-Bleed Cinematic Video Background:**
   - Displays high-resolution backdrop image immediately, followed by a smooth crossfade into a 16:9 scale-to-cover YouTube trailer preview after 1.2s.
   - Multi-stop linear gradients guarantee crisp text legibility on the left and seamless blending into the page below.

2. **Flat Hit-Testing Slots & 3D Card State Machine:**
   - **Zero Hover Jitter:** Non-transformed `.carousel-slot` wrappers handle cursor events (`pointerenter`, `pointerleave`, `click`) while GSAP independently animates the inner `.carousel-card-inner` across circular shortest offsets (`-2, -1, 0, +1, +2`).
   - **120ms Hover-Intent:** Hovering over any side card smoothly transitions it to the front as the active spotlight movie.
   - **Full UI in English:** All headlines, badges, metadata, tooltips, and navigation remain strictly in English.

3. **Cinematic Full Trailer Playback Mode:**
   - Clicking **"▶ Watch trailer"** or the active card's play button expands into full trailer mode with unmuted sound and custom cinematic controls:
     - Back to carousel (`← Back` or `Escape` key)
     - Play / Pause (toggle with button or `Space` key)
     - Interactive scrubber / progress bar with current & total time display
     - Volume slider with persistent `localStorage` level
     - Multilingual audio selector dropdown
     - Fullscreen toggle
     - Auto-restore to carousel upon video completion (`ENDED` event)

4. **Multi-Language Featured Movies (`ml/build_featured.py`):**
   - Automatically builds `data/featured_by_language.json` querying TMDB with `include_video_language='en,hi,kn,ta,te,ml,null'` to fetch verified regional trailers across all 6 languages.
   - The language switcher updates the hero carousel, recommendation rows, and browse catalog while keeping all interface text in English.

---

## 🌐 REST API Endpoints

| Endpoint | Method | Parameters | Description |
|---|---|---|---|
| `/api/featured` | GET | `lang` (`all`, `en`, `hi`, `kn`, `ta`, `te`, `ml`) | Returns featured movies with verified trailers, posters, backdrops, and ML cluster info |
| `/api/recommend/featured` | GET | `slug`, `all_langs`, `userId` | Returns dynamic recommendations for active featured movie (more like this + epic picks) |
| `/api/languages` | GET | — | Returns supported languages, native names, and industries |
| `/api/movies` | GET | `lang`, `category`, `page`, `per_page` | Paginated movie catalog with posters and bilingual titles |
| `/api/rate` | POST | `{movieId, userId, rating}` | Records session star ratings (0.5 to 5.0) |
| `/api/recommend` | GET | `userId`, `model`, `lang` | Top-6 predicted movies + cross-language regional picks |
| `/api/search` | GET | `q`, `lang` | Multi-language transliterated fuzzy search with script auto-detect |
| `/api/similar` | GET | `movieId`, `lang` | Cosine similarity recommendations ("More like this") |
| `/api/metrics` | GET | `lang` | Live model evaluation table (RMSE, MAE, $R^2$), cluster info, and PCA plot path |
| `/api/clusters` | GET | `lang` | Cluster breakdown, dominant genres, and movie counts |
| `/api/watchlist` | GET | `media_type`, `watched`, `sort_by` | Retrieve user's saved watchlist items |
| `/api/watchlist` | POST | `{tmdb_id, media_type, ...}` | Add item to user's watchlist |
| `/api/watchlist/<media_type>/<int:tmdb_id>` | DELETE | — | Remove single item from watchlist |
| `/api/watchlist/<media_type>/<int:tmdb_id>` | PATCH | `{watched, rating, position}` | Update watched status, user rating, or custom position |
| `/api/watchlist` | DELETE | — | Clear all items from user's watchlist |
| `/api/watchlist/reorder` | POST | `{items: [{tmdb_id, media_type, position}]}` | Batch persist custom drag-and-drop order |
| `/api/watchlist/recommend` | GET | `top_n` | Top-10 recommendations computed from user's watchlist taste centroid |
| `/api/watchlist/clusters` | GET | — | Cluster distribution data for Chart.js doughnut chart |

---


---

## 🔤 100% English Display (Latin Characters Only)

All movie titles, tags, and metadata throughout the user interface are guaranteed to be in the **Latin alphabet only**, eliminating native Indic scripts from display cards while allowing native script input during search:
- **Title Fallback Resolver (`ml/english_titles.py`):**
  1. TMDB English Title (`/movie/{id}?language=en-US`) — validated with `[A-Za-z]` regex.
  2. TMDB English Translations (`/movie/{id}/translations` with `iso_639_1 == "en"`).
  3. TMDB Alternative Titles (`iso_3166_1` US, GB, IN priority).
  4. Script transliteration (`indic-transliteration` + `pykakasi`).
  5. Title overrides (`data/title_overrides.json`) for known regional blockbusters (e.g. *K.G.F: Chapter 2*, *Kantara*, *Kaththi*, *Guru*, *Jawan*).
- **English-Only Typography:** Uses Google Font `Poppins` across all UI elements.
- **English Language Labels:** Displays full names like `2022 · Kannada` instead of 2-letter codes like `KN`.

---

## 🔖 "Add to Watchlist" & Dedicated Watchlist Page (`/watchlist`)

CineStream includes a complete Watchlist feature synchronized across all views without page reload:
- **Bookmark Buttons on All Cards:** Unsaved items show `+`; saved items show a gold bookmark icon (`🏷️`).
- **GSAP Animations:** Pop-and-spin on bookmark click, flying thumbnail clone to the navbar Watchlist link, navbar badge bump, and 4-second Undo toast.
- **Dedicated Watchlist Page (`/watchlist`):**
  - **Header & Search Filter:** Live title search and total item counter.
  - **Filter Toolbar:** Status tabs (*Saved*, *Watched*, *All*), media type pills (*Movies*, *TV Shows*, *Animation*, *Anime*), language dropdown, and sort options (*Recently Added*, *Title A-Z*, *Year*, *Rating*, *Custom Order*).
  - **SortableJS Drag-and-Drop:** Reorder saved movies seamlessly when "Custom Order" is selected; order is persisted to the database.
  - **Watched Switch & 5-Star Rating:** Mark movies as watched and rate them 1–5 stars to instantly update collaborative filtering predictions.
  - **Single Trailer Modal:** Uses the unified `PromoPlayer` controller for seamless playback.
  - **Export & Import JSON:** Back up your watchlist to `cinestream_watchlist.json` or restore from a file.
- **ML Integration (Taste Centroid & Implicit Feedback):**
  - **"Recommended from your Watchlist":** Computes the mathematical centroid of the feature vectors of all your saved movies and returns the top unseen films by cosine similarity with match percentage (`94% match`) and personalized *"Why this?"* explanations.
  - **Chart.js Doughnut Chart:** Interactive breakdown visualizing your saved collection across CineStream's K-Means clusters.
  - **Implicit Rating:** Unwatched saved titles feed into the recommender model with an implicit rating of 4.0, tracked in Model Insights.
- **Backend Storage:** Local SQLite database at `data/cinestream.db` with an anonymous 1-year HttpOnly cookie (`cinestream_uid`).

## ⚖️ Academic Project & Copyright Disclaimer

> **Student Project Disclaimer:** *Ramayana: Part 1* trailer, images, trademarks, and artwork belong to their respective copyright owners (Prime Focus Studios, Monster Mind Creations, DNEG, and director Nitesh Tiwari). This is a non-commercial student project created strictly for educational demonstration of machine learning techniques (K-Means Clustering, Random Forest Regression, Cosine Similarity, and Multi-Language Search).
>
> *This product uses the TMDB API but is not endorsed or certified by TMDB.*

---

## 🎓 Viva Q&A Cheat Sheet

**Q: Why train separate pipelines per language rather than just one global model?**
A: Different film industries have unique distribution dynamics — for instance, regional industries like Sandalwood (Kannada) or Mollywood (Malayalam) often feature distinct runtime norms, storytelling genres, and rating distributions compared to Hollywood. Per-language training tailors cluster boundaries ($k$) and regression hyperplanes to each culture, while our global model (`--lang all`) provides universal cross-industry discovery.

**Q: How does phonetic search for Indian languages work?**
A: When a user types a romanized query like *"bahubali"*, `indic-transliteration` translates native Telugu/Devanagari titles to the standard Roman alphabet (ITRANS). `RapidFuzz` then calculates the Levenshtein token-set similarity between the transliterated strings, enabling typo-tolerant matching across both scripts.

**Q: What is the significance of the "With Cluster" vs "Without Cluster" comparison?**
A: It empirically demonstrates **representation learning**. K-Means unsupervised clustering groups high-dimensional genre and metadata into dense thematic concepts. By injecting this cluster ID into Random Forest, the supervised tree splits leverage pre-learned structural clusters, measurably reducing RMSE.

**Q: What is the Silhouette Score and how was it used?**
A: Silhouette score measures cluster cohesion (distance between samples in the same cluster) vs separation (distance to the nearest neighboring cluster), bounded between $-1$ and $+1$. We run K-Means over $k \in [3, 10]$ and automatically select the $k$ that maximizes the silhouette coefficient.

**Q: What is the cold-start problem and how is it addressed?**
A: When a new user has rated zero films, collaborative filtering cannot make predictions. CineStream solves this by falling back to top-rated popular films within the user's selected language until their first rating is submitted, which immediately triggers the Random Forest / KNN inference pipeline.

