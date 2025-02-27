#!/usr/bin/env python3
"""
Test script for the Meetup parser.
Fetches events from the Orange County AI Meetup group and prints them.
"""

import sys
import json
from pprint import pprint
from meetup import get_events, debug_meetup_json
import requests

MEETUP_URL = "https://www.meetup.com/orange-county-ai/events/"


def main():
    print(f"Fetching events from {MEETUP_URL}...")

    try:
        # Option to debug the JSON structure
        if "--debug" in sys.argv:
            response = requests.get(MEETUP_URL)
            response.raise_for_status()
            debug_meetup_json(response.text, "meetup_debug.json")
            print("Saved JSON debug data to meetup_debug.json")
            return

        # Fetch and display events
        events = get_events(MEETUP_URL)

        print(f"\nFound {len(events)} events:")
        for i, event in enumerate(events, 1):
            print(f"\n--- Event {i} ---")
            print(f"Name: {event.name}")
            print(f"Date: {event.date}")
            print(f"Link: {event.link}")
            print(f"Venue: {event.venue}")
            print(f"Location: {event.location}")
            print(f"Location Link: {event.location_link}")
            print(f"Image: {event.image}")
            description_preview = (
                event.description[:200] + "..."
                if len(event.description) > 200
                else event.description
            )
            print(f"Description (preview): {description_preview}")

    except Exception as e:
        print(f"Error: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
