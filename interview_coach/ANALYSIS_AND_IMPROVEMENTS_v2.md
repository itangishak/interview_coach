# AI Interview Coach — System Analysis & Improvement Plan v2

> Written after a full code trace of the current implementation.
> Version 1 diagnosed the five system-wide flaws (A–E) and proposed ideas.
> Version 2 focuses on three new axes of work:
> 1. The remaining accuracy problems (why metrics lie even now)
> 2. The "Diagnostic Mode" feature (overlays + raw signal inspection)
> 3. Light / Dark theming
>
> **No code in this document.** The purpose is to reason clearly about what
> to do and why, so the implementation decisions are made before touching files.

---

## Part 1 — Accuracy Problems: Root Causes and Fixes

### 1.1  The biggest bug: frozen EMA values emitted when no face is present

**What the code does today**

In `analyze_frame`, when `excluded = True` (no face, or head turned past 25°),
the code reads the last values from `self._ema` and emits them directly:

```
eye_contact    = self._ema["eye_contact"]   # ← frozen
smile          = self._ema["smile"]         # ← frozen
posture        = self._ema["posture"]       # ← frozen
head_stability = self._ema["head_stability"]# ← frozen
body_movement  = self._ema["body_movement"] # ← frozen
```

Then those frozen values are rounded and put into the payload the frontend
receives. So the user sees `eye_contact: 66%` with `face_visible: false`
sitting right next to it.

The EMA is initialized to:

| Metric         | Init value | Why it looks high/suspicious |
|----------------|------------|-------------------------------|
| eye_contact    | 0.5        | After a few good frames, drifts to ~0.66 and stays there |
| posture        | 0.8        | Starts at 80%, never falls without a pose reading |
| head_stability | 1.0        | Starts at 100% and stays there if no movement data |
| body_movement  | 1.0        | Starts at 100% for the same reason |
| smile          | 0.0        | Only one that starts low |

The original design intent was: "freeze rather than fabricate." That was
correct for the session **aggregate** (which does filter excluded frames).
But it was a mistake to emit the frozen value in the **live payload** as if
it were a real measurement. The user sees 66% eye contact while their face
is hidden.

**What to do instead**

Separate two concerns that are currently conflated:

- `self._ema[key]` = internal EMA state, used to seed the next real reading
  when detection returns. This should keep the frozen value — that is fine.
- The **emitted value** in the payload = what the frontend displays. This
  should be `null` (or explicitly `0`) when the frame is excluded.

Concretely: the payload should carry a parallel `"valid": false` flag per
metric, or the numeric values should be `null` / `None` when `excluded=True`.
The frontend then renders "—" or 0 accordingly.

The `_ema` dict itself must remain frozen so the EMA warm-up is instant when
the face returns. Only the transmitted value changes.

**Frontend side**

`MetricsPanel.tsx` currently reads `analysis?.eye_contact ?? 0` — the `?? 0`
fallback means it defaults to 0 only when `analysis` is entirely null, not
when the face is missing. It needs to additionally check `analysis.face_visible`
(and `analysis.pose_visible` for body metrics) and display `—` or `0` when
absent.

Same for `ConfidenceRing` — a ring showing 74% while `face_visible: false` is
actively misleading. It should show a "no signal" state.

The status pills in `page.tsx` already check `analysis.face_detected` and show
"No face" correctly. The metric cards do not. Fixing the cards is the highest
priority change in the frontend.

---

### 1.2  Movement and stability always at 100%

**Root cause: the normalization denominator is too large**

`body_movement_score` maps:

```python
score = 1.0 - (combined - 0.003) / 0.047
```

`combined` is the sum of shoulder variance / shoulder_width², head variance /
shoulder_width², and mean displacement / shoulder_width. In practice, for a
person sitting normally at a desk, `combined` almost never exceeds 0.003
(the lower anchor). The result clips to 1.0 constantly.

The constants `0.003` and `0.047` were chosen empirically without a calibration
dataset. They are too lenient — "still" is defined as anything below
`combined = 0.003`, which covers nearly all normal behavior.

`head_stability_score` has a similar issue:

```python
std_norm = std / (icd * 0.15 + 1e-6)
score    = 1.0 - std_norm
```

If `icd ≈ 0.10` (a face that occupies about 10% of the frame width), the
denominator is `0.015`. The nose position std in normalized coordinates for
a still head is typically `0.001–0.003`, making `std_norm ≈ 0.07–0.20` and
the score `0.80–0.93`. Scores rarely fall below 0.70, so the metric almost
always reads "Good."

