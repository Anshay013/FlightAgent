# tools/mcp_tool.py
from langchain.tools import tool
from tools.base_tool import call_mcp_search

import os
import time
import logging
import requests
from typing import Dict, Any
from langchain.tools import tool
from exceptions import OrchestratorException

# --- Logger ---
logger = logging.getLogger("mcp_tool")
logger.setLevel(logging.INFO)

# --- Configuration ---
MCP_HOST = os.getenv("MCP_HOST", "http://localhost:8080")
MCP_FLIGHT_ENDPOINT = f"{MCP_HOST}/v1/search/flights"


def _call_mcp_search_with_retry(flight_query: Dict[str, Any], max_retries: int = 3, base_delay: float = 1.0):
    """
    Calls MCP's /v1/search/flights endpoint with retries and exponential backoff.
    Returns the JSON response from MCP or raises an OrchestratorException.
    """
    headers = {"Content-Type": "application/json"}

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🚀 Calling MCP (Attempt {attempt}/{max_retries}) → {MCP_FLIGHT_ENDPOINT}")

            response = requests.post(MCP_FLIGHT_ENDPOINT, json=flight_query, headers=headers, timeout=15)

            # ✅ Handle successful response
            if response.status_code == 200:
                logger.info("✅ MCP responded successfully.")
                return response.json()

            # ⚠️ Handle retryable errors
            elif response.status_code in (429, 502, 503, 504):
                wait = base_delay * (2 ** (attempt - 1))
                logger.warning(f"⚠️ MCP responded with {response.status_code}. Retrying in {wait:.1f}s...")
                time.sleep(wait)
                continue

            # ❌ Non-retryable error
            else:
                error_body = response.text
                logger.error(f"❌ MCP returned HTTP {response.status_code}: {error_body}")
                raise OrchestratorException(
                    message=f"MCP returned HTTP {response.status_code}: {error_body}",
                    code="MCP_ERROR",
                    status_code=response.status_code,
                )

        except requests.exceptions.Timeout:
            wait = base_delay * (2 ** (attempt - 1))
            logger.warning(f"⏱️ Timeout contacting MCP (attempt {attempt}). Retrying in {wait:.1f}s...")
            time.sleep(wait)
            continue

        except requests.exceptions.ConnectionError as e:
            wait = base_delay * (2 ** (attempt - 1))
            logger.warning(f"🌐 MCP connection error: {e}. Retrying in {wait:.1f}s...")
            time.sleep(wait)
            continue

        except Exception as e:
            logger.exception(f"💥 Unexpected error calling MCP: {e}")
            raise OrchestratorException(
                message=f"Unexpected error while calling MCP: {str(e)}",
                code="MCP_UNEXPECTED_ERROR",
            )

    # ❌ All retries exhausted
    logger.error("❌ MCP service unreachable after retries.")
    raise OrchestratorException(
        message="MCP service not reachable after multiple retries.",
        code="MCP_UNAVAILABLE",
        status_code=503,
    )


# 🧠 LangChain @tool decorator — registered with the LLM agent
@tool("aggregate_flight_search_tool", return_direct=True)
def aggregate_flight_search_tool(flight_query: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tool for LangChain agent.
    Invokes the MCP microservice to fetch aggregated flight results using Amadeus API.

    Parameters
    ----------
    flight_query : dict
        Expected keys include:
          - origin (str)
          - destination (str)
          - departDate (str)
          - passengers (int)
          - cabinClass (str)
          - currency (str)
          - intent (str)
          - limit (int)
          - minPrice / maxPrice (optional)

    Returns
    -------
    dict
        The JSON response from MCP containing a list of flight results.
    """
    logger.info(f"🧩 aggregate_flight_search_tool invoked with: {flight_query}")

    # Validation sanity check
    if not flight_query.get("origin") or not flight_query.get("destination"):
        raise OrchestratorException("Origin and destination are required", code="INVALID_FLIGHT_QUERY", status_code=400)

    # Call MCP with retry logic
    response = _call_mcp_search_with_retry(flight_query)

    logger.info(f"✅ MCP returned {len(response) if isinstance(response, list) else 'some'} results")
    return response

