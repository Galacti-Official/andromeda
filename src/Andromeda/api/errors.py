from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AndromedaError(Exception):
    def __init__(self, status_code: int, status: str, message: str):
        self.status_code = status_code
        self.status = status
        self.message = message


async def andromeda_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = exc if isinstance(exc, AndromedaError) else AndromedaError(500, "internal_error", "Internal server error")
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.status_code,
                "message": error.message,
                "status": error.status
            }
        }
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": 400,
                "message": "Invalid request",
                "status": "bad_request",
            }
        }
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    status_code = exc.status_code if isinstance(exc, StarletteHTTPException) else 500
    
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": status_code,
                "message": "The requested resource does not exist" if status_code == 404 else "An error has occurred",
                "status": exc.detail.lower().replace(" ", "_") if isinstance(exc, StarletteHTTPException) else "http_error"
            }
        }
    )