**What to do**

The correct fix is to re-tune these constants using real data — record 3–5
minutes of actual webcam footage spanning still and actively moving behavior,
compute the distribution of `combined` and `std_norm`, and set the anchors at
the 10th and 90th percentiles of that distribution. This takes one afternoon of
data collection.

Without data, the pragmatic fix is to tighten the "still" anchor:

- For body movement: lower the `0.003` anchor to `0.0005` so that typical desk
  fidgeting registers. Re-tune `0.047` to `0.020` so the full range is used.
- For head stability: tighten the `0.15` multiplier to `0.06` so that the
  std denominator is smaller and normal small movements register.

These numbers should be moved into `interview_config.json` so they can be
tuned without touching source code.

**Warm-up period**

For the first `window_size` frames (~2 seconds at 15 fps), the buffers have
fewer than `window_size` entries. Both functions still return a score, but it is
based on fewer samples and may be artificially stable. The frontend receives
`calibrating: true` in the feedback payload during this window — but the metric
cards display numbers anyway, ignoring the flag. The cards should show a
"Calibrating…" state (greyed out, "—" values) until `calibrating` is false.

---

### 1.3  Posture is too permissive

**What the metric measures**

`posture_score` measures two things:

1. Shoulder tilt: `shoulder_diff / (sw * 0.4)` — if the tilt is less than 40%
   of shoulder width, score is close to 1.0.
2. Uprightness: `nose[1] < min(ls[1], rs[1])` in image y-coordinates (y
   increases downward). If the nose landmark y is above the shoulder y values,
   the person is considered upright.

**Problems**

- **The uprightness test is coarse.** If a person leans forward significantly
  but their nose is still above their shoulders in frame, they score perfectly
  upright. The check ignores the angle of lean or the distance between nose
  and shoulder.
- **Shoulder visibility threshold is 0.5.** MediaPipe pose visibility is not
  well calibrated — a score of 0.5 on a partially visible shoulder is common.
  The function returns `None` when either shoulder is below 0.5, which
  propagates to a frozen EMA value rather than a 0 or explicit "not measured."
- **No front/back lean detection.** Forward lean (engagement) and backward
  lean (slouching) are both missed because only vertical tilt is measured.
  The z-coordinate from MediaPipe Pose is available but unused.

**What to do**

- Add a lean penalty: measure the signed distance (in y) from nose to
  shoulder midpoint, normalized by shoulder width. A healthy posture has the
  nose roughly 1.5–2× the shoulder width above the shoulder center. Significant
  deviation should reduce the score.
- Raise the shoulder visibility threshold to 0.65 to reduce false "okay"
  readings on partially visible shoulders.
- Consider adding a spine-angle estimate from the hip midpoint (landmarks 23, 24)
  to shoulder midpoint (11, 12) — this is available from the pose model and gives
  a much more accurate uprightness signal.

---

### 1.4  Eye contact metric does not account for looking-at-screen vs. camera

**Current behavior**

The iris offset measures how centered the iris is within the eye socket.
When both irises are centered, the score is high. This is a decent proxy for
"looking at the camera" only when the camera is directly in front of the
eyes at screen center.

In practice:
- The camera sits above the screen. Looking at the interviewer's face (correct
  behavior) means looking slightly down — which moves the iris slightly toward
  the nose and downward, reducing the score.
- The camera-pitch-offset correction (added in v1 fixes) corrects the *pose
  gate* (whether the frame is excluded), but it does not correct the **iris
  position** within the eye socket. Those are two separate things.
- The current code corrects "is the person's head turned?" (yaw/pitch gate)
  but not "where is the iris pointing?" (the actual gaze direction).

**What to do**

The cleanest fix is to compute a **gaze vector** from the iris position relative
to the eye socket center, then project it against the expected camera direction.
MediaPipe provides iris landmarks (468, 473) which, combined with the eye corners,
give an iris-in-socket offset. Converting this to a gaze angle and then
measuring the angle to the camera direction requires:

1. Estimating the camera direction in head-pose coordinates (using the solvePnP
   result you already have).
2. Estimating the iris offset in eye-socket coordinates (you already have this).
3. Measuring the angular distance between them.

This is more math but not more data — all the inputs are already available from
the existing solvePnP solve and the iris landmarks.

