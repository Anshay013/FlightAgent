from typing import Dict
from .base_tool import call_mcp_search

def booking_search_tool(query: Dict):
    """
    Thin wrapper: accepts dict-like FlightQuery and returns the MCP results (list/dict).
    """
    return call_mcp_search(query)
