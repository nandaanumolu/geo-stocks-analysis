import time
from datetime import date, timedelta
from gdeltdoc import GdeltDoc, Filters
from gdeltdoc.errors import RateLimitError
from src.models.events import NewsItem

_gd = GdeltDoc()

# Single focused query — one GDELT call per fetch to stay well within rate limits
_KEYWORD_QUERY = (
    "India (military OR border OR conflict OR sanctions OR "
    "election OR policy OR tariff OR ceasefire OR diplomacy OR war OR RBI OR budget)"
)

_RATE_LIMIT_WAIT = 10  # seconds between retries
_MAX_RETRIES = 2


def fetch_geopolitical_news(
    country_code: str,
    target_date: date,
    window_days: int = 2,
) -> list[NewsItem]:
    """Fetch geo-political news articles from GDELT for a date window around target_date."""
    start = (target_date - timedelta(days=window_days)).strftime("%Y-%m-%d")
    end = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

    for attempt in range(_MAX_RETRIES):
        try:
            f = Filters(
                keyword=_KEYWORD_QUERY,
                start_date=start,
                end_date=end,
                num_records=50,
            )
            df = _gd.article_search(f)
            break
        except RateLimitError:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RATE_LIMIT_WAIT)
            else:
                return []
        except Exception:
            return []
    else:
        return []

    if df is None or df.empty:
        return []

    seen_urls: set[str] = set()
    articles: list[NewsItem] = []
    for _, row in df.iterrows():
        url = str(row.get("url", ""))
        title = str(row.get("title", ""))
        if url not in seen_urls and title:
            seen_urls.add(url)
            articles.append(NewsItem(
                title=title,
                url=url,
                source=str(row.get("domain", "")),
                published_at=str(row.get("seendate", "")),
            ))

    return articles
