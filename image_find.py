"""Find a food image URL via SerpAPI Google Images search."""

import logging
import os
import re
import sys
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "").strip()
CANDIDATE_LIMIT = 10
API_URL = "https://serpapi.com/search.json"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/*,*/*",
    "Referer": "https://www.google.com/",
}

_BLOCKED_DOMAINS = (
    "porn", "xhcdn.com", "phncdn.com", "xhamster", "xvideos", "xnxx",
    "redtube", "youporn", "spankbang", "pornhub", "onlyfans",
    "pixhost", "imagetwist", "adultempire", "vrporn", "pimpandhost",
)


class SerpApiNotConfiguredError(RuntimeError):
    """Raised when SERPAPI_KEY is missing."""


def _add_food_context(keyword: str) -> str:
    food_words = {
        "food", "dish", "recipe", "meal", "cuisine", "soup", "stew",
        "salad", "rice", "bread", "cake", "cooking", "cook", "plate",
    }
    lower = keyword.lower()
    if set(lower.split()) & food_words:
        return keyword.strip()
    return f"{keyword.strip()} food"


def is_blocked_url(url: str) -> bool:
    lower = url.lower()
    return any(blocked in lower for blocked in _BLOCKED_DOMAINS)


def query_words(keyword: str) -> list[str]:
    return [
        w.lower()
        for w in re.findall(r"\w+", keyword)
        if len(w) > 2 and w.lower() not in {"and", "with", "the", "for", "food"}
    ]


def relevance_score(url: str, keyword: str) -> int:
    words = query_words(keyword)
    lower = url.lower()
    score = sum(1 for w in words if w in lower)
    if "wp-content/uploads" in lower or "/uploads/" in lower:
        score += 2
    if "recipe" in lower or "food" in lower:
        score += 1
    return score


def search_google_images(keyword: str, limit: int = CANDIDATE_LIMIT) -> list[str]:
    """Search Google Images via SerpAPI."""
    if not SERPAPI_KEY:
        raise SerpApiNotConfiguredError(
            "Set SERPAPI_KEY environment variable. Get one at https://serpapi.com/"
        )

    query = _add_food_context(keyword)
    params = {
        "engine": "google_images",
        "q": query,
        "api_key": SERPAPI_KEY,
        "safe": "active",
        "num": min(limit, 10),
    }

    response = requests.get(API_URL, params=params, timeout=20)
    if response.status_code == 401:
        raise RuntimeError("SerpAPI key is invalid.")
    if response.status_code == 429:
        raise RuntimeError("SerpAPI monthly quota exceeded (100 free/month).")
    response.raise_for_status()

    data = response.json()
    if data.get("error"):
        raise RuntimeError(data["error"])

    urls: list[str] = []
    for item in data.get("images_results", []):
        link = (item.get("original") or item.get("link") or "").strip()
        if not link.startswith("http"):
            continue
        if is_blocked_url(link):
            continue
        urls.append(link)

    urls.sort(key=lambda u: relevance_score(u, keyword), reverse=True)
    return urls


def is_url_accessible(url: str) -> bool:
    try:
        response = requests.get(
            url, headers=_HEADERS, timeout=10, stream=True, allow_redirects=True
        )
        if response.status_code != 200:
            return False
        if is_blocked_url(response.url):
            return False
        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and not content_type.startswith("image/"):
            return False
        chunk = next(response.iter_content(512), None)
        return bool(chunk)
    except requests.RequestException:
        return False


def get_accessible_image_url(keyword: str) -> str | None:
    """Return the first openable, relevant image URL for *keyword*."""
    candidates = search_google_images(keyword)
    for url in candidates:
        if is_url_accessible(url):
            return url
    return None


def main() -> None:
    keyword = " ".join(sys.argv[1:]).strip() or input("Search for: ").strip()
    if not keyword:
        print("Search keyword required.")
        return

    try:
        url = get_accessible_image_url(keyword)
    except SerpApiNotConfiguredError as exc:
        print(f"Error: {exc}")
        return
    except RuntimeError as exc:
        print(f"Error: {exc}")
        return

    if url:
        print(url)
    else:
        print("No accessible image link found.")


if __name__ == "__main__":
    main()
