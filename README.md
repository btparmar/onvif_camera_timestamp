# ONVIF Timestamp Monitor

A generic ONVIF-based camera timestamp monitor that detects and alerts when a camera's clock changes unexpectedly. Works with **all ONVIF-compliant camera brands** — Hikvision, Dahua, Axis, Hanwha, Bosch, Reolink, and more.

---

## How It Works

The script calls the standard ONVIF `GetSystemDateAndTime` method (mandatory in ONVIF Core Spec) on a polling interval. It compares how much the camera clock advanced versus how much real time passed. If the difference exceeds the configured threshold, it prints a `⚠️ TIMESTAMP CHANGED` alert.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed on your machine
- An ONVIF-enabled camera with:
  - ONVIF protocol **enabled** in camera settings
  - Camera **IP address**, **username**, and **password**

---

## Project Structure

```
.
├── Dockerfile
├── onvif_timestamp_monitor.py
└── README.md
```

---

## Step 1 — Clone or Download the Files

Make sure all three files are in the same folder:

```
onvif_timestamp_monitor.py
Dockerfile
README.md
```

---

## Step 2 — Build the Docker Image

Open a terminal in the project folder and run:

```bash
docker build -t onvif-monitor .
```

Expected output:

```
[+] Building ...
 ✔ Installing tzdata
 ✔ Installing requests
 ✔ Successfully tagged onvif-monitor:latest
```

> This only needs to be done once (or after any code changes).

---

## Step 3 — Run the Monitor

```bash
docker run --rm -e TZ=Asia/Kolkata onvif-monitor \
  --host <CAMERA_IP> \
  --port 80 \
  --username <USERNAME> \
  --password <PASSWORD> \
  --interval 5 \
  --threshold 2
```

### Example

```bash
docker run --rm -e TZ=Asia/Kolkata onvif-monitor \
  --host 192.168.1.64 \
  --port 80 \
  --username admin \
  --password admin123 \
  --interval 5 \
  --threshold 2
```

---

## Configuration Flags

| Flag | Required | Default | Description |
|---|---|---|---|
| `--host` | ✅ Yes | — | Camera IP address |
| `--port` | No | `80` | ONVIF port (try `8080` if `80` fails) |
| `--username` | ✅ Yes | — | Camera login username |
| `--password` | ✅ Yes | — | Camera login password |
| `--interval` | No | `5` | Poll interval in seconds |
| `--threshold` | No | `2` | Drift in seconds to trigger alert |
| `--onvif-path` | No | `/onvif/device_service` | ONVIF service path (rarely needs changing) |

---

## Timezone Configuration

Pass your local timezone via the `-e TZ` Docker flag so timestamps display in local time.

| Region | TZ Value |
|---|---|
| India | `Asia/Kolkata` |
| UAE / Gulf | `Asia/Dubai` |
| UK | `Europe/London` |
| US Eastern | `America/New_York` |
| US Central | `America/Chicago` |
| US Pacific | `America/Los_Angeles` |
| Singapore | `Asia/Singapore` |
| China | `Asia/Shanghai` |
| Germany | `Europe/Berlin` |
| Australia (Sydney) | `Australia/Sydney` |

Full list of timezones:
```bash
timedatectl list-timezones   # Linux/macOS
```

---

## Sample Output

### Normal (stable timestamp)

```
2026-03-11 07:52:26 [INFO] Starting ONVIF timestamp monitor
2026-03-11 07:52:26 [INFO]   Camera URL  : http://192.168.1.64:80/onvif/device_service
2026-03-11 07:52:26 [INFO]   Poll interval : 5s | Change threshold : 2s

2026-03-11 07:52:27 [INFO] Initial camera time: 2026-03-11 07:52:25 IST
2026-03-11 07:52:32 [INFO] Camera time: 2026-03-11 07:52:30 IST | Drift from expected: 0.01s
2026-03-11 07:52:32 [INFO] ✓ Timestamp is stable (drift: 0.01s)
```

### Alert (timestamp changed)

```
============================================================
⚠️  TIMESTAMP CHANGED DETECTED!
============================================================
  Previous camera time : 2026-03-11 07:52:30 IST
  Current camera time  : 2026-03-11 09:15:00 IST
  Elapsed real time    : 5.02s
  Elapsed camera time  : 5229.02s
  Drift detected       : 5224.00s (threshold: 2s)
  Alert at             : 2026-03-11 07:52:35 IST
============================================================
```

---

## Troubleshooting

### Connection Refused
- Verify the camera IP is reachable: `ping <CAMERA_IP>`
- Try port `8080` instead of `80`: `--port 8080`
- Ensure ONVIF is enabled in the camera's web interface

### Authentication Failed
- Double-check username and password
- Some cameras require the ONVIF user to be created separately under **Configuration → ONVIF → Users**

### Wrong ONVIF Path
- Some cameras use a different path. Try: `--onvif-path /onvif/device_service` (default) or `/onvif/services`

### Time Still Showing UTC
- Make sure you passed `-e TZ=Your/Timezone` in the `docker run` command
- Verify your timezone string is valid (see timezone table above)

### Rebuild After Code Changes
```bash
docker build -t onvif-monitor .
```

---

## Stopping the Monitor

Press `Ctrl+C` in the terminal. The container will stop cleanly.

---

## Tested Camera Brands

| Brand | Status |
|---|---|
| Hikvision | ✅ |
| Dahua | ✅ |
| Axis | ✅ |
| Hanwha / Samsung | ✅ |
| Bosch | ✅ |
| Reolink | ✅ |
| Any ONVIF-enabled camera | ✅ |
