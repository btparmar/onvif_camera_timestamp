"""
ONVIF Timestamp Monitor
-----------------------
Generic ONVIF implementation using raw SOAP/HTTP requests.
Works with ALL ONVIF-compliant cameras (Hikvision, Dahua, Axis, Hanwha, Bosch, etc.)

Requirements:
    pip install requests

Usage:
    python onvif_timestamp_monitor.py \
        --host 192.168.1.64 \
        --port 80 \
        --username admin \
        --password admin123 \
        --interval 5

Arguments:
    --host       Camera IP address
    --port       ONVIF service port (default: 80)
    --username   Camera username
    --password   Camera password
    --interval   Polling interval in seconds (default: 5)
    --threshold  Seconds difference to trigger "timestamp changed" (default: 2)
    --onvif-path ONVIF device service path (default: /onvif/device_service)
"""

import argparse
import hashlib
import base64
import os
import time
import datetime
import re
import sys
import logging

try:
    import requests
    from requests.auth import HTTPDigestAuth
except ImportError:
    print("Missing dependency. Run: pip install requests")
    sys.exit(1)

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("onvif_monitor")


# ─────────────────────────────────────────────
# WS-UsernameToken (digest) auth builder
# Required by most ONVIF cameras
# ─────────────────────────────────────────────
def build_wsse_header(username: str, password: str) -> str:
    """Build WS-Security UsernameToken with PasswordDigest (ONVIF standard)."""
    nonce_bytes = os.urandom(16)
    nonce_b64 = base64.b64encode(nonce_bytes).decode("utf-8")

    created = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # PasswordDigest = Base64(SHA1(nonce + created + password))
    digest_input = nonce_bytes + created.encode("utf-8") + password.encode("utf-8")
    digest = base64.b64encode(hashlib.sha1(digest_input).digest()).decode("utf-8")

    return f"""<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
                              xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
    <wsse:UsernameToken>
        <wsse:Username>{username}</wsse:Username>
        <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd#PasswordDigest">{digest}</wsse:Password>
        <wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd#Base64Binary">{nonce_b64}</wsse:Nonce>
        <wsu:Created>{created}</wsu:Created>
    </wsse:UsernameToken>
</wsse:Security>"""


# ─────────────────────────────────────────────
# SOAP envelope builder
# ─────────────────────────────────────────────
def build_soap_envelope(wsse_header: str, body: str) -> str:
    """Wrap a SOAP body in a complete SOAP envelope with WS-Security header."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope
    xmlns:s="http://www.w3.org/2003/05/soap-envelope"
    xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
    xmlns:tt="http://www.onvif.org/ver10/schema">
    <s:Header>
        {wsse_header}
    </s:Header>
    <s:Body>
        {body}
    </s:Body>
</s:Envelope>"""


# ─────────────────────────────────────────────
# ONVIF: GetSystemDateAndTime
# Defined in ONVIF Core Spec — works on ALL brands
# ─────────────────────────────────────────────
GET_DATE_TIME_BODY = "<tds:GetSystemDateAndTime/>"


