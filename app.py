from fastapi import FastAPI, HTTPException, Query, Request, Body
from meetup import get_events, MeetupEvent
from typing import List, Dict, Any, Literal
from dataclasses import asdict
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
import httpx
import os
import jwt
import time
import sentry_sdk
from pocketbase_orm import PBModel
from pocketbase import PocketBase
from loguru import logger


sentry_sdk.init(os.environ["SENTRY_DSN"])
logger.info("Sentry SDK initialized")

MEETUP_URL = "https://www.meetup.com/orange-county-ai/events/"

GHOST_API_URL = "https://blog.orangecountyai.com"
GHOST_ADMIN_KEY = os.environ["GHOST_ADMIN_KEY"]

POCKETBASE_URL = os.environ["POCKETBASE_URL"]
POCKETBASE_USERNAME = os.environ["POCKETBASE_USERNAME"]
POCKETBASE_PASSWORD = os.environ["POCKETBASE_PASSWORD"]


class NewsletterSubscriber(PBModel, collection="newsletter_subscribers"):
    email: str
    active: bool = True


pocketbase_client = PocketBase(POCKETBASE_URL)
pocketbase_client.admins.auth_with_password(POCKETBASE_USERNAME, POCKETBASE_PASSWORD)

PBModel.bind_client(pocketbase_client)
NewsletterSubscriber.sync_collection()

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
    logger.info(
        "Incoming request",
        extra={
            "method": request.method,
            "url": str(request.url),
            "origin": request.headers.get("origin"),
            "headers": dict(request.headers),
        },
    )

    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    logger.info(
        "Request completed",
        extra={
            "method": request.method,
            "url": str(request.url),
            "status_code": response.status_code,
            "process_time": f"{process_time:.2f}s",
            "response_headers": dict(response.headers),
        },
    )
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
    logger.info("Fetching events", extra={"limit": limit, "sort": sort})
    try:
        events = get_events(MEETUP_URL)
        events_list = [asdict(event) for event in events]

        # Sort events by date
        events_list.sort(
            key=lambda x: ("office hours" in x["name"].lower(), x["date"]),
            reverse=(sort == "desc"),
        )

        # Apply limit if specified
        if limit is not None:
            events_list = events_list[:limit]

        logger.info(
            "Events fetched successfully",
            extra={"event_count": len(events_list)},
        )
        return events_list
    except Exception as e:
        logger.error(
            "Error fetching events",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        raise HTTPException(status_code=500, detail=str(e))


def generate_ghost_token(ghost_admin_key: str) -> str:
    """Generate a Ghost Admin API token."""
    logger.debug("Generating Ghost Admin API token")
    try:
        [id, secret] = ghost_admin_key.split(":")
        header = {"alg": "HS256", "typ": "JWT", "kid": id}
        iat = int(time.time())
        payload = {
            "iat": iat,
            "exp": iat + 5 * 60,
            "aud": "/admin/",
        }
        token = jwt.encode(
            payload, bytes.fromhex(secret), algorithm="HS256", headers=header
        )
        logger.debug("Ghost Admin API token generated successfully")
        return token
    except Exception as e:
        logger.error(
            "Error generating Ghost token",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        raise


@app.post("/subscribe")
def subscribe_email(email: str = Body(..., embed=True)):
    """Subscribe an email address to the Orange County AI blog."""
    logger.info("Processing subscription request", extra={"email": email})

    if not GHOST_ADMIN_KEY:
        logger.error("Ghost API key not configured")
        raise HTTPException(status_code=500, detail="Ghost API key not configured")

    try:
        subscriber = NewsletterSubscriber(email=email)
        subscriber.save()
        logger.info("Subscriber saved to PocketBase", extra={"email": email})
    except Exception as e:
        data = e.data.get("data", {})
        if data.get("email", {}).get("code", "") == "validation_not_unique":
            logger.info("Duplicate subscription attempt", extra={"email": email})
        else:
            logger.exception(
                "Error saving subscriber to PocketBase",
                extra={"error": str(e), "email": email},
            )
            raise HTTPException(status_code=500, detail="Internal server error")

    try:
        token = generate_ghost_token(GHOST_ADMIN_KEY)
        logger.debug("Ghost token generated for subscription")

        response = httpx.post(
            f"{GHOST_API_URL}/ghost/api/admin/members/",
            headers={
                "Authorization": f"Ghost {token}",
                "Content-Type": "application/json",
            },
            json={"members": [{"email": email, "subscribed": True}]},
        )

        if response.status_code == 201:
            logger.info("Subscription successful", extra={"email": email})
            return {"message": "Successfully subscribed"}
        elif response.status_code == 422:
            error_data = response.json()
            if any(
                "Member already exists" in error.get("context", "")
                for error in error_data.get("errors", [])
            ):
                logger.info(
                    "Attempted to subscribe existing member",
                    extra={"email": email},
                )
                raise HTTPException(
                    status_code=409, detail="Email is already subscribed"
                )

        logger.error(
            "Ghost API error",
            extra={
                "status_code": response.status_code,
                "response": response.text,
                "email": email,
            },
        )
        raise HTTPException(status_code=400, detail="Failed to subscribe email")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Subscription process failed",
            extra={"error": str(e), "email": email},
        )
        raise HTTPException(status_code=500, detail="Internal server error")
