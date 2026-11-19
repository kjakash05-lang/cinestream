import json
import pandas as pd

titles = ["Ramayana", "K.G.F", "Vikram", "RRR", "Interstellar", "Inception"]
df = pd.read_csv("data/movies_all.csv")
print("=== In movies_all.csv ===")
for t in titles:
    sub = df[df["title"].str.contains(t, case=False, na=False)]
    for _, r in sub.iterrows():
        print(f"{r['title']} | movieId={r.get('movieId')} | tmdb_id={r.get('tmdb_id')} | lang={r.get('lang')} | poster={r.get('poster_url')}")

print("\n=== In posters.json ===")
with open("data/posters.json", "r", encoding="utf-8") as f:
    pj = json.load(f)
for k, v in pj.items():
    for t in titles:
        if t.lower() in str(v.get("title", "")).lower():
            print(f"Key={k} | title={v.get('title')} | tmdbId={v.get('tmdbId')} | movieId={v.get('movieId')} | poster={v.get('poster_url')}")
