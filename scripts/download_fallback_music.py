"""
Download CC0 fallback tracks from Internet Archive into assets/music/.
Run from backend/: python scripts/download_fallback_music.py
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

IA_SEARCH_URL = "https://archive.org/advancedsearch.php"
IA_DETAILS_URL = "https://archive.org/metadata/{identifier}"
IA_DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"
IA_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

MOOD_QUERIES = {
    "motivational": "motivational background instrumental",
    "chill": "chill lofi relaxing instrumental",
    "energy": "upbeat energetic hype instrumental",
    "uplifting": "uplifting happy positive instrumental",
    "cinematic": "cinematic dramatic epic instrumental",
}


def search_ia(query: str, max_results: int = 15) -> list[dict]:
    """Search Internet Archive for CC0 audio."""
    ia_query = f'({query}) AND mediatype:(audio) AND (licenseurl:(*publicdomain*) OR licenseurl:(*creativecommons*zero*))'
    params = {
        "q": ia_query,
        "fl[]": ["identifier", "title", "format"],
        "rows": max_results,
        "output": "json",
        "sort[]": "downloads desc",
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get(IA_SEARCH_URL, params=params, headers=IA_HEADERS)
            r.raise_for_status()
            docs = r.json().get("response", {}).get("docs", [])
            return docs
    except Exception as e:
        print(f"  Search failed: {e}")
        return []


def get_mp3_files(identifier: str) -> list[dict]:
    """Get MP3 file list from an IA item."""
    url = IA_DETAILS_URL.format(identifier=identifier)
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url, headers=IA_HEADERS)
            r.raise_for_status()
            metadata = r.json()
    except Exception as e:
        print(f"  Metadata failed: {e}")
        return []

    mp3s = []
    for info in metadata.get("files", []) or []:
        name = info.get("name", "")
        fmt = info.get("format", "").lower()
        if "mp3" in fmt or name.lower().endswith(".mp3"):
            clean_name = name.lstrip("/")
            size = int(info.get("size", 0))
            if 500_000 < size < 20_000_000:  # 0.5MB–20MB
                mp3s.append({
                    "name": clean_name,
                    "url": IA_DOWNLOAD_URL.format(identifier=identifier, filename=clean_name),
                })
    return mp3s


def download_mp3(url: str, out_path: Path) -> bool:
    """Download MP3 to path."""
    try:
        with httpx.Client(timeout=90.0, follow_redirects=True) as client:
            r = client.get(url, headers=IA_HEADERS)
            r.raise_for_status()
            out_path.write_bytes(r.content)
        return True
    except Exception as e:
        print(f"  Download failed: {e}")
        return False


def main():
    assets_dir = Path(__file__).parent.parent / "assets" / "music"
    assets_dir.mkdir(parents=True, exist_ok=True)
    print(f"Target: {assets_dir}\n")

    for mood, query in MOOD_QUERIES.items():
        out_file = assets_dir / f"{mood}_fallback.mp3"
        if out_file.exists():
            print(f"[{mood}] Already exists: {out_file.name}")
            continue

        print(f"[{mood}] Searching: '{query}'...")
        items = search_ia(query)
        if not items:
            print(f"  No results, trying broader search...")
            items = search_ia("background instrumental music")

        if not items:
            print(f"  Skipped (no CC0 results)")
            continue

        for item in items[:5]:
            identifier = item.get("identifier", "")
            mp3s = get_mp3_files(identifier)
            if not mp3s:
                continue
            # Pick middle-length track
            best = min(mp3s, key=lambda m: abs(len(m["name"]) - 30))
            print(f"  Downloading from {identifier}...")
            if download_mp3(best["url"], out_file):
                print(f"  OK -> {out_file.name}")
                break
        else:
            print(f"  Skipped (no usable MP3s)")

    print("\nDone.")
    existing = list(assets_dir.glob("*.mp3"))
    print(f"Tracks: {[f.name for f in existing]}")


if __name__ == "__main__":
    main()
