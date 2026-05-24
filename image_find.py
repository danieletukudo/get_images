import re
import sys
import time
from urllib.parse import quote_plus

import requests
from playwright.sync_api import sync_playwright

CANDIDATE_LIMIT = 30
GOOGLE_RETRIES = 3
RETRY_DELAY_SECONDS = 2

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_GOOGLE_IMAGE_PATTERN = re.compile(
    r'\["(https?://[^"]+)",\s*(\d+),\s*(\d+)\]'
)
_BING_MURL_PATTERNS = (
    re.compile(r'murl&quot;:&quot;(https?://[^&]+?)&quot;'),
    re.compile(r'"murl":"(https?://[^"]+)"'),
)
_SKIP_DOMAINS = ("tiktok.com/api", "gstatic.com", "google.com")
_BLOCKED_DOMAINS = (
    "xhcdn.com",
    "phncdn.com",
    "porn",
    "pixhost",
    "imagetwist",
    "adultempire",
    "redir.me",
    "vrporn",
    "pimpandhost",
    "ttcache.com",
)
_BLOCKED_URL_HINTS = ("sorry", "captcha", "recaptcha")
_JUNK_URL_FRAGMENTS = (
    "profile_images",
    "/logo",
    "favicon",
    "/icon",
    "avatar",
    "sprite",
    "1x1",
    "pixel",
)


def build_google_search_url(keyword: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(keyword.strip())}&udm=2"


def build_bing_search_url(keyword: str) -> str:
    return (
        f"https://www.bing.com/images/search"
        f"?q={quote_plus(keyword.strip())}&form=HDRSC2&first=1"
    )


