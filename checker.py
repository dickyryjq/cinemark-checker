import requests
from bs4 import BeautifulSoup
import json
import os
import re

THEATER_URL = "https://www.cinemark.com/theatres/wa-kirkland/cinemark-totem-lake-kirkland-and-xd"
SEEN_FILE = "seen_movies.json"

CHINESE_KEYWORDS = [
    "chinese", "mandarin", "cantonese", "中文", "普通话", "粤语"
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def fetch_movies():
    resp = requests.get(THEATER_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    movies = {}

    # Cinemark embeds movie data as JSON in a <script> tag
    for script in soup.find_all("script", type="application/json"):
        try:
            data = json.loads(script.string)
            extract_from_json(data, movies)
        except Exception:
            pass

    # Also scan raw text of the page for movie+language info
    # Look for patterns like "Movie Title (Mandarin with Chinese Subtitles)"
    text = soup.get_text(" ", strip=True)
    for match in re.finditer(
        r'([A-Z][^\n(]{2,60})\s*\(([^)]*(?:' +
        '|'.join(CHINESE_KEYWORDS) +
        r')[^)]*)\)',
        text,
        re.IGNORECASE
    ):
        title = match.group(1).strip()
        lang_info = match.group(2).strip()
        movies[title] = lang_info

    return movies


def extract_from_json(data, movies, depth=0):
    """Recursively search JSON data for movie titles with Chinese language info."""
    if depth > 10:
        return
    if isinstance(data, dict):
        title = data.get("title") or data.get("name") or data.get("movieTitle", "")
        lang = (
            data.get("language") or data.get("subtitle") or
            data.get("languageInfo") or data.get("format", "")
        )
        combined = f"{title} {lang}".lower()
        if title and any(kw in combined for kw in CHINESE_KEYWORDS):
            movies[title] = str(lang)
        for v in data.values():
            extract_from_json(v, movies, depth + 1)
    elif isinstance(data, list):
        for item in data:
            extract_from_json(item, movies, depth + 1)


def main():
    seen = load_seen()
    movies = fetch_movies()

    new_movies = {t: l for t, l in movies.items() if t not in seen}

    if new_movies:
        print("NEW_MOVIES_FOUND")
        for title, lang in new_movies.items():
            print(f"  - {title} ({lang})")
        seen.update(new_movies.keys())
        save_seen(seen)
    else:
        print("NO_NEW_MOVIES")
        # Still update seen with currently showing movies
        # so removed+returned movies count as new again
        save_seen(seen | set(movies.keys()))


if __name__ == "__main__":
    main()
