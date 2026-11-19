"""
config.py - CineStream Global Configuration and ML Constants
Defines weights, language mappings, avatar lists, and recommendation thresholds.
"""
import os

# Score blending weights for Personalized Recommendations
WEIGHT_RF = 0.40
WEIGHT_COSINE = 0.35
WEIGHT_CLUSTER = 0.15
WEIGHT_PREFERENCE = 0.10

# Multi-Modal Content Feature Block Weights (Feature Engineering)
FEATURE_WEIGHT_GENRES = 2.2
FEATURE_WEIGHT_KEYWORDS = 2.5
FEATURE_WEIGHT_CAST = 1.3
FEATURE_WEIGHT_DIRECTOR = 1.3
FEATURE_WEIGHT_LANGUAGE = 1.2
FEATURE_WEIGHT_DECADE = 0.8
FEATURE_WEIGHT_RUNTIME = 0.5
FEATURE_WEIGHT_OVERVIEW_SVD = 1.8

# K-Means Hyperparameters
KMEANS_K_MIN = 6
KMEANS_K_MAX = 20
SVD_COMPONENTS = 50

# Hybrid Collaborative / Content Blending Weights
HYBRID_CONTENT_WEIGHT = 0.55
HYBRID_COLLAB_WEIGHT = 0.45

# Thresholds for Hidden Gems
GEM_MIN_RATING = 7.2
GEM_POPULARITY_PERCENTILE = 0.40
GEM_VOTE_COUNT_PERCENTILE = 0.40

# Supported Languages & Display Config
LANGUAGES = {
    "all": {"name": "All", "native": "All", "industry": "Global Cinema", "speech_code": "en-US"},
    "en": {"name": "English", "native": "English", "industry": "Hollywood", "speech_code": "en-US"},
    "hi": {"name": "Hindi", "native": "Hindi", "industry": "Bollywood", "speech_code": "hi-IN"},
    "kn": {"name": "Kannada", "native": "Kannada", "industry": "Sandalwood", "speech_code": "kn-IN"},
    "ta": {"name": "Tamil", "native": "Tamil", "industry": "Kollywood", "speech_code": "ta-IN"},
    "te": {"name": "Telugu", "native": "Telugu", "industry": "Tollywood", "speech_code": "te-IN"},
    "ml": {"name": "Malayalam", "native": "Malayalam", "industry": "Mollywood", "speech_code": "ml-IN"},
    "ja": {"name": "Japanese", "native": "Japanese", "industry": "Japanese Cinema", "speech_code": "ja-JP"}
}

# Standard Genres
GENRES = [
    "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary",
    "Drama", "Family", "Fantasy", "History", "Horror", "Music",
    "Mystery", "Romance", "Science Fiction", "Thriller", "War", "Western"
]

# Preset Avatars
AVATARS = [
    {"id": "avatar-1", "label": "Classic Cinephile", "icon": "🎬", "color": "#e50914"},
    {"id": "avatar-2", "label": "Sci-Fi Explorer", "icon": "🚀", "color": "#00d2ff"},
    {"id": "avatar-3", "label": "Golden Era Critic", "icon": "🎭", "color": "#f5c518"},
    {"id": "avatar-4", "label": "Action Hero", "icon": "⚡", "color": "#ff5722"},
    {"id": "avatar-5", "label": "Midnight Binge Watcher", "icon": "🍿", "color": "#9c27b0"},
    {"id": "avatar-6", "label": "Mystery Sleuth", "icon": "🕵️", "color": "#4caf50"}
]
