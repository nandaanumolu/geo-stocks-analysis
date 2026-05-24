from datetime import date, timedelta
import yfinance as yf
import pandas as pd

NIFTY50_TICKER = "^NSEI"


def _extract_close_series(df: pd.DataFrame) -> pd.Series:
    """Handle both flat and MultiIndex column DataFrames from yfinance."""
    if df.empty:
        return pd.Series(dtype=float)
    cols = df.columns
    # MultiIndex: columns are tuples like ('Close', 'TICKER')
    if isinstance(cols, pd.MultiIndex):
        close_cols = [c for c in cols if c[0] == "Close"]
        if not close_cols:
            return pd.Series(dtype=float)
        return df[close_cols[0]].dropna()
    # Flat columns
    if "Close" in cols:
        return df["Close"].dropna()
    return pd.Series(dtype=float)


def _next_trading_day_price(ticker: str, target: date, lookahead: int = 5) -> float | None:
    """Fetch closing price on or after target date, skipping non-trading days."""
    end = target + timedelta(days=lookahead + 1)
    df = yf.download(ticker, start=target.isoformat(), end=end.isoformat(), progress=False, auto_adjust=True)
    series = _extract_close_series(df)
    if series.empty:
        return None
    return float(series.iloc[0])


def get_price_on_date(ticker: str, target: date) -> float | None:
    """Return closing price for ticker on or after target date."""
    return _next_trading_day_price(ticker, target)


def get_current_price(ticker: str) -> float | None:
    """Return the most recent available closing price."""
    df = yf.download(ticker, period="5d", progress=False, auto_adjust=True)
    series = _extract_close_series(df)
    if series.empty:
        return None
    return float(series.iloc[-1])


def get_price_series(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Return OHLCV DataFrame for ticker between start and end dates."""
    return yf.download(ticker, start=start.isoformat(), end=end.isoformat(), progress=False, auto_adjust=True)


def get_nifty50_return(start: date, end: date) -> float | None:
    """Return Nifty 50 % return between start and end dates."""
    df = get_price_series(NIFTY50_TICKER, start, end)
    closes = _extract_close_series(df)
    if len(closes) < 2:
        return None
    entry = float(closes.iloc[0])
    current = float(closes.iloc[-1])
    return round((current - entry) / entry * 100, 2)