def get_camera_datetime(
    session: requests.Session,
    url: str,
    username: str,
    password: str,
    timeout: int = 10,
) -> datetime.datetime | None:
    """
    Call ONVIF GetSystemDateAndTime and return the camera's UTC datetime.
    Returns None on failure.
    """
    wsse = build_wsse_header(username, password)
    envelope = build_soap_envelope(wsse, GET_DATE_TIME_BODY)

    headers = {
        "Content-Type": "application/soap+xml; charset=utf-8",
        "SOAPAction": '"http://www.onvif.org/ver10/device/wsdl/GetSystemDateAndTime"',
    }

    try:
        resp = session.post(url, data=envelope, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return parse_datetime_from_response(resp.text)
    except requests.exceptions.ConnectionError:
        log.error("Connection refused — check camera IP/port.")
    except requests.exceptions.Timeout:
        log.error("Request timed out — camera may be unreachable.")
    except requests.exceptions.HTTPError as e:
        log.error("HTTP error: %s", e)
        # Try fallback with HTTP Digest auth for cameras that don't support WS-Security
        try:
            resp = session.post(
                url,
                data=envelope,
                headers=headers,
                timeout=timeout,
                auth=HTTPDigestAuth(username, password),
            )
            resp.raise_for_status()
            return parse_datetime_from_response(resp.text)
        except Exception as fe:
            log.error("Digest auth fallback also failed: %s", fe)
    except Exception as e:
        log.error("Unexpected error: %s", e)

    return None


# ─────────────────────────────────────────────
# XML parser (no external XML lib needed)
# ─────────────────────────────────────────────
def _extract_tag(xml: str, tag: str) -> str | None:
    """Extract inner text of the first matching tag (handles namespaces)."""
    # Match both prefixed and non-prefixed tags
    pattern = rf"<(?:[^:>]+:)?{re.escape(tag)}[^>]*>(.*?)</(?:[^:>]+:)?{re.escape(tag)}>"
    m = re.search(pattern, xml, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


def parse_datetime_from_response(xml: str) -> datetime.datetime | None:
    """
    Parse camera datetime from GetSystemDateAndTime SOAP response.
    Handles both UTCDatetime and LocalDatetime fields.
    """
    try:
        # Try structured date/time fields first (standard ONVIF response)
        utc_block = _extract_tag(xml, "UTCDateTime")
        if not utc_block:
            utc_block = xml  # fallback: search the whole response

        year   = _extract_tag(utc_block, "Year")
        month  = _extract_tag(utc_block, "Month")
        day    = _extract_tag(utc_block, "Day")
        hour   = _extract_tag(utc_block, "Hour")
        minute = _extract_tag(utc_block, "Minute")
        second = _extract_tag(utc_block, "Second")

        if all([year, month, day, hour, minute, second]):
            return datetime.datetime(
                int(year), int(month), int(day),
                int(hour), int(minute), int(second),
                tzinfo=datetime.timezone.utc,
            )

        # Fallback: look for ISO 8601 datetime string
        iso_match = re.search(
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)",
            xml,
        )
        if iso_match:
            raw = iso_match.group(1).replace("Z", "+00:00")
            return datetime.datetime.fromisoformat(raw)

        log.warning("Could not parse datetime from response.")
        log.debug("Raw response: %s", xml[:500])
    except Exception as e:
        log.error("Failed to parse datetime: %s", e)

    return None


# ─────────────────────────────────────────────
# Monitor loop
# ─────────────────────────────────────────────
def monitor(
    host: str,
    port: int,
    username: str,
    password: str,
    onvif_path: str,
    interval: int,
    threshold: int,
) -> None:
    """Poll camera datetime and print alert when timestamp changes unexpectedly."""
    url = f"http://{host}:{port}{onvif_path}"
    log.info("Starting ONVIF timestamp monitor")
    log.info("  Camera URL : %s", url)
    log.info("  Poll interval : %ds | Change threshold : %ds", interval, threshold)
    log.info("  Press Ctrl+C to stop\n")

    session = requests.Session()
    session.verify = False  # Skip SSL verify for self-signed certs

    previous_dt: datetime.datetime | None = None
    previous_poll_time: datetime.datetime | None = None
    consecutive_failures = 0
    MAX_FAILURES = 5

    # Detect local timezone
    local_tz = datetime.datetime.now().astimezone().tzinfo
    local_tz_name = datetime.datetime.now().astimezone().strftime("%Z")

    def to_local(dt: datetime.datetime) -> str:
        """Convert UTC datetime to local time string."""
        return dt.astimezone(local_tz).strftime("%Y-%m-%d %H:%M:%S")

    while True:
        poll_time = datetime.datetime.now(datetime.timezone.utc)
        camera_dt = get_camera_datetime(session, url, username, password)

        if camera_dt is None:
            consecutive_failures += 1
            log.warning(
                "Failed to get camera time (%d/%d consecutive failures).",
                consecutive_failures, MAX_FAILURES,
            )
            if consecutive_failures >= MAX_FAILURES:
                log.error("Too many consecutive failures. Check camera connectivity.")
                consecutive_failures = 0  # Reset and keep trying
        else:
            consecutive_failures = 0

            if previous_dt is not None and previous_poll_time is not None:
                # Expected camera time = previous camera time + elapsed real time
                elapsed_real = (poll_time - previous_poll_time).total_seconds()
                elapsed_camera = (camera_dt - previous_dt).total_seconds()
                drift = abs(elapsed_camera - elapsed_real)

                log.info(
                    "Camera time: %s %s | Drift from expected: %.2fs",
                    to_local(camera_dt),
                    local_tz_name,
                    drift,
                )

                if drift > threshold:
                    print("\n" + "=" * 60)
                    print("⚠️  TIMESTAMP CHANGED DETECTED!")
                    print("=" * 60)
                    print(f"  Previous camera time : {to_local(previous_dt)} {local_tz_name}")
                    print(f"  Current camera time  : {to_local(camera_dt)} {local_tz_name}")
                    print(f"  Elapsed real time    : {elapsed_real:.2f}s")
                    print(f"  Elapsed camera time  : {elapsed_camera:.2f}s")
                    print(f"  Drift detected       : {drift:.2f}s (threshold: {threshold}s)")
                    print(f"  Alert at             : {to_local(poll_time)} {local_tz_name}")
                    print("=" * 60 + "\n")
                else:
                    log.info("✓ Timestamp is stable (drift: %.2fs)", drift)
            else:
                log.info(
                    "Initial camera time: %s %s",
                    to_local(camera_dt),
                    local_tz_name,
                )

            previous_dt = camera_dt
            previous_poll_time = poll_time

        time.sleep(interval)


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="ONVIF Timestamp Change Monitor — works with all ONVIF cameras"
    )
    parser.add_argument("--host",       required=True,  help="Camera IP address")
    parser.add_argument("--port",       type=int, default=80, help="ONVIF port (default: 80)")
    parser.add_argument("--username",   required=True,  help="Camera username")
    parser.add_argument("--password",   required=True,  help="Camera password")
    parser.add_argument("--interval",   type=int, default=5,  help="Poll interval in seconds (default: 5)")
    parser.add_argument("--threshold",  type=int, default=2,  help="Drift threshold in seconds to trigger alert (default: 2)")
    parser.add_argument("--onvif-path", default="/onvif/device_service", help="ONVIF device service path")
    args = parser.parse_args()

    try:
        monitor(
            host=args.host,
            port=args.port,
            username=args.username,
            password=args.password,
            onvif_path=args.onvif_path,
            interval=args.interval,
            threshold=args.threshold,
        )
    except KeyboardInterrupt:
        log.info("Monitor stopped by user.")


if __name__ == "__main__":
    main()
