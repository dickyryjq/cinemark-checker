import requests
from bs4 import BeautifulSoup
import json
import os
import re

THEATER_URL = "https://www.cinemark.com/theatres/wa-kirkland/cinemark-totem-lake-kirkland-and-xd"
SEEN_FILE = "seen_movies.json"

CHINESE_KEYWORDS = ["chinese", "mandarin", "cantonese", "中文", "普通话", "粤语"]

# UI noise that should never appear in a movie title
NOISE_WORDS = ["add to watch", "watch list", "descriptive narration", "closed caption",
               "buy ticket", "showtimes", "select", "trailer"]

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


def has_chinese(text):
    return any(kw in text.lower() for kw in CHINESE_KEYWORDS)


def is_noisy(text):
    return any(noise in text.lower() for noise in NOISE_WORDS)


def fetch_movies():
    resp = requests.get(THEATER_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    movies = {}

    # Strategy 1: Parse Next.js __NEXT_DATA__ JSON (most reliable)
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data:
        try:
            data = json.loads(next_data.string)
            extract_from_json(data, movies)
        except Exception:
            pass

    # Strategy 2: Parse any application/json script tags
    if not movies:
        for script in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script.string)
                extract_from_json(data, movies)
            except Exception:
                pass

    # Strategy 3: Look for clean "Title (language)" patterns in the HTML
    # Target specific HTML elements that contain movie titles
    if not movies:
        # Look for movie title elements (h2, h3, strong, or data-* attributes)
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "span", "p", "div"]):
            text = tag.get_text(" ", strip=True)
            # Skip long blocks of text (likely page sections, not titles)
            if len(text) > 120:
                continue
            if has_chinese(text) and not is_noisy(text):
                # Clean up: extract the meaningful part
                match = re.search(
                    r'([A-Z][^(\n]{1,60}?)\s*\(([^)]*(?:'
                    + '|'.join(CHINESE_KEYWORDS)
                    + r')[^)]*)\)',
                    text,
                    re.IGNORECASE
                )
                if match:
                    title = match.group(1).strip().rstrip("Add to Watch List").strip()
                    lang_info = match.group(2).strip()
                    if not is_noisy(title) and len(title) > 1:
                        movies[title] = lang_info

    return movies


def extract_from_json(data, movies, depth=0):
    """Recursively search JSON data for movie titles with Chinese language info."""
    if depth > 15:
        return
    if isinstance(data, dict):
        title = (
            data.get("title") or data.get("name") or
            data.get("movieTitle") or data.get("movieName") or ""
        )
        lang = " ".join(filter(None, [
            data.get("language", ""),
            data.get("languageInfo", ""),
            data.get("subtitle", ""),
            data.get("format", ""),
            data.get("attributes", ""),
        ]))
        if not lang:
            # Some APIs embed it in the title string: "Pegasus 3 (Mandarin...)"
            m = re.search(r'\(([^)]+)\)$', title)
            if m:
                lang = m.group(1)
                title = title[:m.start()].strip()

        if title and has_chinese(f"{title} {lang}") and not is_noisy(title):
            movies[title] = lang or "(Chinese language)"

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
    else:
        print("NO_NEW_MOVIES")

    # Always save — update seen with currently showing movies
    save_seen(seen | set(movies.keys()))


if __name__ == "__main__":
    main()
