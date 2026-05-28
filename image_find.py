"""Find a food image URL via Google Custom Search JSON API (image search)."""

import logging
import os
import re
import sys

import requests

logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "").strip()
GOOGLE_CX = os.environ.get("GOOGLE_CX", "96354acc97e1a4c5e").strip()
CANDIDATE_LIMIT = 10
API_URL = "https://www.googleapis.com/customsearch/v1"

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


class GoogleApiNotConfiguredError(RuntimeError):
    """Raised when GOOGLE_API_KEY is missing."""


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
    """Call Google Custom Search API (image search)."""
    if not GOOGLE_API_KEY:
        raise GoogleApiNotConfiguredError(
            "Set GOOGLE_API_KEY environment variable (Google Cloud API key)."
        )

    query = _add_food_context(keyword)
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CX,
        "q": query,
        "searchType": "image",
        "num": min(limit, 10),
        "safe": "active",
        "imgSize": "large",
        "imgType": "photo",
    }

    response = requests.get(API_URL, params=params, timeout=15)
    if response.status_code == 403:
        logger.error("Google API 403: %s", response.text[:500])
        raise RuntimeError("Google API access denied. Check API key and billing.")
    if response.status_code == 429:
        logger.error("Google API quota exceeded")
        raise RuntimeError("Google API daily quota exceeded (100 free/day).")
    response.raise_for_status()

    data = response.json()
    urls: list[str] = []
    for item in data.get("items", []):
        link = item.get("link", "").strip()
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
    except GoogleApiNotConfiguredError as exc:
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
