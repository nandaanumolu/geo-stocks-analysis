from datetime import date
import feedparser
from src.data import gdelt_client, guardian_client
from src.data.db import get_session, NewsCache, init_db
from src.models.events import NewsItem

COUNTRY_RSS_FEEDS = {
    "IN": [
        "https://feeds.feedburner.com/ndtvnews-india-news",
        "https://www.thehindu.com/news/international/feeder/default.rss",
        "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
    ]
}

_GEO_KEYWORDS = {
    "tension", "conflict", "border", "sanctions", "trade", "military", "war",
    "election", "coup", "protest", "strike", "policy", "tariff", "embargo",
    "nuclear", "ceasefire", "diplomacy", "treaty", "invasion", "standoff",
    "parliament", "government", "minister", "prime minister", "president",
    "budget", "rbi", "fed", "rate", "inflation", "gdp", "crude", "oil",
    "rupee", "dollar", "defence", "defense", "geopolitical", "sanction",
}


def _is_geopolitical(title: str) -> bool:
    lower = title.lower()
    return any(kw in lower for kw in _GEO_KEYWORDS)


def _fetch_rss_news(country_code: str) -> list[NewsItem]:
    feeds = COUNTRY_RSS_FEEDS.get(country_code, [])
    items: list[NewsItem] = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                title = getattr(entry, "title", "")
                link = getattr(entry, "link", "")
                source = feed.feed.get("title", url)
                published = getattr(entry, "published", "")
                if title and _is_geopolitical(title):
                    items.append(NewsItem(title=title, url=link, source=source, published_at=published))
        except Exception:
            continue
    return items


def _cache_articles(country: str, target_date: date, articles: list[NewsItem]) -> None:
    session = get_session()
    try:
        date_str = target_date.isoformat()
        existing = session.query(NewsCache).filter_by(country=country, fetch_date=date_str).count()
        if existing > 0:
            return
        for a in articles:
            session.add(NewsCache(
                country=country,
                fetch_date=date_str,
                title=a.title,
                url=a.url,
                source=a.source,
                published_at=a.published_at,
            ))
        session.commit()
    finally:
        session.close()


def _load_from_cache(country: str, target_date: date) -> list[NewsItem]:
    session = get_session()
    try:
        rows = session.query(NewsCache).filter_by(
            country=country,
            fetch_date=target_date.isoformat()
        ).all()
        return [NewsItem(title=r.title, url=r.url, source=r.source or "", published_at=r.published_at or "") for r in rows]
    finally:
        session.close()


def get_news(country_code: str, target_date: date, live: bool = False) -> list[NewsItem]:
    """Fetch geo-political news for a country on a given date.

    live=True  → RSS feeds → GDELT fallback (today's news)
    live=False → SQLite cache → Guardian API → GDELT fallback (historical)
    """
    init_db()

    if live:
        rss = _fetch_rss_news(country_code)
        if rss:
            return rss
        # RSS failed (paywalls/network) — use Guardian for today
        articles = guardian_client.fetch_geopolitical_news(country_code, target_date)
        if articles:
            return articles
        # Last resort: GDELT (rate-limited but works for recent dates)
        articles = gdelt_client.fetch_geopolitical_news(country_code, target_date)
        return articles

    # Historical path: check cache first
    cached = _load_from_cache(country_code, target_date)
    if cached:
        return cached

    # Guardian API: works for any date back to 1999
    articles = guardian_client.fetch_geopolitical_news(country_code, target_date)

    # Supplement with GDELT for recent dates (last ~90 days)
    from datetime import date as _date
    from datetime import timedelta
    if (_date.today() - target_date).days <= 90:
        gdelt_articles = gdelt_client.fetch_geopolitical_news(country_code, target_date)
        seen = {a.url for a in articles}
        articles += [a for a in gdelt_articles if a.url not in seen]

    if articles:
        _cache_articles(country_code, target_date, articles)

    return articles
