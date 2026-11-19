"""
download_data.py
Automatically downloads the MovieLens ml-latest-small dataset.
Run: python data/download_data.py
"""
import os
import zipfile
import shutil
import ssl
import urllib.request
import certifi
import requests

DATASET_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
ZIP_PATH = os.path.join(DATA_DIR, "ml-latest-small.zip")
EXTRACT_DIR = os.path.join(DATA_DIR, "ml-latest-small")

def download_dataset():
    if os.path.exists(os.path.join(DATA_DIR, "movies.csv")) and \
       os.path.exists(os.path.join(DATA_DIR, "ratings.csv")):
        print("[INFO] Dataset already exists in data/. Skipping download.")
        return

    print(f"[INFO] Downloading MovieLens ml-latest-small from:\n  {DATASET_URL}")
    
    # Use requests with stream for reliability and progress tracking
    try:
        response = requests.get(DATASET_URL, stream=True, timeout=30)
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 64 * 1024

        with open(ZIP_PATH, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = min(100.0, downloaded * 100 / total_size)
                        bar = "#" * int(pct // 2)
                        print(f"\r  [{bar:<50}] {pct:.1f}%", end="", flush=True)
        print("\n[INFO] Download complete. Extracting...")
    except Exception as e:
        print(f"\n[WARN] requests failed ({e}), falling back to urllib with unverified context...")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(DATASET_URL, context=ctx) as resp, open(ZIP_PATH, "wb") as out:
            shutil.copyfileobj(resp, out)
        print("[INFO] Fallback download complete. Extracting...")

    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        zf.extractall(DATA_DIR)

    # Move csv files to data/
    for fname in ["movies.csv", "ratings.csv", "tags.csv", "links.csv"]:
        src = os.path.join(EXTRACT_DIR, fname)
        dst = os.path.join(DATA_DIR, fname)
        if os.path.exists(src):
            shutil.move(src, dst)
            print(f"[INFO] Saved {fname} -> data/")

    # Cleanup temporary folders/archives
    if os.path.exists(EXTRACT_DIR):
        shutil.rmtree(EXTRACT_DIR)
    if os.path.exists(ZIP_PATH):
        os.remove(ZIP_PATH)

    print("[SUCCESS] MovieLens dataset ready in data/ folder!")

if __name__ == "__main__":
    download_dataset()
