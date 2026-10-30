"""Main FastAPI Application Entrypoint for Sana'a AI."""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response

from app.api.routes import router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    description="Multilingual AI Maintenance Assistant for Home Appliances & Skilled Trades (Graduation Project)",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS so the future Sana'a Mobile/Web Frontend can communicate seamlessly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins during development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API endpoints
app.include_router(router)

# Paths for Frontend Assets
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/chat", response_class=HTMLResponse, include_in_schema=False)
def serve_chat_ui():
    """Serves the Sana'a AI Chatbot Web Interface (Imported from Figma)."""
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>Sana'a Frontend not found</h2>", status_code=404)


@app.get("/styles.css", include_in_schema=False)
def serve_css():
    """Serves the Figma design system stylesheet."""
    css_file = os.path.join(FRONTEND_DIR, "styles.css")
    if os.path.exists(css_file):
        with open(css_file, "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/css")
    return Response(status_code=404)


@app.get("/app.js", include_in_schema=False)
def serve_js():
    """Serves the Chatbot frontend client logic."""
    js_file = os.path.join(FRONTEND_DIR, "app.js")
    if os.path.exists(js_file):
        with open(js_file, "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="application/javascript")
    return Response(status_code=404)
