from fastapi import FastAPI, HTTPException, Query, Request, Body
from meetup_notifier import get_events
from typing import List, Dict, Any, Literal
from dataclasses import asdict
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
import httpx
import os
import jwt
import time


MEETUP_URL = "https://www.meetup.com/orange-county-ai/events/"

GHOST_API_URL = "https://blog.orangecountyai.com"
GHOST_ADMIN_KEY = os.environ["GHOST_ADMIN_KEY"]

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Orange County AI Meetup API")

# Add CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"https://.*\.lovable\.app|https://orangecountyai\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],  # Add this to expose headers to the client
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


def generate_ghost_token(ghost_admin_key: str) -> str:
    """Generate a Ghost Admin API token."""
    [id, secret] = ghost_admin_key.split(":")
    # Create the token header
    header = {"alg": "HS256", "typ": "JWT", "kid": id}
    # Create the token payload
    iat = int(time.time())
    payload = {
        "iat": iat,
        "exp": iat + 5 * 60,  # Token expires in 5 minutes
        "aud": "/admin/",
    }
    # Create the token
    token = jwt.encode(
        payload, bytes.fromhex(secret), algorithm="HS256", headers=header
    )
    return token


@app.post("/subscribe")
async def subscribe_email(email: str = Body(..., embed=True)):
    """Subscribe an email address to the Orange County AI blog."""
    if not GHOST_ADMIN_KEY:
        raise HTTPException(status_code=500, detail="Ghost API key not configured")

    try:
        # Generate the token
        token = generate_ghost_token(GHOST_ADMIN_KEY)

        # Create a member in Ghost
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GHOST_API_URL}/ghost/api/admin/members/",
                headers={
                    "Authorization": f"Ghost {token}",
                    "Content-Type": "application/json",
                },
                json={"members": [{"email": email, "subscribed": True}]},
            )

            if response.status_code == 201:
                return {"message": "Successfully subscribed"}
            else:
                logger.error(
                    f"Ghost API error: {response.status_code} - {response.text}"
                )
                raise HTTPException(status_code=400, detail="Failed to subscribe email")

    except Exception as e:
        logger.error(f"Subscription error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
