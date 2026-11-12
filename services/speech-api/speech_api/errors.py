"""Every error leaves the gateway as JSON: {"error": str, ...}."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, error: str, headers: dict | None = None, **extra):
        super().__init__(error)
        self.status = status
        self.error = error
        self.extra = extra
        self.headers = headers or {}

    def response(self) -> JSONResponse:
        return JSONResponse({"error": self.error, **self.extra}, status_code=self.status, headers=self.headers)


def engine_unavailable(engine: str) -> ApiError:
    return ApiError(503, "engine unavailable", engine=engine)


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return exc.response()

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        detail = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()]
        return JSONResponse({"error": "invalid request", "detail": detail}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        msg = exc.detail if isinstance(exc.detail, str) else "error"
        return JSONResponse({"error": msg.lower()}, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        return JSONResponse({"error": "internal error"}, status_code=500)
