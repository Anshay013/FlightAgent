import os
import time
import logging
import requests
from typing import Dict, Any, Optional
from exceptions import OrchestratorException

logger = logging.getLogger("base_tool")
logger.setLevel(logging.INFO)


def call_http_with_retry(
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    method: str = "POST",
    headers: Optional[Dict[str, str]] = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: int = 15,
) -> Dict[str, Any]:
    """
    Generic HTTP request wrapper with retry & exponential backoff.

    Args:
        url (str): The target API endpoint.
        payload (dict): The JSON body to send.
        method (str): HTTP method (POST or GET).
        headers (dict): HTTP headers.
        max_retries (int): Max retry attempts.
        base_delay (float): Base delay before retry (doubles each time).
        timeout (int): Timeout per request.

    Returns:
        dict: JSON response from server.

    Raises:
        OrchestratorException: If retries exhausted or non-retryable error.
    """
    if headers is None:
        headers = {"Content-Type": "application/json"}

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🌐 [{method}] {url} (Attempt {attempt}/{max_retries})")

            if method.upper() == "POST":
                response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            elif method.upper() == "GET":
                response = requests.get(url, params=payload, headers=headers, timeout=timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # ✅ Success
            if response.status_code == 200:
                logger.info("✅ Successful response received")
                return response.json()

            # ⚠️ Retryable errors
            elif response.status_code in (429, 502, 503, 504):
                wait = base_delay * (2 ** (attempt - 1))
                logger.warning(f"⚠️ Server returned {response.status_code}, retrying in {wait:.1f}s...")
                time.sleep(wait)
                continue

            # ❌ Non-retryable errors
            else:
                logger.error(f"❌ HTTP {response.status_code}: {response.text}")
                raise OrchestratorException(
                    message=f"Server returned {response.status_code}: {response.text}",
                    code="REMOTE_API_ERROR",
                    status_code=response.status_code,
                )

        except requests.exceptions.Timeout:
            wait = base_delay * (2 ** (attempt - 1))
            logger.warning(f"⏱ Timeout on attempt {attempt}, retrying in {wait:.1f}s...")
            time.sleep(wait)
            continue

        except requests.exceptions.ConnectionError as e:
            wait = base_delay * (2 ** (attempt - 1))
            logger.warning(f"🌐 Connection error: {e}. Retrying in {wait:.1f}s...")
            time.sleep(wait)
            continue

        except Exception as e:
            logger.exception(f"💥 Unexpected error calling {url}: {e}")
            raise OrchestratorException(
                message=f"Unexpected error: {str(e)}",
                code="HTTP_UNEXPECTED_ERROR"
            )

    logger.error(f"❌ All retries exhausted for {url}")
    raise OrchestratorException(
        message=f"Failed to reach {url} after {max_retries} retries.",
        code="REMOTE_API_UNAVAILABLE",
        status_code=503
    )
