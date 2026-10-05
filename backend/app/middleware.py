from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    """Bound request buffering before JSON parsing, including chunked uploads."""
    def __init__(self, app, maximum=3_000_000):
        self.app = app
        self.maximum = maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        maximum = self.maximum
        if scope["path"].endswith("/ai/generate-questions/image"):
            from .config import settings
            maximum = settings().ai_max_image_size_mb * 1024 * 1024 + 128 * 1024
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > maximum:
                return await JSONResponse({"detail": f"Request exceeds {maximum // (1024 * 1024)} MB limit"}, status_code=413)(scope, receive, send)
            chunks.append(message)
            if not message.get("more_body", False):
                break
        async def replay():
            if chunks:
                return chunks.pop(0)
            return await receive()
        await self.app(scope, replay, send)
