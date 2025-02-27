import parsel
from dataclasses import dataclass
from datetime import datetime
import requests
import re
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class MeetupEvent:
    link: str
    name: str
    description: str
    image: str
    location: str
    location_link: str | None
    venue: str | None
    date: datetime


def parse_event_page(html: str) -> MeetupEvent:
    # Try to extract the event data from JSON embedded in the page
    try:
        # Find the JSON data in the HTML
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not match:
            raise ValueError("Could not find event JSON data in HTML")

        json_data = json.loads(match.group(1))

        # Extract event data from the JSON
        event_props = json_data.get("props", {}).get("pageProps", {})
        event_data = event_props.get("__APOLLO_STATE__", {})

        # Find the first key that starts with 'Event:'
        event_key = next((k for k in event_data.keys() if k.startswith("Event:")), None)
        if not event_key:
            raise ValueError("Could not find event data in JSON")

        event = event_data[event_key]

        # Extract fields
        link = event.get("eventUrl")
        name = event.get("title")
        description = event.get("description")

        # Find featured event photo
        photo_ref = event.get("featuredEventPhoto", {}).get("__ref")
        image = ""
        if photo_ref and photo_ref in event_data:
            image = event_data[photo_ref].get("highResUrl", "")

        # Extract location
        venue_ref = event.get("venue", {}).get("__ref")
        venue_name = None
        location = "Online"
        location_link = None

        if venue_ref and venue_ref in event_data:
            venue_data = event_data[venue_ref]
            venue_name = venue_data.get("name")
            address = venue_data.get("address", "")
            city = venue_data.get("city", "")
            state = venue_data.get("state", "")
            country = venue_data.get("country", "")

            location_parts = [p for p in [address, city, state, country] if p]
            location = ", ".join(location_parts)
            location_link = f"https://maps.google.com/?q={location}"

        # Extract date
        date_str = event.get("dateTime")
        date = datetime.fromisoformat(date_str) if date_str else datetime.now()

        return MeetupEvent(
            link=link,
            name=name,
            description=description,
            image=image,
            location=location,
            location_link=location_link,
            venue=venue_name,
            date=date,
        )
    except Exception as e:
        # Fallback to the old parsing method
        try:
            selector = parsel.Selector(html)

            link = selector.css("head > meta:nth-child(28)::attr(content)").get()
            name = (
                selector.css(
                    "#main > div.px-5.w-full.border-b.border-shadowColor.bg-white.py-2.lg\:py-6 > div > h1::text"
                )
                .get()
                .replace("\n", "")
                .split()
            )
            image = selector.css(
                "#main > div.flex.w-full.flex-col.items-center.justify-between.border-t.border-gray2.bg-gray1.pb-6.lg\:px-5 > div.md\:max-w-screen.w-full.bg-gray1 > div > div.flex.flex-grow.flex-col.lg\:mt-5.lg\:max-w-2xl > div.emrv9za > div:nth-child(1) > picture > div > img::attr(src)"
            ).get()
            description = selector.css("#event-details > div.break-words")

            texts = []
            for element in description.xpath(".//p | .//li"):
                text = element.xpath("string(.)").get().strip()
                text = text.replace("\n", " ")
                text = " ".join(text.split())

                if element.root.tag == "li":
                    text = f"• {text}"  # Formatting list items with bullet points
                texts.append(text)

            description = "\n".join(texts)

            location_a = selector.css(
                "#event-info > div.bg-white.px-5.pb-3.pt-6.sm\:pb-4\.5.lg\:py-5.lg\:rounded-t-2xl > div:nth-child(1) > div.flex.flex-col > div > div.overflow-hidden.pl-4.md\:pl-4\.5.lg\:pl-5 > a"
            )
            location_link = location_a.css("::attr(href)").get()
            location = (
                selector.css(
                    "#event-info > div.bg-white.px-5.pb-3.pt-6.sm\:pb-4\.5.lg\:py-5.lg\:rounded-t-2xl > div:nth-child(1) > div.flex.flex-col > div > div.overflow-hidden.pl-4.md\:pl-4\.5.lg\:pl-5 > div::text"
                )
                .get()
                .replace("\n", "")
                .split()
            )

            pattern = r'"dateTime":"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2})?)"'
            match = re.search(pattern, html)
            date = match.group(1)

            venue = [""]
            if location[0] != "Online":
                venue = location_a.css("::text").get().replace("\n", "").split()

            return MeetupEvent(
                link=link,
                name=" ".join(name),
                description=description,
                image=image,
                location=" ".join(location),
                location_link=location_link,
                venue=" ".join(venue) if venue != [""] else None,
                date=datetime.fromisoformat(date),
            )
        except Exception as nested_error:
            # If both methods fail, raise the original error with more context
            raise ValueError(
                f"Failed to parse event page: {str(e)}. Nested error: {str(nested_error)}"
            ) from e


