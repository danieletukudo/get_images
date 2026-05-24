import re
import sys
from urllib.parse import quote_plus

import requests
from playwright.sync_api import sync_playwright

CANDIDATE_LIMIT = 30

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_IMAGE_URL_PATTERN = re.compile(r'\["(https?://[^"]+)",\s*(\d+),\s*(\d+)\]')
_SKIP_DOMAINS = ("tiktok.com/api", "gstatic.com", "google.com")


def build_search_url(keyword: str) -> str:
    """Build Google Image search URL; spaces become '+'."""
    return f"https://www.google.com/search?q={quote_plus(keyword.strip())}&udm=2"


def fetch_page_html(url: str) -> str:
    """Load Google Images in a real browser (avoids captcha on plain requests)."""
    with sync_playwright() as playwright:
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
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=90_000)

        if "google.com/sorry" in page.url:
            browser.close()
            raise RuntimeError(
                "Google blocked the request (captcha). Try again in a few minutes."
            )

        html = page.content()
        browser.close()
        return html


def normalize_url(url: str) -> str:
    return url.replace("\\u003d", "=").replace("\\u0026", "&")


def is_image_url(url: str) -> bool:
    if any(skip in url for skip in _SKIP_DOMAINS):
        return False
    lower = url.lower()
    return any(
        ext in lower
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", "/upload", "/images/")
    )


def get_image_urls(search_url: str, limit: int = CANDIDATE_LIMIT) -> list[str]:
    html = fetch_page_html(search_url)

    images: list[str] = []
    seen: set[str] = set()
    for url, _, _ in _IMAGE_URL_PATTERN.findall(html):
        url = normalize_url(url)
        if url in seen or not is_image_url(url):
            continue
        seen.add(url)
        images.append(url)
        if len(images) >= limit:
            break

    return images


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

        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and not content_type.startswith("image/"):
            return False

        chunk = next(response.iter_content(512), None)
        return bool(chunk)
    except requests.RequestException:
        return False


def get_accessible_image_url(keyword: str) -> str | None:
    """Search Google Images and return the first URL that is actually openable."""
    search_url = build_search_url(keyword)
    candidates = get_image_urls(search_url)

    for url in candidates:
        if is_url_accessible(url):
            return url

    return None


def main() -> None:
    keyword = " ".join(sys.argv[1:]).strip() or input("Search for: ").strip()
    if not keyword:
        print("Search keyword required.")
        return

    print(f"Searching: {build_search_url(keyword)}")

    try:
        image_url = get_accessible_image_url(keyword)
    except Exception as exc:
        print(f"Search failed: {exc}")
        return

    if image_url:
        print(image_url)
    else:
        print("No accessible image link found.")


if __name__ == "__main__":
    main()
