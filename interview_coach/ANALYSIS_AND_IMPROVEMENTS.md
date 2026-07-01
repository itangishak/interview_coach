# AI Interview Coach — System Analysis & Improvement Ideas

> Expert review of why the interview coaching results feel "static / generic / coded"
> and why the behavioural metrics (smile is just one of them) are unreliable.
> Scope: `backend/app/services/interview_analyzer.py`, `feedback_engine.py`,
> the `/ws/interview` pipeline, and `frontend/hooks/useInterviewSession.ts`.

This is **not** a smile detector. Per the README, the app analyzes **five behaviours** and
produces an overall confidence score:

| Metric | Weight | Function |
|---|---|---|
| Eye contact | 0.30 | `iris_eye_contact_score` |
| Smile | 0.15 | `raw_smile_score` |
| Posture | 0.20 | `posture_score` |
| Head stability | 0.20 | `head_stability_from_positions` |
| Body movement | 0.15 | `body_movement_from_buffers` |
| **Confidence** | — | `_compute_confidence` (weighted sum → 0–100) |

The smile complaint is real, but it's a **symptom of a system-wide design pattern**. The
same handful of flaws degrade every metric. Fixing them fixes the whole coach.

---

## The uncomfortable truth: it *is* coded/static

Despite the name "AI Interview Coach" and the `checkpoints/`, `transformer.py`, `mlp.py`
directories (those belong to the **sign-language** path — `mock_recognizer`, `/ws/sign`),
the interview analyzer contains **zero machine learning**. It is:

- **Hand-tuned geometric heuristics** with magic constants scattered across every metric —
  `0.015`, `2.0`, `3.0` (smile); `0.35` (eye); `5.0` (posture); `0.008 / 0.035`
  (head stability); `0.003 / 0.022` (body movement).
- A **fixed linear weighted sum** for "confidence" (`_compute_confidence`, line 274), with
  weights frozen in a JSON file.
- **Five canned feedback strings** (`feedback_engine.py:40-49`) — the same sentences every
  time, which is exactly why it reads as "generic."

So "it feels coded" isn't a perception problem. It literally is a rule engine wearing an
AI label. Everything below flows from that.

---

## Five system-wide flaws (they hit every metric, not just smile)

### Flaw A — Nothing is normalized to face/body scale, so results track distance, not behaviour
MediaPipe landmarks are normalized to the frame `[0,1]`, **not** to the person. Every
absolute threshold therefore silently encodes "how close you sit to the webcam":

- **Smile**: `elevation / 0.015` (`interview_analyzer.py:145`). Lean back → mouth shrinks in
  frame units → even a huge grin scores ~0. Lean in → trivial movement saturates. **This is
  the main reason your smile is sometimes missed** — it's detecting distance, not a smile.
- **Head stability**: `std` thresholds `0.008 / 0.035` (line 161) are frame-relative, so the
  same head sway scores differently depending on framing.
- **Body movement**: same story with `0.003 / 0.022` (line 187).
- **Posture**: `shoulder_diff * 5.0` (line 202) isn't divided by shoulder width, so distance
  changes the score.

**Fix pattern:** divide every distance by a stable per-person reference — interocular
distance (eye corners 33↔263) for the face, shoulder width for the body. Then thresholds
mean the same thing at any distance.

### Flaw B — 2D geometry ignores head pose, so turning your head breaks the metrics
Everything is computed in flat 2D and the z-coordinate MediaPipe provides is discarded.
- **Smile**: a slight head turn foreshortens `mouth_width` → smile collapses while grinning.
- **Eye contact**: head yaw shifts the iris within the socket → reads as "not centred" even
  when you're looking straight at the camera.
- **Eye contact, additionally**: the webcam sits *above* the screen, so genuine eye contact
  with the on-screen interviewer is geometrically "off-centre." The metric can penalize the
  exact behaviour it's meant to reward.

**Fix pattern:** estimate head pose (yaw/pitch/roll) from the landmarks (or the face
transformation matrix) and compensate, or work in a pose-normalized coordinate frame.

### Flaw C — The 30-frame *mean* erases the events you care about
`_smooth` returns `np.mean(buffer)` over ~2 seconds (`interview_analyzer.py:149-153`). A mean
is a brick-wall low-pass filter:
- A one-second smile averaged against surrounding neutral frames never clears the `0.5`
  "Good" threshold → **smiles look like they "don't register."**
- Eye contact and stability feel **sluggish and static** — the numbers barely move because
  they're dragged toward the window average.

**Fix pattern:** use an exponential moving average (α≈0.3) so recent frames dominate; add
hysteresis on the status labels to stop flicker; and for event-like signals (smile) report
the **peak/percentile over the window**, not the mean — coaching cares about "did you smile,"
not the average lip position.

### Flaw D — Missing face/pose data is faked into plausible numbers ("hiding" isn't handled)
When detection fails, the code fabricates neutral-to-good defaults instead of admitting it
can't see you:
- `raw_smile_score(None)` and `iris_eye_contact_score(None)` → `0.0`.
- `posture_score(None)` → **`0.5`** (line 199), and returns `0.5` again when shoulder
  visibility is low (line 199).
