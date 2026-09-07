# BhuDrishti

BhuDrishti is a runnable prototype for Trishuli/Bhote Koshi flood-corridor telemetry in
the Rasuwa/Nuwakot region of Nepal. It combines a
FastAPI service, an explainable scikit-learn classifier, and a Vite/React dashboard with a
Leaflet map, live waveform, coverage-gap view, and simulated ESP32 events.

## Quick start

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API is available at `http://localhost:8000/docs`. The service loads
`nepal-flood-corridor-seed-data.json` from the repository root and falls back to built-in
data if the file is missing.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Set `VITE_API_URL` when the API is not running on port 8000.

### Supabase event history

Events are persisted by the backend to Supabase when `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` are configured. Copy `.env.example` to `.env`, fill in the
backend-only credentials, and run `supabase/events.sql` in the Supabase SQL editor.
The service-role key must never be added to the frontend or committed to source control.
Without these variables, the app uses the in-memory prototype buffer.

### ESP32 bridge

`scripts/esp32_bridge.py` can forward newline-delimited JSON from a serial port to the
ingest endpoint:

```powershell
python scripts/esp32_bridge.py --port COM5 --api http://localhost:8000
```

It also supports `--demo` to emit synthetic telemetry without hardware.

## API overview

* `GET /api/nodes`, `/api/settlements`, `/api/coverage-gaps` — map and status data.
* `POST /api/classify` — classify a raw vibration window and return the extracted features.
* `POST /api/ingest` — validate a sensor reading window, classify it, persist it in memory, and
  broadcast the event to websocket clients.
* `POST /api/simulate-event` — create a realistic event for a selected node.
* `GET /api/events` — recent readings and model decisions (from Supabase when configured).
* `WS /ws/live` — JSON event stream for dashboard clients.

The model is an explainable logistic regression trained on deterministic synthetic vibration
windows: low-amplitude ambient noise versus a sharp attack and exponential-decay collapse
signature. Every prediction returns peak amplitude, RMS, zero-crossing rate, dominant FFT
frequency, duration, and decay envelope. Run `python scripts/retrain_model.py` to regenerate
`backend/model_artifact.json`. Replace `synthetic_training_data` in `backend/model.py` with
labelled sensor-collected or USGS windows when real data is available.

This is a demonstration system, not a safety-critical warning service.
# BhuDrishti
