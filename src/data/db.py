import os
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, Column, String, Float, Boolean, DateTime, Text, Integer, JSON
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DATABASE_URL = os.getenv("DATABASE_URL")
if _DATABASE_URL:
    # Render provides postgres:// but SQLAlchemy 2.x needs postgresql://
    _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(_DATABASE_URL, echo=False)
else:
    DB_PATH = Path(__file__).parent.parent.parent / "geo_stocks.db"
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)

Session = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class NewsCache(Base):
    __tablename__ = "news_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    country = Column(String(10), nullable=False, index=True)
    fetch_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    source = Column(String(200))
    published_at = Column(String(30))
    fetched_at = Column(DateTime, default=datetime.utcnow)


class RecommendationRun(Base):
    __tablename__ = "recommendation_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    country = Column(String(10), nullable=False)
    analysis_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    is_backtest = Column(Boolean, default=False)
    overall_sentiment = Column(String(20))
    key_events = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class StockRecommendationDB(Base):
    __tablename__ = "stock_recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False, index=True)
    ticker = Column(String(20), nullable=False)
    company_name = Column(String(200))
    sector = Column(String(50))
    signal = Column(String(10))  # BUY / SELL / HOLD
    confidence = Column(Float)
    reasoning = Column(Text)
    time_horizon = Column(String(20))
    entry_price = Column(Float)
    current_price = Column(Float)
    return_pct = Column(Float)
    correct_call = Column(Boolean)
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyPickLog(Base):
    __tablename__ = "daily_pick_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    ticker = Column(String(20), nullable=False)
    company_name = Column(String(200))
    signal = Column(String(10))        # BUY
    ref_price = Column(Float)          # last closing price at time of pick
    created_at = Column(DateTime, default=datetime.utcnow)


class PickDetail(Base):
    __tablename__ = "pick_detail"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(String(10), nullable=False, index=True)
    ticker = Column(String(20), nullable=False)
    company_name = Column(String(200))
    sector = Column(String(50))
    signal = Column(String(10))
    confidence = Column(Float)
    risk_level = Column(String(10))
    ref_price = Column(Float)
    predicted_return_min = Column(Float)
    predicted_return_max = Column(Float)
    stop_loss_pct = Column(Float)
    reasoning = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyLearning(Base):
    __tablename__ = "daily_learning"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(String(10), unique=True, nullable=False)
    hit_rate = Column(Float)
    avg_return_pct = Column(Float)
    total_picks = Column(Integer)
    what_worked = Column(Text)
    what_failed = Column(Text)
    lessons = Column(Text)   # JSON list of strings
    raw_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session():
    return Session()