- `head_stability_from_positions` → **`1.0`** when it has < 2 points (line 157); worse, the
  nose buffer only appends when a face is found, so during occlusion it keeps scoring against
  **stale** positions and stays high.
- `body_movement_from_buffers` → **`1.0`** with no data (line 172).

Net effect: **cover your face and the confidence score stays plausible** instead of dropping
or flagging "not visible." That fabricated resilience is a big part of why the output feels
dishonest/coded — and it's exactly the "I hide myself and it doesn't react" behaviour.

**Fix pattern:** gate on `face_detected` / `pose_detected`. When absent, freeze the score,
exclude the frame from session aggregates, and surface an explicit "Face not visible — centre
yourself in frame" state.

### Flaw E — No learning and no personalization anywhere
- **No per-user baseline.** Everyone's neutral face/posture differs; absolute thresholds
  can't fit an individual. There's no calibration step.
- **Confidence is a frozen linear formula.** Because head-stability and body-movement default
  high, the weighted sum sits in a narrow band regardless of behaviour → feels static.
- **Feedback is five fixed strings.** No variation, no context → "generic."

---

## The ideas — what to actually do

From highest-leverage to nice-to-have. These lift **all** metrics, not just smile.

### Idea 1 — Move to MediaPipe Tasks `FaceLandmarker` + **blendshapes** (biggest single win)
The code uses the **legacy** `mp.solutions.face_mesh` solution. The modern **MediaPipe Tasks
`FaceLandmarker`** can emit `output_face_blendshapes=True`: **52 calibrated coefficients
(0–1) trained by Google** — `mouthSmileLeft/Right`, `cheekSquintLeft/Right` (Duchenne / genuine
vs polite smile), `eyeBlinkLeft/Right`, `browInnerUp`, `jawOpen`, and gaze-relevant eye
shapes. These are already normalized for face size, distance, and largely head pose, so they
dissolve Flaws A and B for the facial metrics at once. Smile becomes
`(mouthSmileLeft + mouthSmileRight)/2`; you also gain brow/eye signals for richer coaching.

### Idea 2 — Normalize every remaining metric by a per-person reference
For anything you keep as geometry: divide facial distances by interocular distance and body
distances by shoulder width; measure lifts/offsets relative to a reference line, not raw
frame units. Delete the frame-relative magic constants. (Fixes Flaw A everywhere.)

### Idea 3 — Compensate for head pose (Flaw B)
Estimate yaw/pitch/roll from landmarks (or the face transformation matrix) and correct eye
contact / smile geometry. For eye contact specifically, account for the camera-above-screen
offset so looking at the interviewer isn't penalized.

### Idea 4 — Calibrate a per-user neutral baseline (Flaw E)
Spend the first ~2 seconds recording resting face/posture, then score deviations from the
user's own neutral rather than a universal constant. Turns "arbitrary" into "personal."

### Idea 5 — Fix the temporal filter (Flaw C)
Replace `np.mean` with an EMA; add hysteresis to status labels; report peak/percentile for
event-like signals (smile). Metrics become responsive and stop feeling static.

### Idea 6 — Gate honestly on detection (Flaw D)
Stop fabricating `0.5` / `1.0` defaults. When the face/pose is missing, freeze the score,
exclude the frame from aggregates, and tell the user they're not visible.

### Idea 7 — Make it actually learn (kills "static/generic" for good — Flaw E)
- **Expression / behaviour model:** feed the 478 landmarks (or the 52 blendshapes + pose)
  into a small learned classifier, or use an FER CNN (FER2013 / AffectNet). Metrics become
  learned probabilities, not formulas.
- **Confidence model:** replace the linear weighted sum with a small learned model
  (logistic regression / gradient-boosted trees / shallow MLP) trained on a few labeled
  sessions — the `transformer.py` / `mlp.py` scaffolding already exists to host it.
- **Feedback text:** route the metric summary through an **LLM (Claude)** for varied,
  contextual, personalized coaching ("Your eye contact was strong until the technical
  questions, and your smile faded there — try…"). Cheapest change that most kills the
  "generic" feeling.

### Idea 8 — Cheap robustness wins
Raise MediaPipe detection/tracking robustness for poor lighting; send frames at higher JPEG
quality than `0.7` (`useInterviewSession.ts:124`) — compression artifacts around lips and
eyes degrade fine landmark accuracy.

---

## If you only do three things

1. **Switch to MediaPipe Tasks `FaceLandmarker` + blendshapes** → fixes smile *and* eye/brow
   metrics at the source (Ideas 1–3).
2. **EMA + hysteresis + honest detection gating** → makes the whole coach feel alive and
   trustworthy instead of static/fake (Ideas 5, 6).
3. **LLM-generated feedback + a learned confidence model** → removes the "coded/generic"
   character entirely (Idea 7).
