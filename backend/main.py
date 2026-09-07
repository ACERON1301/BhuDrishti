from __future__ import annotations

import asyncio
import json
import random
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:  # Supports both `uvicorn main:app` from backend and `uvicorn backend.main:app`.
    from .ml.classifier import classify
    from .storage import store
except ImportError:
    from ml.classifier import classify
    from storage import store

ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = ROOT / "nepal-flood-corridor-seed-data.json"


def fallback_seed() -> dict[str, Any]:
    return {
        "region": "Koshi flood corridor, Nepal",
        "nodes": [
            {"id": "BD-001", "name": "Chatara Bridge", "lat": 26.875, "lng": 87.162, "elevation_m": 115, "status": "online", "battery_pct": 92},
            {"id": "BD-002", "name": "Barahakshetra", "lat": 26.817, "lng": 87.154, "elevation_m": 128, "status": "online", "battery_pct": 78},
        ],
        "settlements": [],
        "coverage_gaps": [],
    }


def load_seed() -> dict[str, Any]:
    try:
        return json.loads(SEED_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback_seed()


seed = load_seed()
nodes: list[dict[str, Any]] = seed.get("nodes", [])
settlements: list[dict[str, Any]] = seed.get("settlements", [])
coverage_gaps: list[dict[str, Any]] = seed.get("coverage_gaps", [])
events: list[dict[str, Any]] = []


class TelemetryIn(BaseModel):
    node_id: str = Field(..., min_length=2)
    sensor_window: list[float] = Field(..., min_length=8)
    source: Literal["esp32_node", "phone_layer"] = "esp32_node"
    water_level_cm: float = Field(0, ge=0, le=1000)
    rainfall_mm: float = Field(0, ge=0, le=1000)
    flow_rate_m3s: float = Field(0, ge=0, le=20000)
    soil_moisture_pct: float = Field(0, ge=0, le=100)
    battery_pct: float = Field(100, ge=0, le=100)
    temperature_c: float | None = Field(None, ge=-60, le=80)
    recorded_at: str | None = None


class SimulationIn(BaseModel):
    node_id: str | None = None
    severity: str = Field("random", pattern="^(random|normal|watch|critical)$")
    source: Literal["esp32_node", "phone_layer"] = "esp32_node"


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        disconnected = []
        for connection in list(self.connections):
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for connection in disconnected:
            self.disconnect(connection)


manager = ConnectionManager()
app = FastAPI(title="BhuDrishti API", version="0.1.0", description="Flood corridor telemetry prototype")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_node(node_id: str) -> dict[str, Any]:
    return next((node for node in nodes if node["id"] == node_id), None)


def build_event(telemetry: TelemetryIn) -> dict[str, Any]:
    node = find_node(telemetry.node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Unknown node: {telemetry.node_id}")
    model = classify(telemetry.sensor_window)
    recent_sources = {
        prior["source"]
        for prior in events
        if prior["node_id"] == telemetry.node_id
        and prior["classification"]["classification"] == "event"
        and (datetime.now(timezone.utc) - datetime.fromisoformat(prior["recorded_at"].replace("Z", "+00:00"))).total_seconds() <= 30
    }
    recent_sources.add(telemetry.source) if model["classification"] == "event" else None
    cross_confirmed = model["classification"] == "event" and {"esp32_node", "phone_layer"} <= recent_sources
    if cross_confirmed:
        model["confidence"] = round(min(1.0, model["confidence"] + 0.15), 4)
    event = {
        "id": f"evt-{int(datetime.now().timestamp() * 1000)}",
        "node_id": telemetry.node_id,
        "node_name": node.get("name", telemetry.node_id),
        "lat": node.get("lat"),
        "lng": node.get("lng"),
        "recorded_at": telemetry.recorded_at or utc_now(),
        "telemetry": telemetry.model_dump(),
        "classification": model,
        "source": telemetry.source,
        "confirmation": "cross-confirmed" if cross_confirmed else "unconfirmed, single-source",
    }
    node["last_seen"] = event["recorded_at"]
    node["battery_pct"] = telemetry.battery_pct
    node["status"] = "critical" if model["classification"] == "event" else "online"
    events.insert(0, event)
    del events[100:]
    return event


@app.post("/api/classify")
async def classify_window(window: list[float]) -> dict[str, Any]:
    try:
        return classify(window)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "service": "bhudrishti-api", "nodes": len(nodes), "events": len(events), "supabase": store.configured}


@app.get("/api/nodes")
async def get_nodes() -> list[dict[str, Any]]:
    return nodes


@app.get("/api/settlements")
async def get_settlements() -> list[dict[str, Any]]:
    result = []
    for settlement in settlements:
        nearest = find_node(settlement.get("nearest_node", ""))
        connected = nearest is not None and nearest.get("status") != "offline"
        result.append({
            **settlement,
            "connectivity_status": "connected" if connected else "degraded",
            "phone_layer_active": connected,
        })
    return result


@app.get("/api/coverage-gaps")
async def get_coverage_gaps() -> list[dict[str, Any]]:
    return coverage_gaps


@app.get("/api/events")
async def get_events(limit: int = 30) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(limit, 100))
    if store.configured:
        try:
            return store.list_events(bounded_limit)
        except requests.RequestException as exc:
            raise HTTPException(status_code=503, detail=f"Supabase event query failed: {exc}") from exc
    return events[:bounded_limit]


