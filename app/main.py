import logging
from pathlib import Path

import markdown as md
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.middleware import RequestIdMiddleware
from app.api.routes import router as api_router
from app.core.config import settings
from app.core.logging import setup_logging

# Configure structured JSON logging with request correlation
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)
app.add_middleware(RequestIdMiddleware)

# Setup Paths
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"

# Mount Static
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include Router
app.include_router(api_router)

# Setup Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["markdown"] = lambda text: md.markdown(text) if text else ""


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request) -> HTMLResponse:  # type: ignore[type-arg]
    return templates.TemplateResponse(request, "index.html", {"app_name": settings.APP_NAME})


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "env": settings.APP_ENV}
