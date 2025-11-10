import os
import json
import asyncio
import re
import logging
import requests                     
from typing import Optional, Dict, Any, List  
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv
import openai

# Local imports
from models.flight_models import FlightQuery
from tools.base_tool import call_mcp_search
from redis_memory import append_message, get_history
from intent_parser import parse_user_query



# --- Optional tracing ---
from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from tools.mcp_tool import aggregate_flight_search_tool
from langchain.agents import initialize_agent, AgentType
from langchain_openai import ChatOpenAI




# Load env vars
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY", "")


# Initialize the LLM (GPT model)
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.3,
    openai_api_key=openai.api_key
)

# Register available tools
tools = [aggregate_flight_search_tool]

# Create the LangChain agent
agent = initialize_agent(
    tools=tools,
    llm=llm,
    agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True,
)



tracer = trace.get_tracer(__name__)
otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
if otel_endpoint:
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "langchain-orchestrator"}))
    exporter = OTLPSpanExporter(endpoint=otel_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor().instrument()
    RequestsInstrumentor().instrument()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("orchestrator.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("orchestrator")



# --- FastAPI app ---
app = FastAPI(title="LangChain Flight Orchestrator")

@app.get("/")
def root():
    return {"status": "ok", "service": "orchestrator"}


_EXCHANGE_RATES = {}
try:
    _EXCHANGE_RATES = json.loads(os.getenv("EXCHANGE_RATES", "{}"))
except Exception:
    _EXCHANGE_RATES = {}

def detect_region_from_ip(ip_address: Optional[str]) -> Dict[str, Any]:
    """
    Attempt to detect a single region dict from client IP.
    Returns a dict like: {"country": "IN", "currency": "INR", "region": "Asia/India"}.
    If an external IP geolocation provider is configured via env var IP_GEO_PROVIDER,
    it will call it (simple GET JSON with keys 'country' and 'currency' expected).
    Otherwise returns a safe default.
    """
    if not ip_address:
        return {"country": "IN", "currency": "INR", "region": "IN"}

    provider = os.getenv("IP_GEO_PROVIDER", "").strip()
    try:
        if provider:
            # expected format: provider URL with {ip} placeholder, e.g. "https://ipapi.co/{ip}/json"
            url = provider.format(ip=ip_address)
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                country = data.get("country", data.get("country_code", "IN"))
                # many providers call currency "currency" or "currency_code"
                currency = data.get("currency", data.get("currency_code", "INR"))
                return {"country": country, "currency": currency, "region": country}
    except Exception as e:
        logger.warning("Region detection via IP provider failed: %s", e)

    # fallback
    return {"country": "IN", "currency": "INR", "region": "IN"}


def normalize_price(amount: float, from_currency: str, to_currency: str) -> Optional[float]:
    """
    Convert 'amount' from 'from_currency' to 'to_currency' using simple env-driven rates.
    If rates incomplete, return None (indicates cannot normalize).
    Rates are expected as: EXCHANGE_RATES={"INR":1.0,"USD":0.012,...}
    """
    if not _EXCHANGE_RATES:
        return None
    try:
        if from_currency == to_currency:
            return amount
        base_rate = _EXCHANGE_RATES.get(from_currency)
        target_rate = _EXCHANGE_RATES.get(to_currency)
        if base_rate is None or target_rate is None:
            return None
        # Convert amount -> base USD-like unit using base_rate, then to target
        # Here base_rate is assumed as per-unit relative to "base currency" (e.g., INR:1.0)
        normalized = (amount / base_rate) * target_rate
        return normalized
    except Exception:
        return None



def merge_and_dedupe_results(all_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge lists from multiple regions:
      - Deduplicate using providerFlightId if present
      - If no providerFlightId, dedupe by (provider, origin, destination, departureTime, price)
    Keeps the earliest occurrence and appends a 'region_sources' list to each result with regions that found it.
    """
    seen = {}
    merged = []
    for r in all_results:
        try:
            pid = r.get("providerFlightId")
            if pid:
                key = f"pid::{r.get('provider')}::{pid}"
            else:
                key = f"anon::{r.get('provider')}::{r.get('origin')}::{r.get('destination')}::{r.get('departureTime')}::{r.get('price')}"
            if key in seen:
                existing = seen[key]
                src = r.get("region_source")
                if src and src not in existing.get("region_sources", []):
                    existing["region_sources"].append(src)
            else:
                r_copy = dict(r)
                r_copy["region_sources"] = [r.get("region_source")] if r.get("region_source") else []
                merged.append(r_copy)
                seen[key] = r_copy
        except Exception:
            # defensive: if malformed result skip it
            continue
    return merged






# 🧩 1. Intent-aware natural language endpoint
# @app.post("/agent/query")
# async def handle_text_query(payload: Dict[str, Any], session_id: Optional[str] = Query(None)):
#     """
#     Multi-region flow:
#     - If payload.device contains 'regions': a list of region dicts or region codes, we will query MCP per region.
#       Example device.regions: [{"country":"AE","currency":"AED"},{"country":"IN","currency":"INR"}]
#     - Otherwise will use IP detection for a single region and call MCP once.
#     - Aggregates results, dedupes, optionally normalizes prices (if EXCHANGE_RATES provided).
#     """
#     try:
#         text = payload.get("query", "")
#         if not text:
#             raise OrchestratorException("Query text cannot be empty", code="EMPTY_QUERY", status_code=400)

#         device = payload.get("device", {}) or {}
#         ip_address = payload.get("ip", None)

#         # parse user intent -> base query dict
#         parsed = parse_user_query(text)

#         # Decide target regions list (list of dicts with at least currency & country)
#         regions_input = device.get("regions")
#         regions: List[Dict[str, Any]] = []

#         if regions_input:
#             # normalize different possible region inputs
#             for x in regions_input:
#                 if isinstance(x, str):
#                     # simple code like "IN" or "AE" -> default currency mapping (can be extended)
#                     regions.append({"country": x, "currency": None, "region": x})
#                 elif isinstance(x, dict):
#                     regions.append({"country": x.get("country") or x.get("region"),
#                                     "currency": x.get("currency"),
#                                     "region": x.get("region") or x.get("country")})
#         else:
#             # single region detection via device or IP
#             if device.get("country") or device.get("currency"):
#                 regions.append({"country": device.get("country"), "currency": device.get("currency"), "region": device.get("region")})
#             else:
#                 regions.append(detect_region_from_ip(ip_address))

#         # For each region, build a query copy with currency set and call MCP
#         aggregated_results = []
#         for reg in regions:
#             # determine currency precedence: user text override > region currency > parsed currency > default IN
#             currency_override = detect_currency_from_text(text)
#             currency = currency_override or reg.get("currency") or parsed.get("currency") or "INR"

#             # build FlightQuery payload
#             fq_payload = dict(parsed)  # shallow copy
#             fq_payload["currency"] = currency

#             # ensure required fields exist (origin/destination must be present from parsed or we raise)
#             if not fq_payload.get("origin") or not fq_payload.get("destination"):
#                 raise OrchestratorException("origin/destination missing in parsed query", code="INVALID_QUERY", status_code=400)

#             # call MCP
#             logger.info("Calling MCP for region %s with currency %s", reg.get("region"), currency)
#             try:
#                 results = call_mcp_search(fq_payload)
#             except Exception as e:
#                 logger.warning("MCP call failed for region %s: %s", reg.get("region"), e)
#                 results = []

#             # tag each result with region
#             for r in results:
#                 r["region_source"] = reg.get("region") or reg.get("country") or "unknown"
#                 aggregated_results.append(r)

#         # Merge & dedupe
#         merged = merge_and_dedupe_results(aggregated_results)

#         # Optionally normalize prices to user's preferred currency (if env var USER_DISPLAY_CURRENCY set)
#         display_currency = parsed.get("currency") or os.getenv("USER_DISPLAY_CURRENCY")
#         if display_currency:
#             for r in merged:
#                 try:
#                     normalized = normalize_price(r.get("price", 0.0), r.get("currency", ""), display_currency)
#                     if normalized is not None:
#                         r["_price_normalized"] = round(normalized, 2)
#                         r["_display_currency"] = display_currency
#                 except Exception:
#                     pass

#             # sort by normalized price if available else raw price
#             merged.sort(key=lambda x: x.get("_price_normalized", x.get("price", float('inf'))))
#         else:
#             merged.sort(key=lambda x: x.get("price", float('inf')))

#         # Summarize (we pass merged results)
#         summary_prompt = (
#             f"User asked: '{text}'\n"
#             f"Regions queried: {[r.get('region_source') for r in merged]}\n"
#             f"Aggregated flight results: {json.dumps(merged)[:5000]}\n"  # truncate large payload for prompt safety
#             f"Summarize top {parsed.get('limit', 10)} flights and mention region & currency."
#         )
#         summary = call_openai_sync(summary_prompt)

#         # session persistence
#         if session_id:
#             append_message(session_id, "user", text)
#             append_message(session_id, "assistant", summary)

#         return JSONResponse({
#             "status": "ok",
#             "parsed_query": parsed,
#             "regions": regions,
#             "results": merged,
#             "summary": summary
#         })

#     except OrchestratorException as oe:
#         # let custom handler format it
#         raise oe

#     except Exception as e:
#         logger.exception("Unexpected error in handle_text_query: %s", e)
#         raise OrchestratorException(
#             f"Unexpected error while processing query: {str(e)}",
#             code="QUERY_PROCESSING_ERROR"
#         )



@app.post("/agent/query")
async def handle_text_query(payload: Dict[str, Any], session_id: Optional[str] = Query(None)):
    """
    Natural language endpoint where the LLM agent autonomously decides how to use the flight search tool.

    It supports natural conversations:
      - "Find me the cheapest flights from Delhi to Dubai tomorrow"
      - "Show flights from Mumbai to London on 12th December for 2 adults"
      - "Now make it for 2 people instead"
      - "Show only morning ones"

    The LLM will recall prior context via Redis memory.
    """
    try:
        text = payload.get("query", "")
        if not text:
            raise OrchestratorException("Query text cannot be empty", code="EMPTY_QUERY", status_code=400)

        # Load session memory if available
        history = get_history(session_id) if session_id else []

        #  Construct conversation context for the LLM
        messages = [{"role": "system", "content": (
            "You are a helpful flight booking assistant. "
            "You help users search and modify their flight requests using available tools like aggregate_flight_search. "
            "Always infer user intent from conversation history."
        )}]

        for msg in history:
            # each message is expected as {"role": "user"/"assistant", "content": "..."}
            messages.append(msg)

        messages.append({"role": "user", "content": text})

        logger.info(f"🧠 LLM analyzing: {text}")
        logger.debug(f"💬 Context sent to LLM: {messages}")

        #  Invoke the LangChain agent with full memory
        llm_response = agent.invoke({"input": messages})

        summary_prompt = f"Summarize this in 2 lines for a user interface: {llm_response}"
        summary = call_openai_sync(summary_prompt)

        #  Store the new conversation turn in Redis
        if session_id:
            append_message(session_id, "user", text)
            append_message(session_id, "assistant", llm_response)

        #  Return response
        return JSONResponse({
            "status": "ok",
            "response": llm_response,
            "session_id": session_id,
        })

    except OrchestratorException as oe:
        raise oe

    except Exception as e:
        logger.exception("❌ Unexpected error in handle_text_query: %s", e)
        raise OrchestratorException(
            message=f"Unexpected error while processing query: {str(e)}",
            code="QUERY_PROCESSING_ERROR",
            status_code=500
        )





def append_message(session_id: str, role: str, content: str):
    redis_client.rpush(session_id, json.dumps({"role": role, "content": content}))

def get_history(session_id: str):
    messages = redis_client.lrange(session_id, 0, -1)
    return [json.loads(m.decode('utf-8')) for m in messages]



def detect_currency_from_text(text: str):
    text = text.lower()
    currencies = {
        "usd": "USD", "inr": "INR", "euro": "EUR", "eur": "EUR",
        "pound": "GBP", "gbp": "GBP", "aed": "AED", "dirham": "AED"
    }
    for k, v in currencies.items():
        if k in text:
            return v
    return None




# 🧩 2. Structured (non-stream) search
@app.post("/agent/search")
async def orchestrate_search(query: FlightQuery, session_id: Optional[str] = Query(None)):
    """
    Direct structured search endpoint — bypasses natural language flow.
    Uses the same LangChain tool internally to call MCP.
    """
    try:
        if session_id:
            append_message(session_id, "user", json.dumps(query.dict()))

        # 🧩 Use the LangChain Tool instead of direct MCP call
        results = aggregate_flight_search_tool.invoke(query.dict())

        if session_id:
            append_message(session_id, "assistant", json.dumps(results))

        # Summarize results with OpenAI
        summary_prompt = f"Summarize Amadeus flight results in 2 lines for the UI: {results}"
        summary = call_openai_sync(summary_prompt)

        if session_id:
            append_message(session_id, "assistant", summary)

        return JSONResponse({
            "status": "ok",
            "results": results,
            "summary": summary
        })

    except OrchestratorException as oe:
        raise oe

    except Exception as e:
        logger.exception("❌ Unexpected error while searching flights: %s", e)
        raise OrchestratorException(
            message=f"Unexpected error while searching flights: {str(e)}",
            code="SEARCH_ERROR",
            status_code=500
        )




# 🧩 3. Streaming endpoint (SSE)
@app.post("/agent/search/stream")
async def orchestrate_search_stream(query: FlightQuery, session_id: Optional[str] = Query(None)):
    """
    Production-safe Server-Sent Events (SSE) endpoint.
    Streams OpenAI summary tokens in real time.
    """
    try:
        if not openai.api_key:
            raise OrchestratorException(
                "OPENAI_API_KEY not configured",
                code="OPENAI_KEY_MISSING",
                status_code=500
            )

        # 🧩 Use the LangChain Tool for flight search
        results = aggregate_flight_search_tool.invoke(query.dict())
        prompt = f"Stream a short summary for these Amadeus flight results: {results}"

        async def event_generator():
            try:
                stream = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    temperature=0.0
                )

                for event in stream:
                    if isinstance(event, dict) and event.get("choices"):
                        for ch in event["choices"]:
                            delta = ch.get("delta", {})
                            token = delta.get("content") or delta.get("text")
                            if token:
                                yield f"data: {token}\n\n"

                yield "data: [DONE]\n\n"

            except Exception as e:
                logger.exception("💥 OpenAI streaming failed: %s", e)
                yield f"data: [ERROR] {str(e)}\n\n"
                yield "data: [DONE]\n\n"

        # Session persistence
        if session_id:
            append_message(session_id, "user", json.dumps(query.dict()))
            append_message(session_id, "assistant", "[Streaming started]")

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except OrchestratorException as oe:
        raise oe

    except Exception as e:
        logger.exception("Unexpected streaming error: %s", e)
        raise OrchestratorException(
            f"Unexpected error during stream: {str(e)}",
            code="STREAM_ERROR",
            status_code=500
        )




# --- Utility function for OpenAI calls ---
def call_openai_sync(prompt: str) -> str:
    """
    Calls OpenAI synchronously. Raises OrchestratorException if key missing or API fails.
    """
    if not openai.api_key:
        raise OrchestratorException(
            "OPENAI_API_KEY not configured",
            code="OPENAI_KEY_MISSING",
            status_code=500
        )

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=200
        )
        return resp["choices"][0]["message"]["content"]
    except Exception as e:
        logger.exception("OpenAI API call failed: %s", e)
        raise OrchestratorException(
            f"OpenAI API error: {str(e)}",
            code="OPENAI_API_ERROR",
            status_code=502
        )

    


# --- Global Exception Handling Setup ---
from fastapi.exceptions import RequestValidationError
from exceptions import (
    orchestrator_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
    OrchestratorException,
)

app.add_exception_handler(OrchestratorException, orchestrator_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
