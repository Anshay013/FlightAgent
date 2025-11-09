from pydantic import BaseModel, field_validator
from typing import Optional, Literal

class FlightQuery(BaseModel):
    origin: str
    destination: str
    departDate: Optional[str] = None
    passengers: Optional[int] = 1
    cabinClass: Optional[str] = "Economy"
    currency: Optional[str] = "INR"
    limit: Optional[int] = 10
    minPrice: Optional[float] = None
    maxPrice: Optional[float] = None
    intent: Optional[str] = "cheapest"

    @field_validator("intent", mode="before")
    def validate_intent(cls, v):
        allowed = {"cheapest", "price_range", "earliest", "direct", "cabin_filter", "day_compare"}
        if v not in allowed:
            # fallback: log it, but don't break the system
            print(f"[Warning] Unrecognized intent '{v}', defaulting to 'cheapest'")
            return "cheapest"
        return v
