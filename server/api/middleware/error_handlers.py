from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..models.schemas import ErrorResponse


logger = logging.getLogger('omniroute.api.errors')


def error_payload(request: Request, code: str, message: str, details: dict | None = None) -> dict:
    return ErrorResponse(
        code=code,
        message=message,
        details=details or {},
        request_id=getattr(request.state, 'request_id', ''),
    ).model_dump()


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else 'Request failed.'
    details = exc.detail if isinstance(exc.detail, dict) else {}
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(request, code='http_error', message=message, details=details),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_payload(
            request,
            code='validation_error',
            message='Invalid request payload.',
            details={'errors': exc.errors()},
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception('Unhandled API exception', extra={'request_id': getattr(request.state, 'request_id', '')})
    return JSONResponse(
        status_code=500,
        content=error_payload(
            request,
            code='internal_error',
            message='Internal server error.',
            details={},
        ),
    )
