from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY, HTTP_500_INTERNAL_SERVER_ERROR
import traceback
import logging

logger = logging.getLogger(__name__)

class OrchestratorException(Exception):
    """Base exception for orchestrator-related errors."""
    def __init__(self, message: str, code: str = "ORCHESTRATOR_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)

# Exception handlers
async def orchestrator_exception_handler(request: Request, exc: OrchestratorException):
    logger.error(f"[OrchestratorException] {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.code,
            "message": exc.message,
            "path": str(request.url),
        },
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"[ValidationError] {exc.errors()}")
    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "VALIDATION_ERROR",
            "message": exc.errors(),
            "path": str(request.url),
        },
    )

async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"[UnhandledException] {str(exc)}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": str(exc),
            "path": str(request.url),
        },
    )
