import os
import time
import logging
import requests
from exceptions import OrchestratorException
from typing import Dict

logger = logging.getLogger(__name__)

# In docker-compose the MCP service name is 'mcp' (hostname). For local dev use http://localhost:8080
MCP_HOST = os.getenv("MCP_HOST", "http://localhost:8080")

def call_mcp_search(flight_query: dict, max_retries: int = 3, base_delay: float = 1.0):
    """
    Calls the Spring Boot MCP flight search endpoint with retry & exponential backoff.
    - max_retries: how many times to retry on failure
    - base_delay: initial wait before retry, doubles each retry
    """
    url = f"{MCP_HOST}/v1/search/flights"
    headers = {"Content-Type": "application/json"}

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🔁 Calling MCP (Attempt {attempt}/{max_retries}) → {url}")

            response = requests.post(url, json=flight_query, headers=headers, timeout=10)

            # Handle success
            if response.status_code == 200:
                return response.json()

            # Handle common transient errors (retryable)
            elif response.status_code in (429, 502, 503, 504):
                wait = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"⚠️ MCP responded with {response.status_code}. Retrying in {wait:.1f}s..."
                )
                time.sleep(wait)
                continue

            # Non-retryable errors
            else:
                logger.error(f"❌ MCP responded with {response.status_code}: {response.text}")
                raise OrchestratorException(
                    message=f"MCP returned HTTP {response.status_code}: {response.text}",
                    code="MCP_ERROR",
                    status_code=response.status_code,
                )

        except requests.exceptions.Timeout:
            wait = base_delay * (2 ** (attempt - 1))
            logger.warning(f"⏱ MCP timeout (attempt {attempt}). Retrying in {wait:.1f}s...")
            time.sleep(wait)
            continue

        except requests.exceptions.ConnectionError as e:
            wait = base_delay * (2 ** (attempt - 1))
            logger.warning(f"🌐 MCP connection error: {e}. Retrying in {wait:.1f}s...")
            time.sleep(wait)
            continue

        except Exception as e:
            logger.exception(f"❌ Unexpected error calling MCP: {e}")
            raise OrchestratorException(
                message=f"Unexpected error while calling MCP: {str(e)}",
                code="MCP_UNEXPECTED_ERROR"
            )

    # If we exhausted all retries
    logger.error("❌ MCP not reachable after retries.")
    raise OrchestratorException(
        message="MCP service not reachable after multiple retries.",
        code="MCP_UNAVAILABLE",
        status_code=503
    )
