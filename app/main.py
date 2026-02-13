import logging
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router as api_router
from app.core.config import settings

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

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


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request) -> HTMLResponse:  # type: ignore
    return templates.TemplateResponse(request, "index.html", {"app_name": settings.APP_NAME})


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "env": settings.APP_ENV}
