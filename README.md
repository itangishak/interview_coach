# AI Interview Coach

Real-time interview coaching system that analyzes body language, eye contact, facial expressions, and movement via webcam, then delivers live feedback through a browser dashboard.

**Stack:** Next.js 14 · FastAPI · MediaPipe · SQLite · WebSocket  
**Python:** 3.10 – 3.14 · **Node.js:** 18+

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Project structure](#project-structure)
3. [Clone the repository](#clone-the-repository)
4. [Backend setup](#backend-setup)
5. [Frontend setup](#frontend-setup)
6. [Running the project](#running-the-project)
7. [Configuration](#configuration)
8. [API reference](#api-reference)
9. [Running tests](#running-tests)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Install these tools before anything else.

| Tool | Minimum version | Download |
|---|---|---|
| Python | 3.10 | https://python.org/downloads |
| Node.js | 18 | https://nodejs.org |
| Git | any | https://git-scm.com |
| A webcam | — | required at runtime |

> **macOS:** Python 3 may be missing. Install via `brew install python` or from python.org.  
> **Linux:** `sudo apt install python3 python3-venv python3-pip` (Debian/Ubuntu).  
> **Windows:** Use the official python.org installer. Check "Add Python to PATH" during setup.

---

## Project structure

```
interview_coach/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/endpoints/interview.py
│   │   ├── services/
│   │   │   ├── interview_analyzer.py
│   │   │   ├── feedback_engine.py
│   │   │   └── session_service.py
│   │   ├── core/config.py
│   │   └── database/
│   ├── checkpoints/interview/
│   ├── tests/
│   ├── config.yaml
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── globals.css
│   ├── components/
│   │   ├── ConfidenceRing.tsx
│   │   ├── MetricsPanel.tsx
│   │   ├── StatusCards.tsx
│   │   ├── SparklineChart.tsx
│   │   ├── FeedbackPanel.tsx
│   │   └── SessionReport.tsx
│   ├── hooks/useInterviewSession.ts
│   ├── types/index.ts
│   └── package.json
└── README.md
```

---

## Clone the repository

```bash
git clone <your-repo-url>
cd interview_coach
```

---

## Backend setup

All commands run from the `backend/` directory.

### 1. Navigate to the backend

```bash
cd interview_coach/backend
```

### 2. Create a virtual environment

**Windows (cmd)**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks the script, run this once first:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now show `(.venv)`.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** `mediapipe` requires Python 3.10 – 3.12 for pre-built wheels.  
> On Python 3.13+ it may need to build from source — ensure you have a C++ compiler installed.  
> On **Windows**: install [Build Tools for Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/) if you see compiler errors.  
> On **macOS**: `xcode-select --install`  
> On **Linux**: `sudo apt install build-essential`

### 4. Verify the install

```bash
python -c "import mediapipe, fastapi, sqlalchemy; print('OK')"
```

Should print `OK` with no errors.

---

## Frontend setup

All commands run from the `frontend/` directory.

### 1. Navigate to the frontend

```bash
cd interview_coach/frontend
```

### 2. Install dependencies

```bash
npm install
```

### 3. (Optional) Configure the backend URL

If your backend runs on a different host or port, copy the example env file and edit it:

```bash
# macOS / Linux
cp .env.local.example .env.local

# Windows (cmd)
copy .env.local.example .env.local
```

Then open `.env.local` and set:

```env
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/interview
```

The default (`ws://localhost:8000`) works without any changes for local development.

---

## Running the project

You need two terminals running simultaneously.

### Terminal 1 — Backend

```bash
cd interview_coach/backend

# Activate venv (if not already active)
# Windows:  .venv\Scripts\activate.bat
# macOS/Linux: source .venv/bin/activate

python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

Verify it's healthy: open `http://localhost:8000/health` in a browser — you should see:
```json
{ "status": "ok", "app": "AI Interview Coach" }
```

### Terminal 2 — Frontend

```bash
cd interview_coach/frontend
npm run dev
```

Expected output:
```
▲ Next.js 14.x.x
  - Local: http://localhost:3000
✓ Ready in ~5s
```

Open `http://localhost:3000` in your browser.

---

## Using the app

1. Open `http://localhost:3000`
2. Click **Start Session** — the browser will ask for camera permission, grant it
3. The dashboard shows live metrics: eye contact, smile, posture, body movement
4. The confidence ring and sparkline update every frame
5. Click **Stop Session** to end — a session summary is automatically shown
6. Click **📋 Session Report** at any time to view the report modal

---

## Configuration

All backend tuning lives in `backend/config.yaml`. No restart is needed when using `--reload`.

```yaml
interview:
  window_size: 30        # rolling window for temporal smoothing (frames)
  target_fps: 15         # expected client frame rate
  eye_contact_good: 0.7  # iris ratio threshold for "good" eye contact
  smile_good: 0.4        # smile score threshold

mediapipe:
  model_complexity: 1              # 0 = fastest, 2 = most accurate
  min_detection_confidence: 0.5
  min_tracking_confidence: 0.5
  refine_landmarks: true           # required for iris landmark extraction

database:
  url: "sqlite:///./interview_coach.db"   # file is created automatically
```

**Confidence score weights** can also be tuned in `config.yaml` (or via `checkpoints/interview/interview_config.json` if present):

```yaml
confidence_weights:
  eye_contact:    0.30
  smile:          0.15
  posture:        0.20
  head_stability: 0.20
  body_movement:  0.15
```

---

## API reference

### Health check

```
GET /health
```
```json
{ "status": "ok", "app": "AI Interview Coach", "calibration_available": false }
```

### WebSocket — `/ws/interview`

Connect with any WebSocket client to `ws://localhost:8000/ws/interview`.

**Messages you send:**

```jsonc
// 1. Start a session
{ "type": "start", "session_id": "optional-uuid" }

// 2. Send a frame (repeat at ~15 fps)
{ "type": "frame", "image": "data:image/jpeg;base64,..." }

// 3. End the session
{ "type": "stop" }
```

**Messages you receive:**

```jsonc
// After start
{ "type": "status", "payload": { "session_id": "...", "started_at": "..." } }

// After each frame
{
  "type": "analysis",
  "payload": {
    "eye_contact": 0.82,
    "smile": 0.55,
    "posture": 0.78,
    "head_stability": 0.91,
    "body_movement": 0.74,
    "confidence": 74.0,
    "feedback": { "recommendations": ["..."] },
    "face_detected": true,
    "pose_detected": true
  }
}

// After stop
{
  "type": "summary",
  "payload": {
    "session_id": "...",
    "duration_seconds": 120,
    "total_frames": 1800,
    "metrics": {
      "eye_contact":    { "mean": 0.79, "min": 0.12, "max": 0.99 },
      "confidence":     { "mean": 71.4, "min": 30.0, "max": 95.0 }
    },
    "recommendations": ["Maintain more consistent eye contact."]
  }
}
```

### Session REST endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/interview/sessions` | List recent sessions (`?limit=20`) |
| `GET` | `/interview/sessions/{id}` | Full session record |
| `GET` | `/interview/sessions/{id}/report` | Aggregated metrics + recommendations |

Interactive docs: `http://localhost:8000/docs`

---

## Running tests

```bash
cd interview_coach/backend

# Activate venv first, then:
pytest tests/ -v
```

Tests cover:
- `test_interview_metrics.py` — unit tests for each metric function
- `test_pipeline.py` — WebSocket integration test (start → frames → stop)

---

## Troubleshooting

**`mediapipe` install fails**

Ensure your Python version is 3.10, 3.11, or 3.12. Run `python --version` to check.  
On Python 3.13+, try:
```bash
pip install mediapipe --pre
```

**Camera permission denied in browser**

Chrome and Edge require HTTPS for camera access except on `localhost`. The app runs on `localhost` so it should work. If using a remote machine, set up a reverse proxy with TLS.

**`ModuleNotFoundError: No module named 'app'`**

Make sure you run uvicorn from inside the `backend/` directory, not the project root:
```bash
cd interview_coach/backend
python -m uvicorn app.main:app --reload --port 8000
```

**WebSocket connection refused on the frontend**

- Confirm the backend is running and shows `Application startup complete`
- Check there is no firewall blocking port 8000
- If running backend on a different machine, update `NEXT_PUBLIC_WS_URL` in `.env.local`

**`Set-ExecutionPolicy` error on Windows PowerShell**

Run PowerShell as Administrator and execute:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Port already in use**

```bash
# Change the backend port
python -m uvicorn app.main:app --reload --port 8001

# Then update frontend .env.local
NEXT_PUBLIC_WS_URL=ws://localhost:8001/ws/interview
```

**SQLite database location**

The database file `interview_coach.db` is created automatically in `backend/` on first run. To reset all sessions, delete the file and restart the backend.

---

## Browser compatibility

| Feature | Chrome | Edge | Firefox | Safari |
|---|---|---|---|---|
| WebSocket | ✅ | ✅ | ✅ | ✅ |
| Webcam (getUserMedia) | ✅ | ✅ | ✅ | ✅ (macOS/iOS 14.3+) |
| Web Speech API (STT/TTS) | ✅ | ✅ | Partial | Partial |

Chrome or Edge recommended for full speech feature support.
