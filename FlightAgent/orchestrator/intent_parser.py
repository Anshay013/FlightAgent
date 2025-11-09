import re
from datetime import date, timedelta, datetime
from typing import Dict, List, Optional

# Mapping for simple weekday recognition
WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2,
    "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
}

def parse_user_query(text: str) -> Dict:
    """
    Enhanced natural language parser for flight queries.
    Extracts origin, destination, dates, price range, airlines, time filters, and intent.
    Returns a dict usable directly for FlightQuery.
    """
    text_lower = text.lower()
    query: Dict = {}

    # --- 1️⃣ Origin & Destination ---
    m = re.search(r"from ([a-zA-Z\s]+) to ([a-zA-Z\s]+)", text_lower)
    if m:
        query["origin"] = m.group(1).strip().upper()
        query["destination"] = m.group(2).strip().upper()

    # --- 2️⃣ Date Handling ---
    today = date.today()
    if "today" in text_lower:
        query["departDate"] = today.isoformat()
    elif "tomorrow" in text_lower:
        query["departDate"] = (today + timedelta(days=1)).isoformat()
    elif "next weekend" in text_lower:
        # Next Saturday as depart, Sunday as return
        days_ahead = (5 - today.weekday()) % 7  # Saturday
        depart = today + timedelta(days=days_ahead)
        ret = depart + timedelta(days=1)
        query["departDate"] = depart.isoformat()
        query["returnDate"] = ret.isoformat()
    else:
        # Specific day names e.g. "Monday" or "Tuesday"
        for day_name, weekday_num in WEEKDAYS.items():
            if day_name in text_lower:
                days_ahead = (weekday_num - today.weekday()) % 7
                query["departDate"] = (today + timedelta(days=days_ahead)).isoformat()
                break

        # Specific calendar date e.g. "on 15th Nov" or "on 20 November"
        m = re.search(r"on (\d{1,2})(?:st|nd|rd|th)? (\w+)", text_lower)
        if m:
            try:
                d = int(m.group(1))
                month_str = m.group(2)
                depart_dt = datetime.strptime(f"{d} {month_str} {today.year}", "%d %B %Y").date()
                query["departDate"] = depart_dt.isoformat()
            except Exception:
                pass

    # --- 3️⃣ Round Trip ---
    if "return" in text_lower or "round trip" in text_lower:
        if "returnDate" not in query:
            # default: +3 days
            query["returnDate"] = (today + timedelta(days=3)).isoformat()

    # --- 4️⃣ Price Range ---
    m = re.search(r"between ?₹?(\d+) and ?₹?(\d+)", text_lower)
    if m:
        query["minPrice"] = float(m.group(1))
        query["maxPrice"] = float(m.group(2))
        query["intent"] = "price_range"
    elif "under" in text_lower or "below" in text_lower:
        m = re.search(r"(?:under|below) ?₹?(\d+)", text_lower)
        if m:
            query["maxPrice"] = float(m.group(1))
            query["intent"] = "price_range"
    elif "above" in text_lower or "over" in text_lower:
        m = re.search(r"(?:above|over) ?₹?(\d+)", text_lower)
        if m:
            query["minPrice"] = float(m.group(1))
            query["intent"] = "price_range"

    # --- 5️⃣ Time filters (after/before specific time) ---
    m = re.search(r"after (\d{1,2})(?:[:\.](\d{2}))?\s*(am|pm)?", text_lower)
    if m:
        hour = int(m.group(1))
        if m.group(3) == "pm" and hour < 12:
            hour += 12
        query["departAfter"] = f"{hour:02d}:00"
    m = re.search(r"before (\d{1,2})(?:[:\.](\d{2}))?\s*(am|pm)?", text_lower)
    if m:
        hour = int(m.group(1))
        if m.group(3) == "pm" and hour < 12:
            hour += 12
        query["departBefore"] = f"{hour:02d}:00"

    # --- 6️⃣ Airline preference ---
    airline_keywords = ["emirates", "air india", "indigo", "qatar", "lufthansa", "spicejet"]
    for airline in airline_keywords:
        if airline in text_lower:
            query["airline"] = airline.title()
            query["intent"] = "airline_filter"

    # --- 7️⃣ Stops ---
    if "nonstop" in text_lower or "non-stop" in text_lower or "direct" in text_lower:
        query["stops"] = 0
        query["intent"] = "direct"
    elif "1-stop" in text_lower or "one stop" in text_lower:
        query["stops"] = 1

    # --- 8️⃣ Cabin ---
    if "business" in text_lower:
        query["cabinClass"] = "Business"
        query["intent"] = "cabin_filter"
    elif "premium economy" in text_lower:
        query["cabinClass"] = "Premium Economy"
        query["intent"] = "cabin_filter"
    elif "economy" in text_lower:
        query["cabinClass"] = "Economy"

    # --- 9️⃣ Multi-day compare ---
    if "compare" in text_lower and any(day in text_lower for day in WEEKDAYS.keys()):
        query["intent"] = "day_compare"

    # --- 🔟 Cheap fallback intent ---
    if "cheap" in text_lower or "lowest" in text_lower or "affordable" in text_lower:
        query["intent"] = "cheapest"

    # --- 1️⃣1️⃣ Numeric limits ---
    m = re.search(r"(\d+)\s*(cheapest|flights)", text_lower)
    if m:
        query["limit"] = int(m.group(1))

    # --- 1️⃣2️⃣ Default fallback intent ---
    if "intent" not in query:
        query["intent"] = "cheapest"

    return query
