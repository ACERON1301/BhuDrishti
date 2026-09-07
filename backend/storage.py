"""Supabase event persistence.

The frontend never receives the service-role key. When credentials are absent, the
prototype intentionally uses its existing in-memory event buffer for local demos.
"""
from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()


class SupabaseStore:
    def __init__(self) -> None:
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def _headers(self) -> dict[str, str]:
        if not self.configured:
            raise RuntimeError("Supabase is not configured")
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

    def insert_event(self, event: dict[str, Any]) -> None:
        payload = {
            "id": event["id"],
            "node_id": event["node_id"],
            "node_name": event["node_name"],
            "lat": event["lat"],
            "lng": event["lng"],
            "recorded_at": event["recorded_at"],
            "source": event["source"],
            "confirmation": event["confirmation"],
            "classification": event["classification"]["classification"],
            "confidence": event["classification"]["confidence"],
            "features": event["classification"]["features"],
            "telemetry": event["telemetry"],
        }
        response = requests.post(
            f"{self.url}/rest/v1/events",
            headers=self._headers(),
            json=payload,
            timeout=8,
        )
        response.raise_for_status()

    def list_events(self, limit: int = 30) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.url}/rest/v1/events",
            headers={**self._headers(), "Prefer": "return=representation"},
            params={"select": "*", "order": "recorded_at.desc", "limit": limit},
            timeout=8,
        )
        response.raise_for_status()
        rows = response.json()
        return [
            {
                "id": row["id"],
                "node_id": row["node_id"],
                "node_name": row["node_name"],
                "lat": row["lat"],
                "lng": row["lng"],
                "recorded_at": row["recorded_at"],
                "source": row["source"],
                "confirmation": row["confirmation"],
                "telemetry": row["telemetry"],
                "classification": {
                    "classification": row["classification"],
                    "confidence": row["confidence"],
                    "features": row["features"],
                },
            }
            for row in rows
        ]


store = SupabaseStore()
