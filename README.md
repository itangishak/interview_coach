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
8. [Software engineering architecture](#software-engineering-architecture)
9. [Configuration](#configuration)
10. [API reference](#api-reference)
11. [Running tests](#running-tests)
12. [Known limitations](#known-limitations)
13. [Troubleshooting](#troubleshooting)

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
│   │   ├── main.py                        ← FastAPI app factory
│   │   ├── api/
│   │   │   └── endpoints/
│   │   │       └── interview.py           ← WebSocket + REST endpoints
│   │   ├── core/
│   │   │   ├── config.py                  ← Singleton settings (YAML + descriptors)
│   │   │   ├── decorators.py              ← @validate_score @log_call @retry @memoize
│   │   │   ├── iterators.py               ← FrameWindowIterator, SentenceTokenIterator,
│   │   │   │                                 generators (metric_history, frame_chunk)
│   │   │   └── singleton.py               ← Thread-safe SingletonMeta metaclass
│   │   ├── services/
│   │   │   ├── interview_analyzer.py      ← Core metric engine (MediaPipe)
│   │   │   ├── metric_scorers.py          ← ABC hierarchy: 5 concrete scorer classes
│   │   │   ├── feedback_engine.py         ← BaseFeedbackEngine → CoachingFeedbackEngine
│   │   │   ├── session_service.py         ← Singleton + contextmanager + generators
│   │   │   ├── user_profile_service.py    ← Singleton + typed UserProfileData dataclass
│   │   │   └── sentence_assembler.py      ← Iterator + generator + dunder methods
│   │   ├── database/
│   │   │   ├── models.py                  ← SQLAlchemy ORM models
│   │   │   └── db_manager.py             ← Singleton database manager
│   │   └── utils/
│   ├── checkpoints/interview/
│   │   └── interview_config.json          ← Weights & thresholds (fully wired)
│   ├── tests/
│   │   ├── test_interview_metrics.py      ← 46 metric + pipeline tests
│   │   └── test_patterns.py               ← 63 software-engineering pattern tests
│   ├── config.yaml
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── globals.css                    ← CSS token system (dark + light theme)
│   ├── components/
│   │   ├── ConfidenceRing.tsx
│   │   ├── MetricsPanel.tsx
│   │   ├── StatusCards.tsx                ← Shows yaw_deg + pitch_deg live
│   │   ├── SparklineChart.tsx
│   │   ├── FeedbackPanel.tsx
│   │   └── SessionReport.tsx
│   ├── hooks/useInterviewSession.ts
│   ├── types/index.ts
│   └── package.json
├── interview_coach/
│   ├── ANALYSIS_AND_IMPROVEMENTS.md      ← v1 original diagnostic report
│   └── ANALYSIS_AND_IMPROVEMENTS_v2.md   ← v2 improvement plan
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

### Metrics and weights

The confidence score is a weighted sum of five behavioral metrics:

| Metric | Weight | Source |
|---|---|---|
| Eye contact | 0.30 | Iris position relative to eye-socket width (ICD-normalized) |
| Posture | 0.20 | Shoulder tilt + lean penalty + hip angle (shoulder-width-normalized) |
| Head stability | 0.20 | Nose-position std over rolling window (ICD-normalized, coeff=0.06) |
| Body movement | 0.15 | Shoulder + nose variance (shoulder-width-normalized, floor=0.0003) |
| Smile | 0.15 | Mouth ratio + lip elevation + cheek-squint proxy |

### Scale normalization

Every metric is normalized to a per-person reference distance — interocular distance (ICD, landmarks 33↔263) for facial metrics and shoulder width (landmarks 11↔12) for body metrics. Results are therefore independent of camera distance.

### 3-D head-pose estimation

Head pose is estimated via `cv2.solvePnP` using 6 stable landmarks (nose, chin, eye corners, mouth corners) mapped to a canonical 3-D face model. The rotation matrix is decomposed into Euler angles (XYZ convention) to produce yaw, pitch, and roll in degrees.

A per-user `camera_pitch_offset_deg` is subtracted from every pitch estimate so genuine eye contact with the on-screen interviewer reads as ~0°. Frames where `|corrected yaw| > 25°` are gated — scores are frozen at the last valid EMA value and excluded from session aggregates.

### Temporal smoothing

- **Exponential moving average** (α = 0.30 for most metrics, 0.45 for smile) replaces the old brick-wall window mean.
- **Status labels** use a ±0.05 hysteresis band to prevent rapid flicker at boundaries.
- **Smile** reports the 80th-percentile of a 30-frame rolling window before the EMA, so a genuine 1-second smile clears the threshold even with surrounding neutral frames.

### Detection gating

When detection fails, all metric functions return `None`. In `analyze_frame`, frames where `face_visible=False` or `raw_eye=None` (head turned) are marked `excluded=True`. The internal EMA state is frozen (for smooth warm-up when detection returns), but the emitted payload values drop to 0 — the frontend shows "—" rather than a stale frozen number.

Session summaries aggregate only non-excluded frames; the summary includes `valid_frame_count` and `excluded_frame_count`.

### Personal baseline calibration

During the first 2 seconds, the analyzer records raw metric values and computes a per-user neutral median. All subsequent scores are expressed as a ratio to that baseline (value / baseline, clamped 0–1).

Baselines persist across sessions in the `user_profiles` SQLite table via `UserProfileService`. The stored baseline evolves using an EMA blend (30% new session, 70% stored history). Pass a `user_id` in the WebSocket start message to enable persistence:

```json
{ "type": "start", "session_id": "...", "user_id": "alice" }
```

### Smile improvements

The smile metric now combines three signals:
- **Ratio score** — mouth width / height (suppressed when jaw is open to avoid false negatives during speech)
- **Elevation score** — lip-corner elevation normalized by ICD
- **Cheek-squint score** — y-gap between eye outer corner and infraorbital region (landmarks 33/263 ↔ 116/345), which contracts during genuine Duchenne smiles

Blend: 70% mouth geometry, 30% cheek squint.

### Posture improvements

The posture score now includes:
- **Shoulder tilt** normalized by shoulder width (as before)
- **Lean penalty** — nose-to-shoulder-midpoint y-distance relative to shoulder width (penalizes leaning too far back)
- **Hip uprightness check** — spine angle from shoulder midpoint to hip midpoint (landmarks 23/24) when visible

---

## Software engineering architecture

The backend applies every major Python software-engineering pattern deliberately and verifiably. All patterns are covered by 63 dedicated unit tests in `tests/test_patterns.py`.

For the full implementation writeup, see [software engineering development.md](software%20engineering%20development.md) in the project root.

Quick reference:

| Pattern | Primary file | Key element |
|---|---|---|
| Singleton + metaclass | `core/singleton.py` | `SingletonMeta` with `threading.Lock` |
| Decorator factory | `core/decorators.py` | `@validate_score`, `@log_call`, `@retry`, `@memoize` |
| Closure | `services/metric_scorers.py` | `make_ema_fn`, `make_threshold_checker` |
| Abstract Base Class | `services/metric_scorers.py` | `BaseMetricScorer(ABC)` |
| Inheritance | `services/metric_scorers.py` | 5 concrete scorers extend `BaseMetricScorer` |
| Polymorphism | `services/metric_scorers.py` | Each subclass overrides `score()` differently |
| Generator | `core/iterators.py` | `metric_history_generator`, `frame_chunk_generator` |
| Iterator protocol | `core/iterators.py` | `FrameWindowIterator`, `SentenceTokenIterator` |
| Dataclass | `core/iterators.py`, `services/` | `MetricResult(slots=True)`, `FrameWindow(slots=True)` |
| contextmanager | `services/session_service.py` | `session_scope(id, /, *, fps)` |
| `@property` / `@classmethod` / `@staticmethod` | `services/metric_scorers.py` | `ema_value`, `from_config`, `normalize_to_unit_range` |
| `__repr__` / `__str__` / `__len__` / `__contains__` | all service classes | standard dunder coverage |
| Positional-only `/` | throughout | `score(value, /)`, `from_config(cfg, /)` |
| Keyword-only `*` | throughout | `update(raw, *, valid)`, `update_camera_offset(id, /, *, pitch_deg)` |

---

## Configuration

All backend tuning lives in `backend/config.yaml`. No restart is needed when using `--reload`.

```yaml
interview:
  window_size: 30        # rolling window for temporal smoothing (frames)
  target_fps: 15         # expected client frame rate
  eye_contact_good: 0.7
  smile_good: 0.4

mediapipe:
  model_complexity: 1
  min_detection_confidence: 0.6
  min_tracking_confidence: 0.6
  refine_landmarks: true           # required for iris landmark extraction

database:
  url: "sqlite:///./interview_coach.db"
```

**Confidence weights and per-metric thresholds** are in `checkpoints/interview/interview_config.json`:

```json
{
  "window_size": 30,
  "confidence_weights": {
    "eye_contact": 0.30, "smile": 0.15,
    "posture": 0.20, "head_stability": 0.20, "body_movement": 0.15
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

Thresholds are fully wired — changing `smile.good` to `0.5` changes both the feedback label and the severity bucket without any code edit.

**EMA and calibration constants** in `interview_analyzer.py`:

| Constant | Default | Effect |
|---|---|---|
| `_EMA_ALPHA` | `0.30` | Higher = more responsive, more jitter |
| `_EMA_ALPHA_SMILE` | `0.45` | Faster EMA for short genuine smiles |
| `_YAW_THRESHOLD_DEG` | `25.0` | Lower = more frames gated on head turns |
| `_CALIB_SECONDS` | `2` | Neutral calibration window at session start |
| `_SMILE_PEAK_PERCENTILE` | `80` | Higher = less sensitive to fleeting smiles |
| `_MOVEMENT_FLOOR` | `0.0003` | Tightened from 0.003 — desk-still baseline |
| `_MOVEMENT_CEIL` | `0.018` | Tightened from 0.047 — realistic fidget ceiling |
| `_STABILITY_COEFF` | `0.06` | Tightened from 0.15 — small head movements register |

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

**Messages you send:**

```jsonc
// Start (user_id optional — enables persistent baseline)
{ "type": "start", "session_id": "optional-uuid", "user_id": "optional-username" }

// Send a frame (~15 fps)
{ "type": "frame", "image": "data:image/jpeg;base64,..." }

// End the session
{ "type": "stop" }
```

**Analysis payload received per frame:**

```jsonc
{
  "type": "analysis",
  "payload": {
    "eye_contact":    0.82,
    "smile":          0.55,
    "posture":        0.78,
    "head_stability": 0.91,
    "body_movement":  0.74,
    "confidence":     74.0,
    "feedback":       { "recommendations": ["..."] },
    "face_visible":   true,
    "pose_visible":   true,
    "excluded":       false,
    "yaw_deg":        -3.2,
    "pitch_deg":       1.1
  }
}
```

**Summary payload received on stop:**

```jsonc
{
  "type": "summary",
  "payload": {
    "session_id":            "...",
    "duration_seconds":      120,
    "total_frames":          1800,
    "valid_frame_count":     1743,
    "excluded_frame_count":  57,
    "confidence_p25":        62.1,
    "confidence_p75":        81.4,
    "metrics": {
      "eye_contact": { "mean": 0.79, "min": 0.12, "max": 0.99 },
      "confidence":  { "mean": 71.4, "min": 30.0, "max": 95.0 }
    },
    "recommendations": ["..."]
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
| `GET` | `/interview/profiles/{user_id}` | Stored baseline + camera offset |
| `POST` | `/interview/profiles/{user_id}/camera-offset` | Set camera pitch offset (degrees) |

Camera offset body: `{ "pitch_deg": -9.5 }`. Typical value: −8 to −12° (webcam above screen centre).

Interactive docs: `http://localhost:8000/docs`

---

## Running tests

```bash
cd interview_coach/backend
pytest tests/ -v
```

Test files:

| File | Tests | What it covers |
|---|---|---|
| `test_interview_metrics.py` | 46 | All five metric functions, EMA, hysteresis, detection gating, solvePnP, persistent profiles |
| `test_patterns.py` | 63 | Every software-engineering pattern: Singleton, decorators, closures, iterators, generators, ABC hierarchy, dataclasses, `contextmanager`, dunder methods |

Run only the patterns suite:
```bash
pytest tests/test_patterns.py -v
```

Run only metrics (skipping DB-heavy tests):
```bash
pytest tests/test_interview_metrics.py -v -k "not TestSessionService and not TestUserProfileService and not test_analyzer_loads"
```

---

## Known limitations

**Geometry-based metrics, not learned ones.** Every metric is a hand-crafted formula. A learned model trained on labeled sessions would generalize better across individuals.

**Legacy MediaPipe Face Mesh, not blendshapes.** The 52 Google-calibrated blendshape coefficients (`mouthSmileLeft/Right`, `eyeBlinkLeft/Right`, etc.) would improve facial metric accuracy. Switching to MediaPipe Tasks `FaceLandmarker` is the highest-leverage remaining improvement.

**Linear confidence formula.** `_compute_confidence` is a weighted dot-product. A small learned model (gradient-boosted or shallow MLP) would produce more differentiated scores.

**Approximate camera matrix in solvePnP.** Focal length is estimated as `frame_width`. A proper OpenCV calibration with a checkerboard would improve pose accuracy for wide-angle lenses.

**Session-scoped calibration resets.** The 2-second calibration happens fresh each session and persists via `UserProfileService` for named users. Anonymous sessions (no `user_id`) never persist baselines.

---

## Troubleshooting

**`mediapipe` install fails**

Ensure Python 3.10–3.12. On 3.13+: `pip install mediapipe --pre`

**Camera permission denied in browser**

Chrome/Edge require HTTPS except on `localhost`. For remote machines set up a TLS reverse proxy.

**`ModuleNotFoundError: No module named 'app'`**

Run uvicorn from inside `backend/`:
```bash
cd interview_coach/backend
python -m uvicorn app.main:app --reload --port 8000
```

**Metrics feel sluggish**

Raise `_EMA_ALPHA` toward 0.5 in `interview_analyzer.py` and lower `window_size` in `interview_config.json`. More responsiveness comes with more jitter.

**Movement always 100% / stability always 100%**

Check that `_MOVEMENT_FLOOR = 0.0003` and `_STABILITY_COEFF = 0.06` are in place in `interview_analyzer.py`. The old values (0.003 / 0.15) caused permanent ceiling clipping for normal desk behavior.

**Smile never reaches "Good"**

Fill at least 1/3 of the frame vertically. MediaPipe landmark accuracy degrades on small faces. The cheek-squint proxy helps when the mouth is open during speech.

**Port already in use**

```bash
python -m uvicorn app.main:app --reload --port 8001
# Then: NEXT_PUBLIC_WS_URL=ws://localhost:8001/ws/interview
```

**SQLite reset**

Delete `backend/interview_coach.db` and restart the backend.

---

## Browser compatibility

| Feature | Chrome | Edge | Firefox | Safari |
|---|---|---|---|---|
| WebSocket | ✅ | ✅ | ✅ | ✅ |
| Webcam (getUserMedia) | ✅ | ✅ | ✅ | ✅ (macOS/iOS 14.3+) |
| Web Speech API | ✅ | ✅ | Partial | Partial |

Chrome or Edge recommended.
