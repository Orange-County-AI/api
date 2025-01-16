from fastapi import FastAPI, HTTPException, Query, Request
from meetup_notifier import get_events
from typing import List, Dict, Any, Literal
from dataclasses import asdict
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Orange County AI Meetup API")

# Add CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log incoming requests and their CORS headers"""
    logger.info(f"Incoming request: {request.method} {request.url}")
    logger.info(f"Origin: {request.headers.get('origin')}")
    logger.info(f"Headers: {dict(request.headers)}")

    response = await call_next(request)

    logger.info(f"Response headers: {dict(response.headers)}")
    return response


MEETUP_URL = "https://www.meetup.com/orange-county-ai/events/"


@app.get("/", response_class=RedirectResponse, status_code=303)
async def redirect_to_docs():
    """Redirect root path to API documentation."""
    return "/docs"


@app.get("/events", response_model=List[Dict[str, Any]])
async def list_events(
    limit: int = Query(
        default=None, ge=1, description="Limit the number of events returned"
    ),
    sort: Literal["asc", "desc"] = Query(
        default="asc", description="Sort events by date (asc or desc)"
    ),
):
    """Get all upcoming events from Orange County AI meetup group."""
    try:
        events = get_events(MEETUP_URL)
        events_list = [asdict(event) for event in events]

        # Sort events by date
        events_list.sort(key=lambda x: x["date"], reverse=(sort == "desc"))

        # Apply limit if specified
        if limit is not None:
            events_list = events_list[:limit]

        return events_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
