import socket
socket.setdefaulttimeout(4)
import urllib.request, json

candidates = {
    "kantara": {"kn": "8mrVmf239GU", "hi": "6oKFao0aISA", "te": "axBF-4nNZ3s", "ta": "gKJMgeEvSyE", "ml": "qGWJSY9UXZ0"},
    "ramayana-part-1": {"hi": "1zip1rNaNYs", "en": "74nF-FWAS6M", "te": "bL5CBbMQghQ", "ta": "K7zjRJ_0sgk", "kn": "edgXQeM6uO8", "ml": "U05xJjT0aoc"},
    "brahmastra-part-one-shiva": {"hi": "V5jVntRVl-0", "te": "l54jYAncjdw", "ta": "mhPb6wxXAfM", "kn": "cM-z9kZwOAw", "ml": "LAr8_zIsFPE"},
    "sapta-sagaradaache-ello-side-a": {"kn": "hcJ1ZHHahMA"}
}

for slug, trailers in candidates.items():
    print(f"=== {slug} ===")
    for lang, vid in trailers.items():
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                data = json.loads(r.read().decode("utf-8"))
                print(f"  [{lang}] {vid} -> OK ({data.get('title')[:35]})")
        except Exception as e:
            print(f"  [{lang}] {vid} -> FAILED ({e})")
