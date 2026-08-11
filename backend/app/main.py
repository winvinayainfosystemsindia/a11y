"""
FastAPI application entrypoint: creates the app, wires up CORS, registers
all routers, and normalizes error responses to a consistent {"detail": ...}
shape.
"""
import logging
import os

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.views import audit_routes, auth_routes, crawl_routes, project_routes, user_routes, wcag_routes

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Accessibility Audit Platform API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Evidence screenshots captured by the AI audit agent (app/ai/tools/screenshot_tool.py)
# are written under "static/" and served back to the frontend from here.
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth_routes.router)
app.include_router(user_routes.router)
app.include_router(project_routes.router)
app.include_router(crawl_routes.router)
app.include_router(audit_routes.router)
app.include_router(wcag_routes.router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Collapse Pydantic's verbose error list into the project-wide {"detail": ...} shape.
    first_error = exc.errors()[0] if exc.errors() else None
    message = first_error.get("msg", "Invalid request") if first_error else "Invalid request"
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": message})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger(__name__).exception("Unhandled error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred"},
    )


@app.get("/api/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok", "environment": settings.ENVIRONMENT}