@app.post("/api/ingest")
async def ingest(telemetry: TelemetryIn) -> dict[str, Any]:
    event = build_event(telemetry)
    if store.configured:
        try:
            store.insert_event(event)
        except requests.RequestException as exc:
            raise HTTPException(status_code=503, detail=f"Supabase event insert failed: {exc}") from exc
    await manager.broadcast({"type": "telemetry", "event": event})
    return event


@app.post("/api/simulate-event")
async def simulate_event(request: SimulationIn) -> dict[str, Any]:
    node_id = request.node_id or random.choice(nodes)["id"]
    if find_node(node_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown node: {node_id}")
    severity = request.severity
    if severity == "normal":
        water, rain, flow, soil = random.uniform(70, 145), random.uniform(0, 20), random.uniform(300, 1000), random.uniform(30, 65)
    elif severity == "watch":
        water, rain, flow, soil = random.uniform(150, 250), random.uniform(20, 75), random.uniform(900, 2200), random.uniform(55, 85)
    elif severity == "critical":
        water, rain, flow, soil = random.uniform(260, 390), random.uniform(70, 180), random.uniform(2200, 4200), random.uniform(75, 99)
    else:
        water, rain, flow, soil = random.uniform(75, 350), random.uniform(0, 160), random.uniform(300, 3800), random.uniform(25, 99)
    sample_count = 160
    t = [index / 100 for index in range(sample_count)]
    import math
    import numpy as np
    rng = np.random.default_rng()
    if severity == "normal":
        window = (rng.normal(0, 0.06, sample_count)).tolist()
    else:
        amplitude = {"watch": 0.8, "critical": 1.6, "random": 1.2}.get(severity, 1.2)
        window = (amplitude * np.sin(2 * math.pi * 18 * np.asarray(t)) * np.exp(-3 * np.maximum(np.asarray(t) - 0.08, 0)) + rng.normal(0, 0.06, sample_count)).tolist()
    return await ingest(
        TelemetryIn(
            node_id=node_id,
            sensor_window=window,
            source=request.source,
            water_level_cm=round(water, 1),
            rainfall_mm=round(rain, 1),
            flow_rate_m3s=round(flow, 1),
            soil_moisture_pct=round(soil, 1),
            battery_pct=round(random.uniform(45, 98), 1),
            temperature_c=round(random.uniform(16, 29), 1),
        )
    )


@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        await websocket.send_json({"type": "snapshot", "events": events[:20], "nodes": nodes})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


@app.on_event("startup")
async def startup_event() -> None:
    # Keep the service useful immediately after startup without fabricating alert events.
    if not events:
        for node in nodes:
            node.setdefault("last_seen", utc_now())