def _launch_browser_page(playwright):
    launch_kwargs = {
        "headless": True,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    try:
        browser = playwright.chromium.launch(channel="chrome", **launch_kwargs)
    except Exception:
        browser = playwright.chromium.launch(**launch_kwargs)

    context = browser.new_context(
        user_agent=headers["User-Agent"],
        locale="en-US",
        viewport={"width": 1440, "height": 812},
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return browser, context.new_page()


def fetch_page_html(url: str, blocked_marker: str | None = None) -> str | None:
    """Load a search page in a browser. Returns None if blocked."""
    with sync_playwright() as playwright:
        browser, page = _launch_browser_page(playwright)
        page.goto(url, wait_until="networkidle", timeout=90_000)

        if blocked_marker and blocked_marker in page.url:
            browser.close()
            return None

        html = page.content()
        browser.close()
        return html


def normalize_url(url: str) -> str:
    return url.replace("\\u003d", "=").replace("\\u0026", "&")


def is_blocked_domain(url: str) -> bool:
    lower = url.lower()
    return any(domain in lower for domain in _BLOCKED_DOMAINS)


def is_image_url(url: str) -> bool:
    if any(skip in url for skip in _SKIP_DOMAINS):
        return False
    if is_blocked_domain(url):
        return False
    lower = url.lower()
    if any(junk in lower for junk in _JUNK_URL_FRAGMENTS):
        return False
    return any(
        ext in lower
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", "/upload", "/images/")
    )


def query_words(keyword: str) -> list[str]:
    return [
        word.lower()
        for word in re.findall(r"\w+", keyword)
        if len(word) > 2 and word.lower() not in {"and", "with", "the"}
    ]


def relevance_score(url: str, keyword: str) -> int:
    words = query_words(keyword)
    lower = url.lower()
    score = sum(1 for word in words if word in lower)
    if "wp-content/uploads" in lower:
        score += 2
    if "/recipes/" in lower or "recipe" in lower:
        score += 1
    return score


def _extract_google_candidates(
    html: str, limit: int
) -> list[tuple[str, int, int]]:
    candidates: list[tuple[str, int, int]] = []
    seen: set[str] = set()
    for url, width, height in _GOOGLE_IMAGE_PATTERN.findall(html):
        url = normalize_url(url)
        if url in seen or not is_image_url(url):
            continue
        seen.add(url)
        candidates.append((url, int(width), int(height)))
        if len(candidates) >= limit:
            break
    return candidates


def rank_google_candidates(
    candidates: list[tuple[str, int, int]], keyword: str
) -> list[str]:
    words = query_words(keyword)
    scored: list[tuple[str, int, int]] = []
    for url, width, height in candidates:
        if width * height < 40_000:
            continue
        lower = url.lower()
        relevance = sum(1 for word in words if word in lower)
        scored.append((url, relevance, width * height))

    scored.sort(key=lambda item: (item[1], item[2]), reverse=True)
    return [url for url, _, _ in scored]


def _extract_bing_urls(html: str, limit: int) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for pattern in _BING_MURL_PATTERNS:
        for match in pattern.findall(html):
            url = normalize_url(match.replace("&amp;", "&"))
            if url in seen or not url.startswith("http") or not is_image_url(url):
                continue
            seen.add(url)
            urls.append(url)
            if len(urls) >= limit:
                return urls
    return urls


def rank_bing_candidates(urls: list[str], keyword: str) -> list[str]:
    """Strict ranking for Bing — skip URLs that don't match the search."""
    words = query_words(keyword)
    min_relevance = min(2, len(words)) if words else 1

    scored: list[tuple[str, int]] = []
    for url in urls:
        lower = url.lower()
        if "/thumb/" in lower and any(size in lower for size in ("220px", "300px")):
            continue
        score = relevance_score(url, keyword)
        if score < min_relevance:
            continue
        scored.append((url, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return [url for url, _ in scored]


def get_google_image_urls(
    keyword: str, limit: int = CANDIDATE_LIMIT
) -> tuple[list[str], bool]:
    search_url = build_google_search_url(keyword)
    blocked_attempts = 0

    for attempt in range(GOOGLE_RETRIES):
        html = fetch_page_html(search_url, "google.com/sorry")
        if html is None:
            blocked_attempts += 1
            if attempt < GOOGLE_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
            continue

        candidates = _extract_google_candidates(html, limit)
        if candidates:
            return rank_google_candidates(candidates, keyword), False

        if attempt < GOOGLE_RETRIES - 1:
            time.sleep(RETRY_DELAY_SECONDS)

    return [], blocked_attempts == GOOGLE_RETRIES


def get_bing_image_urls(keyword: str, limit: int = CANDIDATE_LIMIT) -> list[str]:
    html = fetch_page_html(build_bing_search_url(keyword))
    if not html:
        return []
    urls = _extract_bing_urls(html, limit)
    return rank_bing_candidates(urls, keyword)


def get_image_candidates(keyword: str, limit: int = CANDIDATE_LIMIT) -> list[str]:
    """Google first; Bing via browser if Google is blocked or empty."""
    google_urls, google_blocked = get_google_image_urls(keyword, limit=limit)
    if google_urls:
        return google_urls
    if google_blocked or not google_urls:
        bing_urls = get_bing_image_urls(keyword, limit=limit)
        if bing_urls:
            return bing_urls
    return []


def is_url_accessible(url: str) -> bool:
    """Return True if the URL opens and returns an image."""
    request_headers = {
        **headers,
        "Referer": "https://www.google.com/",
        "Accept": "image/*,*/*",
    }

    try:
        response = requests.get(
            url,
            headers=request_headers,
            timeout=10,
            stream=True,
            allow_redirects=True,
        )
        if response.status_code != 200:
            return False

        final_url = response.url.lower()
        if any(hint in final_url for hint in _BLOCKED_URL_HINTS):
            return False

        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and not content_type.startswith("image/"):
            return False

        chunk = next(response.iter_content(512), None)
        return bool(chunk)
    except requests.RequestException:
        return False


def get_accessible_image_url(keyword: str) -> str | None:
    """Return the best openable image URL from Google or Bing."""
    candidates = get_image_candidates(keyword)

    for url in candidates:
        if is_url_accessible(url):
            return url

    return None


def main() -> None:
    keyword = " ".join(sys.argv[1:]).strip() or input("Search for: ").strip()
    if not keyword:
        print("Search keyword required.")
        return

    print(f"Searching: {build_google_search_url(keyword)}")

    image_url = get_accessible_image_url(keyword)
    if image_url:
        print(image_url)
    else:
        print("No accessible image link found.")


if __name__ == "__main__":
    main()
