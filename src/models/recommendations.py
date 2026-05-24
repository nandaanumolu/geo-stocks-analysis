from pydantic import BaseModel, Field
from typing import Literal


class StockRecommendation(BaseModel):
    ticker: str
    company_name: str
    sector: str
    signal: Literal["BUY", "SELL", "HOLD"]
    confidence: float = Field(ge=0.0, le=100.0)
    reasoning: str
    time_horizon: Literal["short_term", "medium_term", "long_term"] = "medium_term"
    triggered_by: list[str] = Field(default_factory=list)