A simpler but less principled workaround: add a per-user calibration step
where the user is asked to "look at the camera" for 3 seconds. Record the
average iris offset during this window and use it as the "perfect eye contact"
reference. Any subsequent offset is measured relative to that reference, not
relative to "iris exactly centered in socket." This is essentially extending
the existing calibration to include gaze reference, not just neutral expression.

---

### 1.5  Smile metric: why it still under-reports

**What the metric does**

`raw_smile_score` combines:
- `ratio_score`: `(mouth_width / mouth_height - 2.0) / 3.0` — wide, shallow
  mouth = smile. Ratio of 2 → score 0; ratio of 5 → score 1.
- `elevation_score`: lip corners above lip center, normalized by ICD.

Then the 80th percentile of a 30-frame rolling window feeds into an EMA.

**Problems**

- **Mouth height in the denominator collapses when speaking.** While talking,
  the mouth opens — `mouth_height` grows — which makes the ratio drop toward
  1–2, pulling `ratio_score` to 0. A person smiling while speaking will score
  lower than a person smiling with mouth closed. The metric conflates smiling
  with not-speaking.
- **The elevation signal requires the lip center to be above the corners.** For
  most neutral faces this is very small. People with naturally downturned mouths
  will consistently score low elevation even when smiling.
- **EMA on top of percentile means two smoothing stages.** A genuine 1-second
  smile still has to push through the percentile window and then through the EMA.
  The response is slow.

**What to do**

- Separate "is the person speaking?" from "is the person smiling?" MediaPipe
  provides jaw-open blendshape-equivalent geometry: the distance between the
  upper and lower lip center (landmarks 13 and 14). When this distance exceeds
  a threshold (mouth open), suppress the ratio score and rely only on elevation
  and cheek squint proxies.
- Add cheek squint as a signal: the y-distance between the eye outer corner
  (33/263) and the cheekbone (landmarks 116/345) contracts when genuinely
  smiling (Duchenne smile). This is available in the existing 478-point mesh and
  is more robust to speech than the mouth ratio.
- Reduce the EMA alpha for smile specifically (e.g. α=0.5 instead of 0.3) to
  make it more responsive to short genuine smiles.

---

## Part 2 — Diagnostic Mode

### 2.1  Name

**"Diagnostic Mode"** — preferred over "Developer Mode" or "Advanced Mode"
because it accurately describes the purpose: inspecting the raw signals that
drive the scores, not developing the app or accessing advanced settings. It
signals to users "this is for understanding what the system sees," not "this
is for power users."

The toggle lives in the header, next to the Session Report button. It is
sticky (localStorage) so it persists across page loads.

---

### 2.2  What goes in Diagnostic Mode

Three layers, toggled independently:

#### Layer 1 — Geometric overlays on the video

A `<canvas>` element positioned absolutely over the `<video>` in the video
panel. Semi-transparent, non-interactive. Drawn each frame from coordinate
data the backend already sends (or can be extended to send).

The five axes you specified map to these specific constructs:

| Your term | What it actually is | How to draw it |
|---|---|---|
| Facial midline / Face center axis / Face symmetry axis | Vertical through nose bridge (landmark 168) and nose tip (landmark 1/4), extended to chin (152) | A single vertical line through 3 collinear points |
| Eye line | Horizontal between outer eye corners 33 ↔ 263 | One horizontal line segment |
| Pose midline | Vertical from shoulder midpoint (midpoint of 11 ↔ 12) through hip midpoint (23 ↔ 24) | One vertical line, two body segments |

All three together look like a crosshair centered on the face and a spine line
on the body. They make tilt, lean, and symmetry immediately visible.

Additional overlays worth including in diagnostic mode:
- The 6 PnP reference points (nose, chin, eye corners, mouth corners) as
  colored dots — these are what the solvePnP solve uses, and seeing them
  confirms the pose estimation is tracking correctly.
- The iris landmarks (468, 473) as small circles — shows what the eye contact
  metric is actually measuring.
- A small axes indicator (3-D cube corner) showing estimated yaw/pitch/roll.

**How to get the coordinates to the frontend**

Option A (recommended for now): extend the analysis payload to include the
key landmark coordinates as normalized [0,1] pairs. Only send the ~15 points
needed for overlays — not all 478. The frontend scales them to canvas pixels
using `canvas.width` and `canvas.height`. Bandwidth cost: negligible (15 points
× 2 floats ≈ 120 bytes per frame at 15fps).

Option B: run MediaPipe JS in the browser for overlay only. Higher quality,
no latency, but heavier page load and duplicates detection logic.

