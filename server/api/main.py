from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .middleware import (
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from .routes import admin

logging.basicConfig(level=logging.INFO, format='%(message)s')

app = FastAPI(title='OmniRoute API', version='0.1.0')
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(admin.router)


@app.get('/health', tags=['health'])
async def health() -> dict[str, str]:
    return {'status': 'ok'}


app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
