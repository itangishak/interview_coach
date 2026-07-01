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
7. [How the analyzer works](#how-the-analyzer-works)
8. [Configuration](#configuration)
9. [API reference](#api-reference)
10. [Running tests](#running-tests)
11. [Known limitations](#known-limitations)
12. [Troubleshooting](#troubleshooting)

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
│   │   │   ├── interview_analyzer.py   ← core metric engine
│   │   │   ├── feedback_engine.py      ← varied, context-aware coaching text
│   │   │   └── session_service.py      ← SQLite persistence
│   │   ├── core/config.py
│   │   └── database/
│   ├── checkpoints/interview/
│   │   └── interview_config.json       ← weights & thresholds
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
3. **Hold still for ~2 seconds** while the analyzer calibrates to your neutral face and posture
4. The dashboard shows live metrics: eye contact, smile, posture, head stability, body movement
5. The confidence ring and sparkline update every frame
6. Feedback messages rotate through a pool — they won't repeat the same sentence consecutively
7. Click **Stop Session** to end — a session summary is automatically shown (aggregated over valid frames only)
8. Click **📋 Session Report** at any time to view the report modal

---

## How the analyzer works

This section documents what the analyzer actually does and the design decisions behind it.

### Metrics and weights

The confidence score is a weighted sum of five behavioral metrics:

| Metric | Weight | Method |
|---|---|---|
| Eye contact | 0.30 | Iris position relative to eye-socket width |
| Posture | 0.20 | Shoulder tilt + uprightness via pose landmarks |
| Head stability | 0.20 | Nose-position variance over rolling window |
| Body movement | 0.15 | Shoulder-center + nose variance over rolling window |
| Smile | 0.15 | Mouth width/height ratio + lip-corner elevation |

### Scale normalization (Flaw A — fixed)

Every metric is normalized to a per-person reference distance so results are independent of how close you sit to the webcam:

- **Facial metrics** (smile, eye contact, head stability) are normalized by the **interocular distance** (outer eye corners, landmarks 33 and 263).
- **Body metrics** (posture, body movement) are normalized by **shoulder width** (landmarks 11 and 12).

The old version used raw frame-relative thresholds (`0.015`, `3.0`, `0.008`/`0.035`, `0.003`/`0.022`). Those constants encoded "how close you sit," not actual behavior. They have been removed.

### Head-pose compensation (Flaw B — fully fixed)

Head pose is now estimated via a **solvePnP solve** using 6 stable landmarks (nose tip, chin, eye corners, mouth corners) mapped to a canonical 3-D face model. This produces real yaw, pitch, and roll angles rather than the 2-D geometric approximation used previously.

The solve uses an estimated camera matrix derived from the frame dimensions (focal length ≈ frame width, principal point = frame centre). The rotation matrix is decomposed into Euler angles using the XYZ convention.

**Camera-above-screen pitch offset compensation** is also implemented. The webcam typically sits 8–12° above the centre of the monitor, so genuine eye contact with the on-screen interviewer is geometrically "looking slightly downward." The per-user profile stores a `camera_pitch_offset_deg` value that is subtracted from every pitch estimate. To calibrate this, call the `/interview/profiles/{user_id}/camera-offset` REST endpoint with the measured offset — or set it manually if you know your webcam position.

Frames where `|corrected yaw| > 25°` are gated (EMA frozen, excluded from aggregates). The `yaw_deg` and `pitch_deg` values are included in every analysis payload and shown live in the dashboard status cards.

### Temporal smoothing (Flaw C — fixed)

The old approach used a 30-frame brick-wall mean (`np.mean`), which caused a 1-second genuine smile to disappear into surrounding neutral frames and never clear the "Good" threshold.

Current implementation:

- An **exponential moving average** (α = 0.30) is applied to every metric so recent frames dominate.
- **Status labels** (Good / Okay / Needs improvement) use **hysteresis** (±0.05 band) to prevent rapid flicker at threshold boundaries.
- The smile metric specifically reports the **80th-percentile** of a 30-frame window rather than the mean — this captures "did you smile" rather than "what was the average lip position."

### Detection gating (Flaw D — fixed)

When detection fails, the old code fabricated neutral-to-good defaults (posture → 0.5, head stability → 1.0, body movement → 1.0). Covering your face left the confidence score looking healthy.

Current behavior:

- `iris_eye_contact_score`, `raw_smile_score`, `posture_score`, `head_stability_score`, `body_movement_score` all return `None` when their input is absent or insufficient.
- `posture_score` additionally returns `None` when MediaPipe shoulder visibility < 0.5.
- When `face_visible=False` or `raw_eye=None` (head turned beyond 25°), the frame is marked `excluded=True` and **all scores are frozen** at the last valid EMA value.
- Session summaries aggregate **only non-excluded frames**. The response includes `valid_frame_count` and `excluded_frame_count` so you can see how many frames were usable.
- The feedback panel shows "Your face isn't clearly visible — centre yourself in the frame" when the face is lost.

### Personal baseline calibration (Flaw E — fully fixed)

**In-session calibration:** during the first 2 seconds, the analyzer records raw metric values and computes a per-user neutral median. Scores are then expressed as a ratio to that baseline rather than against a universal constant.

**Persistent cross-session profiles:** at session end, the baseline is saved to a `user_profiles` SQLite table via `UserProfileService`. On the next session start, the stored baseline is loaded immediately so the user is pre-calibrated from frame one. The stored baseline evolves across sessions using an EMA blend (new session contributes 30%, stored history 70%) so it tracks gradual changes in the user's natural behavior.

**Camera offset persistence:** the per-user `camera_pitch_offset_deg` is also stored in the profile and loaded at session start. It only needs to be set once.

To use persistent profiles, pass a `user_id` in the WebSocket start message:
```json
{ "type": "start", "session_id": "...", "user_id": "alice" }
```

Anonymous sessions (no `user_id`) still get in-session calibration but nothing is persisted.

### Config thresholds — fully wired

All "good"/"okay" thresholds from `interview_config.json` now flow through the entire pipeline:

- `InterviewAnalyzer._load_config()` merges JSON thresholds over defaults per-metric
- `_label_with_hysteresis()` reads `self._threshold(metric, level)` instead of hardcoded 0.7/0.4
- `FeedbackEngine._severity()` and `_label()` call `self._good_t(metric)` / `self._okay_t(metric)` which read from the `thresholds` dict passed at construction

Previously the config `thresholds` block was loaded but never consulted — changing `smile.good` from 0.7 to 0.5 had no effect. Now it does.

| Metric | Bad | Okay | Good |
|---|---|---|---|
| Eye contact | 3 | 2 | 2 |
| Smile | 3 | 2 | 2 |
| Posture | 3 | 2 | 2 |
| Head stability | 2 | 1 | 2 |
| Body movement | 3 | 1 | 2 |

Feedback is generated per-frame and prioritizes metrics that are below "Good." When all metrics are Good, a rotating "all good" message is shown.

### What is not yet implemented

The following improvements from the system analysis remain as future work:

- **MediaPipe Tasks `FaceLandmarker` + blendshapes**: the 52 Google-trained calibrated coefficients (`mouthSmileLeft/Right`, `eyeBlinkLeft/Right`, etc.) would further improve accuracy of facial metrics. The app still uses the legacy `mp.solutions.face_mesh`.
- **Learned confidence model**: the weighted sum in `_compute_confidence` is still a fixed linear formula. The transformer/MLP scaffolding exists in `backend/app/services/` but is not wired to the interview pipeline.
- **LLM-generated feedback**: feedback is pool-based. Routing the metric summary through a language model would produce varied, contextual, session-specific coaching ("Your eye contact was strong until the technical questions…").

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
  min_detection_confidence: 0.6    # raised from 0.5 for robustness
  min_tracking_confidence: 0.6
  refine_landmarks: true           # required for iris landmark extraction

database:
  url: "sqlite:///./interview_coach.db"   # file is created automatically
```

**Confidence score weights and per-metric thresholds** can be tuned in `checkpoints/interview/interview_config.json`:

```json
{
  "window_size": 30,
  "confidence_weights": {
    "eye_contact":    0.30,
    "smile":          0.15,
    "posture":        0.20,
    "head_stability": 0.20,
    "body_movement":  0.15
  },
  "thresholds": {
    "eye_contact":    { "good": 0.7, "okay": 0.4 },
    "smile":          { "good": 0.5, "okay": 0.2 },
    "posture":        { "good": 0.7, "okay": 0.5 },
    "head_stability": { "good": 0.7, "okay": 0.4 },
    "body_movement":  { "good": 0.7, "okay": 0.4 }
  }
}
```

> **Note:** The `thresholds` block is loaded and passed to `FeedbackEngine`, but the current feedback severity logic uses hardcoded 0.7 / 0.4 boundaries. The config weights are fully honored; per-metric threshold overrides are not yet wired through.

**EMA and calibration constants** are in `interview_analyzer.py`:

| Constant | Default | Effect |
|---|---|---|
| `_EMA_ALPHA` | `0.30` | Higher = more responsive, more jitter |
| `_YAW_THRESHOLD_DEG` | `25.0` | Lower = more frames gated on head turns |
| `_CALIB_SECONDS` | `2` | Neutral calibration window at session start |
| `_SMILE_PEAK_PERCENTILE` | `80` | Higher = less sensitive to fleeting smiles |

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
// 1. Start a session (user_id optional — enables persistent baseline)
{ "type": "start", "session_id": "optional-uuid", "user_id": "optional-username" }

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
    "eye_contact":    0.82,
    "smile":          0.55,
    "posture":        0.78,
    "head_stability": 0.91,
    "body_movement":  0.74,
    "confidence":     74.0,
    "feedback": { "recommendations": ["..."] },
    "face_visible":   true,
    "pose_visible":   true,
    "excluded":       false,    // true when frame was gated (not in session aggregates)
    "yaw_deg":        -3.2,     // corrected head yaw  (camera offset subtracted)
    "pitch_deg":      1.1       // corrected head pitch
  }
}

// After stop
{
  "type": "summary",
  "payload": {
    "session_id": "...",
    "duration_seconds": 120,
    "total_frames": 1800,
    "valid_frame_count": 1743,
    "excluded_frame_count": 57,
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

### User profile endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/interview/profiles` | List all user profiles |
| `GET` | `/interview/profiles/{user_id}` | Stored baseline + camera offset for a user |
| `POST` | `/interview/profiles/{user_id}/camera-offset` | Set camera pitch offset (degrees) |

**Camera offset request body:**
```json
{ "pitch_deg": -9.5 }
```
Typical values: –8 to –12 (webcam above centre of monitor). A value of –9.5 means "the webcam is 9.5° above the screen centre; subtract that from pitch so looking at the interviewer reads as 0°."

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

## Known limitations

These are honest gaps in the current implementation.

**Geometry-based metrics, not learned ones.** Every metric is a hand-crafted formula. Results can feel inconsistent between individuals with different facial geometries or skin tones. The per-user baseline calibration and camera-offset compensation help significantly, but a learned model (trained on labeled sessions) would generalize better.

**Legacy MediaPipe Face Mesh, not blendshapes.** The app uses `mp.solutions.face_mesh` rather than the modern MediaPipe Tasks `FaceLandmarker` with blendshapes. The 52 Google-calibrated blendshape coefficients (`mouthSmileLeft/Right`, `eyeBlinkLeft/Right`, etc.) would make facial metrics more robust across individuals. Switching is the highest-leverage remaining improvement.

**Linear confidence formula.** `_compute_confidence` is a weighted dot-product. Head-stability and body-movement metrics initialize high and degrade slowly, which can make the confidence score feel slightly optimistic at the start of a session before the EMA converges.

**Approximate camera matrix in solvePnP.** The focal length is estimated as `frame_width` and the principal point as frame centre. For wide-angle webcams or cameras with distortion, a proper calibration (e.g. OpenCV `calibrateCamera` with a checkerboard) would improve pose accuracy.

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

**Metrics feel sluggish or don't respond to changes**

The EMA alpha (0.30) and 30-frame window are intentional. If you want faster response, raise `_EMA_ALPHA` toward 0.5 in `interview_analyzer.py` and lower `window_size` in `interview_config.json`. More responsiveness means more jitter.

**Smile never reaches "Good"**

Check your camera framing — you should fill at least 1/3 of the frame vertically. The smile metric now normalizes by interocular distance so extreme distances (face very small in frame) or very close distances both work, but MediaPipe's landmark accuracy degrades when the face is too small.

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
