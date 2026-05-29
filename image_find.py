"""Find a food image URL via Serper.dev Google Images API."""

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

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "").strip()
CANDIDATE_LIMIT = 10
API_URL = "https://google.serper.dev/images"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/*,*/*",
    "Referer": "https://www.google.com/",
}

_FOOD_DOMAINS = (
    "seriouseats.com", "allrecipes.com", "epicurious.com", "foodnetwork.com",
    "simplyrecipes.com", "bonappetit.com", "africanbites.com", "weeatatlast.com",
    "cheflolaskitchen.com", "allnigerianfoods.com", "wikipedia.org",
    "wp-content/uploads", "assets.epicurious.com",
)

_BLOCKED_DOMAINS = (
    "porn", "xhcdn.com", "phncdn.com", "xhamster", "xvideos", "xnxx",
    "redtube", "youporn", "spankbang", "pornhub", "onlyfans",
)


class SerperNotConfiguredError(RuntimeError):
    """Raised when SERPER_API_KEY is missing."""


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


def relevance_score(url: str, keyword: str, title: str = "", domain: str = "") -> int:
    words = query_words(keyword)
    text = f"{url} {title} {domain}".lower()
    score = sum(1 for w in words if w in text)
    if any(safe in url.lower() for safe in _FOOD_DOMAINS):
        score += 3
    if "recipe" in text or "soup" in text or "food" in text:
        score += 1
    return score


def search_google_images(keyword: str, limit: int = CANDIDATE_LIMIT) -> list[str]:
    """Search Google Images via Serper.dev."""
    if not SERPER_API_KEY:
        raise SerperNotConfiguredError(
            "Set SERPER_API_KEY environment variable. Get one at https://serper.dev/"
        )

    query = _add_food_context(keyword)
    response = requests.post(
        API_URL,
        headers={
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json",
        },
        json={"q": query, "num": min(limit, 10)},
        timeout=20,
    )

    if response.status_code == 401:
        raise RuntimeError("Serper API key is invalid.")
    if response.status_code == 429:
        raise RuntimeError("Serper API quota exceeded.")
    response.raise_for_status()

    data = response.json()
    scored: list[tuple[str, int]] = []

    for item in data.get("images", []):
        url = (item.get("imageUrl") or "").strip()
        if not url.startswith("http") or is_blocked_url(url):
            continue
        score = relevance_score(
            url,
            keyword,
            title=item.get("title", ""),
            domain=item.get("domain", ""),
        )
        scored.append((url, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [url for url, _ in scored]


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
    # If hotlink checks fail, return best Serper result (frontend can still display)
    return candidates[0] if candidates else None


def main() -> None:
    keyword = " ".join(sys.argv[1:]).strip() or input("Search for: ").strip()
    if not keyword:
        print("Search keyword required.")
        return

    try:
        url = get_accessible_image_url(keyword)
    except SerperNotConfiguredError as exc:
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
