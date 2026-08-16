"""Application errors and the common HTTP error envelope."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class ProfessorNotFoundError(AppError):
    def __init__(self, professor_id: int) -> None:
        super().__init__(
            code="PROFESSOR_NOT_FOUND",
            message=f"Professor {professor_id} was not found.",
            status_code=404,
            details={"professor_id": professor_id},
        )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, error: AppError) -> JSONResponse:
        body: dict[str, Any] = {
            "error": {
                "code": error.code,
                "message": error.message,
            }
        }
        if error.details is not None:
            body["error"]["details"] = error.details
        return JSONResponse(status_code=error.status_code, content=jsonable_encoder(body))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        issues = [
            {key: issue[key] for key in ("type", "loc", "msg") if key in issue}
            for issue in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Request validation failed.",
                        "details": {"issues": issues},
                    }
                }
            ),
        )
