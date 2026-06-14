#!/usr/bin/env python3
"""
phone_ping.py — probe a phone number locally (no external API).

Uses the bundled phonenumbers library (an offline port of Google's
libphonenumber) to validate and describe a number without any network call.

Usage:
    python phone_ping.py +14155552671
    python phone_ping.py 07911123456 --region GB
    python phone_ping.py +49301234567 --json
"""

import argparse
import json
import sys

try:
    import phonenumbers
    from phonenumbers import (
        geocoder,
        carrier,
        timezone,
        PhoneNumberType,
    )
except ImportError:
    sys.exit(
        "phonenumbers package not found.\n"
        "Install it with:  pip install phonenumbers"
    )

_TYPE_LABELS = {
    PhoneNumberType.FIXED_LINE: "fixed-line",
    PhoneNumberType.MOBILE: "mobile",
    PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed-line-or-mobile",
    PhoneNumberType.TOLL_FREE: "toll-free",
    PhoneNumberType.PREMIUM_RATE: "premium-rate",
    PhoneNumberType.SHARED_COST: "shared-cost",
    PhoneNumberType.VOIP: "voip",
    PhoneNumberType.PERSONAL_NUMBER: "personal-number",
    PhoneNumberType.PAGER: "pager",
    PhoneNumberType.UAN: "uan",
    PhoneNumberType.VOICEMAIL: "voicemail",
    PhoneNumberType.UNKNOWN: "unknown",
}


def ping(number_str: str, region: str | None = None) -> dict:
    """Parse and probe *number_str*, returning a result dict."""
    try:
        parsed = phonenumbers.parse(number_str, region)
    except phonenumbers.NumberParseException as exc:
        return {"input": number_str, "valid": False, "error": str(exc)}

    valid = phonenumbers.is_valid_number(parsed)
    possible = phonenumbers.is_possible_number(parsed)
    line_type = phonenumbers.number_type(parsed)

    result = {
        "input": number_str,
        "valid": valid,
        "possible": possible,
        "e164": phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        ),
        "international": phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
        ),
        "national": phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.NATIONAL
        ),
        "country_code": parsed.country_code,
        "region": phonenumbers.region_code_for_number(parsed),
        "line_type": _TYPE_LABELS.get(line_type, "unknown"),
        "location": geocoder.description_for_number(parsed, "en") or None,
        "carrier": carrier.name_for_number(parsed, "en") or None,
        "timezones": list(timezone.time_zones_for_number(parsed)),
    }
    return result


def _print_human(result: dict) -> None:
    if not result.get("valid") and result.get("error"):
        print(f"ERROR  : {result['error']}")
        return

    status = "VALID" if result["valid"] else ("POSSIBLE" if result["possible"] else "INVALID")
    print(f"Status      : {status}")
    print(f"E.164       : {result['e164']}")
    print(f"International: {result['international']}")
    print(f"National    : {result['national']}")
    print(f"Country code: +{result['country_code']}")
    print(f"Region      : {result['region']}")
    print(f"Line type   : {result['line_type']}")
    if result["location"]:
        print(f"Location    : {result['location']}")
    if result["carrier"]:
        print(f"Carrier     : {result['carrier']}")
    if result["timezones"]:
        print(f"Timezones   : {', '.join(result['timezones'])}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe a phone number locally (offline, no external API).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("number", help="Phone number to probe (E.164 or local format)")
    parser.add_argument(
        "--region",
        metavar="CC",
        help="ISO 3166-1 alpha-2 region hint for local-format numbers (e.g. US, GB)",
    )
    parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Output as JSON"
    )
    args = parser.parse_args()

    result = ping(args.number, args.region)

    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        _print_human(result)

    sys.exit(0 if result.get("valid") else 1)


if __name__ == "__main__":
    main()
