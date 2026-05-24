from pydantic import BaseModel, Field
from typing import Literal


class NewsItem(BaseModel):
    title: str
    url: str
    source: str = ""
    published_at: str = ""


class SectorImpact(BaseModel):
    sector: str
    direction: Literal["positive", "negative", "neutral"]
    magnitude: Literal["low", "medium", "high"]
    reasoning: str


class GeoEvent(BaseModel):
    type: str
    description: str
    affected_sectors: list[SectorImpact] = Field(default_factory=list)
    time_horizon: Literal["short_term", "medium_term", "long_term"] = "medium_term"
    confidence: float = Field(ge=0.0, le=1.0)


class GeoAnalysis(BaseModel):
    events: list[GeoEvent] = Field(default_factory=list)
    overall_market_sentiment: Literal["bullish", "bearish", "neutral"] = "neutral"
    key_risks: list[str] = Field(default_factory=list)
