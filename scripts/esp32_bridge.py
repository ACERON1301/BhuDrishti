"""Forward ESP32 newline-delimited JSON telemetry to BhuDrishti.

Expected line format: {"node_id":"BD-001","sensor_window":[0.01,-0.02,...],"source":"esp32_node"}
Use --demo when a serial device is not connected.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from typing import Any

import requests


def send(api: str, payload: dict[str, Any]) -> None:
    response = requests.post(f"{api.rstrip('/')}/api/ingest", json=payload, timeout=8)
    response.raise_for_status()
    result = response.json()
    classification = result["classification"]["classification"]
    confidence = round(result["classification"]["confidence"] * 100)
    print(f"{result['node_id']}: {classification} ({confidence}% confidence)")


def demo_loop(api: str, node_id: str, interval: float) -> None:
    while True:
        event = random.random() < 0.25
        decay = [random.uniform(0.01, 0.06) for _ in range(160)]
        if event:
            decay = [1.3 * random.uniform(-1, 1) * (0.97 ** index) + random.uniform(-0.06, 0.06) for index in range(160)]
        payload = {"node_id": node_id, "sensor_window": decay, "source": "esp32_node", "battery_pct": round(random.uniform(55, 98), 1)}
        try:
            send(api, payload)
        except requests.RequestException as exc:
            print(f"send failed: {exc}")
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--port", help="Serial port, e.g. COM5")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--node-id", default="BD-001")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--interval", type=float, default=5)
    args = parser.parse_args()
    if args.demo or not args.port:
        demo_loop(args.api, args.node_id, args.interval)
        return
    import serial

    with serial.Serial(args.port, args.baud, timeout=1) as device:
        print(f"Listening on {args.port}; Ctrl+C to stop")
        while True:
            line = device.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                payload.setdefault("source", "esp32_node")
                send(args.api, payload)
            except (json.JSONDecodeError, requests.RequestException, KeyError) as exc:
                print(f"invalid telemetry: {exc}")


if __name__ == "__main__":
    main()
