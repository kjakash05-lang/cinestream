import os
import requests
from dotenv import load_dotenv

try:
    import urllib3.util.connection as urllib_conn
    _orig_create_connection = urllib_conn.create_connection

    def _safe_create_connection(address, *args, **kwargs):
        host, port = address
        if host == "api.themoviedb.org":
            return _orig_create_connection(("3.175.86.37", port), *args, **kwargs)
        return _orig_create_connection(address, *args, **kwargs)

    urllib_conn.create_connection = _safe_create_connection
except Exception:
    pass

load_dotenv()
api_key = os.getenv("TMDB_API_KEY")
headers = {"User-Agent": "Mozilla/5.0"}

ids = [656908, 587412, 743563, 579974, 157336, 27205]
for mid in ids:
    try:
        url = f"https://api.themoviedb.org/3/movie/{mid}?api_key={api_key}&language=en-US"
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            print(f"{mid} -> title: {data.get('title')} | release_date: {data.get('release_date')} | poster_path: {data.get('poster_path')} | original_language: {data.get('original_language')}")
        else:
            print(f"{mid} -> Error {resp.status_code}")
    except Exception as e:
        print(f"{mid} -> Exception: {e}")
