#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "requests",
#   "icalendar",
# ]
# ///

# Get waste collection dates from the Omrin API and convert this into an ics file.
#
# The app now authenticates with a REST login call (postal code + house number,
# no account needed) and fetches the calendar through a GraphQL query.

import uuid
import requests
import sys
import argparse
from datetime import datetime, date, time, timedelta
from icalendar import Calendar, Event

BASE_URL = "https://api.omrinafvalapp.nl"
GRAPHQL_URL = f"{BASE_URL}/graphql"

FETCH_CALENDAR_QUERY = (
    "{fetchCalendar {id, date, description, type, containerType, placingTime, state}}"
)

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Fetch waste collection dates from Omrin API and generate an iCal file."
    )
    parser.add_argument(
        "postal_code",
        help="The postal code for the location (e.g., 8921HA)."
    )
    parser.add_argument(
        "house_number",
        type=int,
        help="The house number for the location (e.g., 123)."
    )
    parser.add_argument(
        "-e", "--extension",
        help="The house number extension, if any (e.g., A).",
        default=None
    )
    parser.add_argument(
        "-o", "--output",
        help="File path to save the iCal file (e.g., omrin.ics). If not provided, prints to stdout.",
        type=str
    )
    return parser.parse_args()

def get_access_token(postal_code, house_number, house_number_extension):
    """Log in (without an account) using the address to obtain a bearer token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "PostalCode": postal_code,
            "HouseNumber": house_number,
            "HouseNumberExtension": house_number_extension,
            "DeviceId": str(uuid.uuid4()),
            "Email": None,
            "Password": None,
            "Platform": "iCal",
            "AppVersion": "1.0.0.0",
            "OsVersion": "omrin2ics",
        },
        timeout=30,
    ).json()

    if not response.get("success") or not response.get("data"):
        errors = response.get("errors") or []
        message = "; ".join(e.get("message", str(e)) for e in errors) or "unknown error"
        raise ValueError(f"Failed to log in to the Omrin API: {message}")

    access_token = response["data"].get("accessToken")
    if not access_token:
        raise ValueError("Login response did not contain an access token.")
    return access_token

def fetch_calendar_data(access_token):
    """Fetch waste collection calendar data from the Omrin GraphQL API."""
    response = requests.post(
        GRAPHQL_URL,
        json={"query": FETCH_CALENDAR_QUERY},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
    ).json()

    if response.get("errors"):
        message = "; ".join(e.get("message", str(e)) for e in response["errors"])
        raise ValueError(f"Failed to fetch data from the Omrin API: {message}")

    return response.get("data", {}).get("fetchCalendar") or []

def create_calendar(calendar_data):
    """Create an iCal calendar from the retrieved data."""
    cal = Calendar()
    cal.add('prodid', '-//WasteCollection//omrin.nl//')
    cal.add('version', '2.0')

    for item in calendar_data:
        date_value = item.get('date')
        if not date_value:
            continue

        item_date = date.fromisoformat(date_value)
        description = item['description']
        summary = f"{item.get('type', '')} ({item.get('containerType', '')})".replace("(PRIVATE)", "").strip().title()

        # Create an event for each waste collection moment
        event = Event()
        event.add('summary', summary)
        event.add('description', description)
        event.add('dtstart', item_date)
        event.add('dtend', item_date + timedelta(days=1))
        event.add('uid', f"omrin-{item_date.isoformat()}-{summary}@omrin.nl")
        event.add('transp', 'TRANSPARENT')  # Make events not show up as 'busy'

        cal.add_component(event)

    return cal

def main():
    args = parse_arguments()
    postal_code = args.postal_code
    house_number = args.house_number
    house_number_extension = args.extension
    output_file = args.output

    try:
        # Log in with the address to obtain a bearer token
        access_token = get_access_token(postal_code, house_number, house_number_extension)

        # Fetch calendar data via GraphQL
        calendar_data = fetch_calendar_data(access_token)

        # Create the calendar
        cal = create_calendar(calendar_data)
        ical_data = cal.to_ical().decode('utf-8')

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(ical_data)
            print(f"iCal file saved to {output_file}")
        else:
            print(ical_data)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