Option A is the right call for a diagnostic tool. Option B makes sense only
if you later want real-time overlay at 30fps for a production "coach view."

#### Layer 2 — Raw numeric readouts panel

A collapsible panel (or a side-drawer) showing the internal values that are
normally hidden. Specifically:

```
face_visible:       true / false
pose_visible:       true / false
excluded:           true / false
yaw_deg:            -3.2°
pitch_deg:          +1.1°
roll_deg:           +0.4°
ICD (px):           112
shoulder_width (px): 248
raw_eye_contact:    0.812   ← before EMA
ema_eye_contact:    0.789   ← after EMA (what is displayed)
raw_smile:          0.241   ← before percentile + EMA
smile_percentile:   0.38    ← 80th pct of window
ema_smile:          0.312   ← final value
combined_movement:  0.0021  ← the key number before normalization
combined_head_std:  0.0008
calibrated:         true / false
baseline:           {ec: 0.81, sm: 0.12, ...}
frame_count:        1847
excluded_count:     23
```

This is the tool that lets you debug "why is movement always 100%" — you look
at `combined_movement: 0.0021` and immediately see it is below the `0.003`
floor. Without this panel, you are flying blind.

The backend already computes all of these internally. Exposing them means
adding them to the payload when diagnostic mode is active. The WebSocket
`start` message should carry a `"diagnostic": true` flag, and the backend
includes the extra fields only when that flag is set (to keep normal mode lean).

#### Layer 3 — Overlay toggles

Six checkboxes in the diagnostic panel header:

- [ ] Facial midline
- [ ] Eye line
- [ ] Pose midline
- [ ] PnP reference points
- [ ] Iris landmarks
- [ ] Pose orientation axes

Each controls whether that specific overlay is drawn. All on by default when
diagnostic mode is enabled; each can be turned off individually.

---

### 2.3  Architecture impact

The backend needs two additions:
1. A `diagnostic_mode: bool` field read from the `start` WebSocket message,
   stored on the `InterviewAnalyzer` instance.
2. When `diagnostic_mode=True`, `analyze_frame` appends a `"diagnostic"` dict
   to the payload containing the raw values and the landmark coordinates listed
   above. Normal mode: no `"diagnostic"` key, payload unchanged.

The frontend needs:
1. A `diagnosticMode` boolean in `useInterviewSession` state, passed to the
   WebSocket `start` message.
2. A `<canvas>` overlay component that draws from `analysis.diagnostic.landmarks`
   when present.
3. A `DiagnosticPanel` component showing the raw readouts.
4. A mode toggle button in the header.

---

## Part 3 — Light / Dark Theming

### 3.1  Current situation

Every color in the UI is a hardcoded inline hex value:
- Background: `#111420`, `#181d2e`, `#0d0f1a`
- Borders: `#252b3d`
- Text muted: `#6b7491`
- Text primary: `#e8ecf4`
- Status green: `#22c55e`
- Status amber: `#f59e0b`
- Status red: `#ef4444`
- Accent blue: `#4f8ef7`

These are scattered across `page.tsx`, `MetricsPanel.tsx`, `StatusCards.tsx`,
`FeedbackPanel.tsx`, `ConfidenceRing.tsx`, `SparklineChart.tsx`, and
`SessionReport.tsx`. There is no theme layer. Toggling light/dark means
replacing every hex in every file — which is why it hasn't been done yet.

### 3.2  The right approach: CSS custom properties

