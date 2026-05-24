import time
import requests
from datetime import date, timedelta
from src.models.events import NewsItem

_BASE_URL = "https://content.guardianapis.com/search"
_API_KEY = "test"  # Free public test key; set GUARDIAN_API_KEY env var for higher limits

# Query groups: global events that move Indian markets + India-specific policy events
_QUERY_GROUPS = [
    "India economy budget RBI interest rate rupee inflation",
    "India military border Pakistan China tension conflict",
    "India election Modi government policy reform",
    "crude oil OPEC Middle East price energy",
    "India trade sanctions tariff export import",
    "US Federal Reserve interest rate dollar emerging markets",
    "India defence spending HAL aerospace",
]

_RELEVANT_SECTIONS = {"world", "business", "money", "politics", "environment", "technology"}


def _fetch_query(query: str, start_str: str, end_str: str) -> list[NewsItem]:
    params = {
        "q": query,
        "from-date": start_str,
        "to-date": end_str,
        "page-size": 20,
        "api-key": _API_KEY,
        "order-by": "relevance",
        "show-fields": "headline,trailText",
    }
    try:
        r = requests.get(_BASE_URL, params=params, timeout=10)
        r.raise_for_status()
        results = r.json().get("response", {}).get("results", [])
        items = []
        for a in results:
            section = a.get("sectionName", "").lower()
            if any(s in section for s in _RELEVANT_SECTIONS):
                items.append(NewsItem(
                    title=a.get("webTitle", ""),
                    url=a.get("webUrl", ""),
                    source="theguardian.com",
                    published_at=a.get("webPublicationDate", ""),
                ))
        return items
    except Exception:
        return []


def fetch_geopolitical_news(
    country_code: str,
    target_date: date,
    window_days: int = 2,
) -> list[NewsItem]:
    """Fetch geo-political news from The Guardian for a date window around target_date."""
    start_str = (target_date - timedelta(days=window_days)).strftime("%Y-%m-%d")
    end_str = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

    seen_urls: set[str] = set()
    all_articles: list[NewsItem] = []

    for query in _QUERY_GROUPS:
        articles = _fetch_query(query, start_str, end_str)
        for a in articles:
            if a.url not in seen_urls and a.title:
                seen_urls.add(a.url)
                all_articles.append(a)
        time.sleep(0.1)  # Be polite to Guardian API

    return all_articles
