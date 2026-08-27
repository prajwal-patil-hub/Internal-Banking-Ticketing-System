"""Reject oversized request bodies before anything else touches them.

The per-endpoint size checks are too late to be the only defence. FastAPI
parses a multipart body — spooling it to a temporary file — *before* it solves
dependencies, so `get_current_user` has not run yet when the bytes arrive. An
unauthenticated caller POSTing a multi-gigabyte body to the upload endpoint
therefore gets it written to disk before the 401 is issued, and the handler's
own `len(data)` check never gets a say.

This runs as raw ASGI rather than `BaseHTTPMiddleware` so it can drain the
body itself, decide, and then replay the bytes to the application. Draining is
what makes the decision reliable: an earlier attempt wrapped `receive` and
raised once the count passed the cap, but by then the app was already running
and the exception surfaced inside FastAPI's body parsing, which turned a
413 into a 400 "malformed JSON". Deciding before the app is invoked leaves no
half-built response to fight with.

Two checks, because either alone is bypassable:

* **Declared size.** `Content-Length` is cheap and refuses the honest case
  before a single byte of body is read.
* **Observed size.** A chunked upload sends no `Content-Length`, and a
  dishonest client can understate it, so the actual bytes are counted as they
  stream and the request is failed the moment the cap is passed.

The limit is per-path: the knowledge base legitimately takes larger files than
ticket attachments, and applying the larger cap everywhere would widen the
exposure of every other endpoint to no purpose.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger

log = get_logger(__name__)


class BodySizeLimitMiddleware:
    """Cap request body size per path prefix.

    `limits` maps a path prefix to a byte cap; the longest matching prefix
    wins, and `default_limit` applies to everything else.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        default_limit: int,
        limits: dict[str, int] | None = None,
    ) -> None:
        self.app = app
        self.default_limit = default_limit
        # Longest prefix first so a specific rule beats a general one.
        self.limits = sorted((limits or {}).items(), key=lambda kv: -len(kv[0]))

    def _limit_for(self, path: str) -> int:
        for prefix, limit in self.limits:
            if path.startswith(prefix):
                return limit
        return self.default_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "DELETE"):
            await self.app(scope, receive, send)
            return

        limit = self._limit_for(scope.get("path", ""))

        # Cheap path: the client told us it is too big.
        headers = {k.decode("latin-1").lower(): v for k, v in scope.get("headers", [])}
        declared = headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    await self._reject(scope, send, limit)
                    return
            except ValueError:
                pass  # Malformed header; the streaming count below still applies.

        # Drain the body here, before the app is ever called, and refuse
        # outright if it runs past the cap.
        #
        # An earlier version wrapped `receive` and raised from inside it while
        # the app was already running. That does not work: the exception
        # surfaces inside FastAPI's body parsing, which turns it into a 400
        # validation error, so an oversized upload was reported as malformed
        # JSON and the 413 never reached the client. Deciding before the app
        # starts means there is no half-built response to fight with.
        #
        # Memory is bounded by `limit` — which is exactly the amount the
        # handler was going to read into memory anyway, so this buffers
        # nothing that was not already going to be buffered.
        chunks: list[bytes] = []
        received = 0
        more_body = True

        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunks.append(message.get("body", b""))
            received += len(chunks[-1])
            if received > limit:
                log.warning(
                    "request_body_too_large",
                    path=scope.get("path"),
                    limit=limit,
                    received=received,
                )
                await self._reject(scope, send, limit)
                return
            more_body = message.get("more_body", False)

        body = b"".join(chunks)
        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if replayed:
                return {"type": "http.disconnect"}
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay_receive, send)

    async def _reject(self, scope: Scope, send: Send, limit: int) -> None:
        """Same envelope shape as every other error in the API."""
        body = json.dumps(
            {
                "success": False,
                "data": None,
                "meta": {},
                "error": {
                    "code": "payload_too_large",
                    "message": (
                        f"Request body exceeds the {limit // 1_048_576} MB limit "
                        f"for {scope.get('path', 'this endpoint')}."
                    ),
                },
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