The correct fix is not to use Tailwind dark mode classes (the codebase bypasses
Tailwind's utility classes entirely and uses inline `style={{}}`), but to
introduce a **CSS variable token set** in `globals.css` and replace the inline
hex values with `var(--token-name)` references.

**Token set (dark → light)**

| Token | Dark value | Light value |
|---|---|---|
| `--bg-base` | `#0d0f1a` | `#f4f5f9` |
| `--bg-surface` | `#111420` | `#ffffff` |
| `--bg-card` | `#181d2e` | `#f9fafb` |
| `--border` | `#252b3d` | `#e2e6f0` |
| `--text` | `#e8ecf4` | `#111827` |
| `--text-muted` | `#6b7491` | `#6b7280` |
| `--accent` | `#4f8ef7` | `#2563eb` |
| `--green` | `#22c55e` | `#16a34a` |
| `--amber` | `#f59e0b` | `#d97706` |
| `--red` | `#ef4444` | `#dc2626` |
| `--ring-track` | `#1e2438` | `#e5e7eb` |

The dark values are the current hardcoded values — switching to tokens is
zero visual change in dark mode. The light values are the new work.

**Mechanism**

```css
/* globals.css */
:root {
  --bg-base: #0d0f1a;
  /* ... all tokens ... */
}

[data-theme="light"] {
  --bg-base: #f4f5f9;
  /* ... light overrides ... */
}
```

A toggle button in the header sets `document.documentElement.dataset.theme`
to `"light"` or removes the attribute (defaulting to dark). The choice is
persisted in `localStorage` and respected on load. On first visit, respect
`prefers-color-scheme` from the OS.

**Migration path**

The migration is mechanical but affects every component. The right way to do
it is file by file:
1. `globals.css` — add the token definitions.
2. `page.tsx` — replace the header, layout, and status pill colors.
3. `MetricsPanel.tsx` — cards, bars, text.
4. `StatusCards.tsx` — cards, icon boxes, degree colors.
5. `FeedbackPanel.tsx` — tip cards.
6. `ConfidenceRing.tsx` — ring track color.
7. `SparklineChart.tsx` — line and axis colors.
8. `SessionReport.tsx` — modal background and content.

Each file is independent. They can be done one at a time without breaking
anything.

---

## Part 4 — Recommended Order of Attack

This table lists every improvement, which bug category it belongs to,
its effort estimate, and its priority.

| # | What | Category | Effort | Priority |
|---|---|---|---|---|
| 1 | Emit `null` for metrics when `face_visible=False`; frontend shows "—" | Accuracy (§1.1) | Small | **Do first** |
| 2 | Frontend: gate `MetricsPanel` and `ConfidenceRing` on `face_visible` / `pose_visible` | Accuracy (§1.1) | Small | **Do first** |
| 3 | Frontend: respect `calibrating` flag in metric cards | Accuracy (§1.2) | Small | **Do first** |
| 4 | Move movement/stability normalization constants to config; tighten anchors | Accuracy (§1.2) | Small | High |
| 5 | Posture: add lean penalty + raise shoulder visibility threshold | Accuracy (§1.3) | Medium | High |
| 6 | Eye contact: add per-user gaze calibration step | Accuracy (§1.4) | Medium | High |
| 7 | Smile: suppress ratio score when mouth is open; add cheek squint proxy | Accuracy (§1.5) | Medium | Medium |
| 8 | Backend: add `diagnostic_mode` flag; send landmark coords + raw internals | Diagnostic (§2.3) | Medium | Medium |
| 9 | Frontend: canvas overlay for facial/pose axes + iris dots | Diagnostic (§2.2) | Medium | Medium |
| 10 | Frontend: `DiagnosticPanel` raw readouts + per-overlay toggles | Diagnostic (§2.2) | Medium | Medium |
| 11 | CSS token set in `globals.css` + header toggle + localStorage | Theming (§3.2) | Small | Low |
| 12 | Component-by-component token migration (8 files) | Theming (§3.2) | Medium | Low |

Items 1–3 are the ones the user already noticed. They take less than a day
combined and immediately fix the "why is eye contact 66% with no face?" problem.
Items 4–7 make the live numbers trustworthy.
Items 8–10 add the diagnostic visualization layer.
Items 11–12 add theming last, since cosmetics have no impact on usefulness.

---

## Traceability Table

| Issue raised by user | Root cause (this doc) | Fix reference |
|---|---|---|
| Eye contact 66% with no face | Frozen EMA emitted in live payload | §1.1 → Items 1, 2 |
| Confidence always high with no face | Confidence is sum of frozen metrics | §1.1 → Items 1, 2 |
| Movement always 100% | Normalization anchor too lenient | §1.2 → Item 4 |
| Posture always high | Same anchor problem + coarse uprightness test | §1.3 → Item 5 |
| Calibration numbers shown as real | `calibrating` flag ignored in frontend | §1.2 → Item 3 |
| Smile under-reported while speaking | Ratio collapses when mouth opens | §1.5 → Item 7 |
| Overlay axes for midline, eye line, pose | Diagnostic Mode design | §2.2 → Items 8–10 |
| Light / dark mode | Inline hex with no theme layer | §3 → Items 11–12 |

---

*Document status: plan only — no code written. Supersedes relevant sections of*
*ANALYSIS_AND_IMPROVEMENTS.md (v1), which remains as the original diagnostic record.*