def parse_events_page(html: str) -> list[str]:
    try:
        # Find the JSON data in the HTML
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not match:
            raise ValueError("Could not find events JSON data in HTML")

        json_data = json.loads(match.group(1))

        # Extract events data from the JSON
        props = json_data.get("props", {}).get("pageProps", {})
        state = props.get("__APOLLO_STATE__", {})

        # Find Group and events data
        group_key = next((k for k in state.keys() if k.startswith("Group:")), None)
        if not group_key or group_key not in state:
            raise ValueError("Could not find group data in JSON")

        group_data = state[group_key]

        # Look for events connection with upcoming events
        events_key = next(
            (
                k
                for k in group_data.keys()
                if k.startswith("events({") and "status" in k and "ACTIVE" in k
            ),
            None,
        )

        if not events_key or events_key not in group_data:
            raise ValueError("Could not find events data in JSON")

        events_connection = group_data[events_key]
        event_edges = events_connection.get("edges", [])

        # Extract event URLs
        event_urls = []
        for edge in event_edges:
            node_ref = edge.get("node", {}).get("__ref")
            if node_ref and node_ref in state:
                event_data = state[node_ref]
                event_url = event_data.get("eventUrl")
                if event_url:
                    event_urls.append(event_url)

        return event_urls
    except Exception as e:
        # Fallback to the old parsing method
        try:
            selector = parsel.Selector(html)
            events = []
            event_link = selector.css("#event-card-e-1").css("a::attr(href)").get()
            while event_link:
                events.append(event_link)
                event_link = (
                    selector.css(f"#event-card-e-{len(events)+1}")
                    .css("a::attr(href)")
                    .get()
                )

            return events
        except Exception as nested_error:
            # If both methods fail, raise the original error with more context
            raise ValueError(
                f"Failed to parse events page: {str(e)}. Nested error: {str(nested_error)}"
            ) from e


def get_events(group_url: str) -> list[MeetupEvent]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.meetup.com/",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }

    logger.info(f"Fetching events from {group_url}")
    response = requests.get(group_url, headers=headers)
    response.raise_for_status()
    events = parse_events_page(response.text)

    meetup_events = []
    for event in events:
        logger.info(f"Fetching event details from {event}")
        response = requests.get(event, headers=headers)
        response.raise_for_status()
        meetup_event = parse_event_page(response.text)
        meetup_events.append(meetup_event)

    return meetup_events


def debug_meetup_json(html: str, output_file: str = "meetup_debug.json") -> None:
    """
    Parse the JSON data from a Meetup page and save it to a file for debugging.

    Args:
        html: The HTML content of the Meetup page
        output_file: The file to write the JSON data to

    Returns:
        None
    """
    try:
        # Find the JSON data in the HTML
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not match:
            logger.error("Could not find JSON data in HTML")
            return

        json_data = json.loads(match.group(1))

        # Write the JSON data to a file
        with open(output_file, "w") as f:
            json.dump(json_data, f, indent=2)

        logger.info(f"Saved JSON data to {output_file}")
    except Exception as e:
        logger.error(f"Error debugging Meetup JSON: {str(e)}")
