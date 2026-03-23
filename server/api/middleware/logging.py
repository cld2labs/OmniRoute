from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


logger = logging.getLogger('omniroute.api')


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = perf_counter()
        response = await call_next(request)
        latency_ms = round((perf_counter() - start) * 1000, 2)

        payload = {
            'timestamp': datetime.now(UTC).isoformat(),
            'service': 'api',
            'request_id': getattr(request.state, 'request_id', ''),
            'user_id': getattr(request.state, 'admin_user_id', None),
            'route': request.url.path,
            'latency_ms': latency_ms,
        }
        logger.info(json.dumps(payload))
        return response
