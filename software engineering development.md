# Software Engineering Development — AI Interview Coach

> Implementation record of every software-engineering principle and design pattern
> applied to the Python backend of the AI Interview Coach project.
> Each section names the exact file and the exact code element that demonstrates
> the principle — no hypothetical examples, only production code.

**Test coverage:** 63 tests in `backend/tests/test_patterns.py`, all passing.  
**Scope:** `backend/app/` — Python only.

---

## Table of Contents

1. [Design Patterns](#1-design-patterns)
   - 1.1 Singleton
   - 1.2 Decorator (Factory)
   - 1.3 Template Method
   - 1.4 Factory Method
   - 1.5 Strategy (via Polymorphism)
2. [Object-Oriented Programming](#2-object-oriented-programming)
   - 2.1 Classes, Attributes, Methods
   - 2.2 Inheritance
   - 2.3 Polymorphism
   - 2.4 Abstract Base Class
   - 2.5 Encapsulation
3. [Python-Specific OOP Mechanisms](#3-python-specific-oop-mechanisms)
   - 3.1 Metaclass
   - 3.2 Special / Dunder Methods
   - 3.3 Properties
   - 3.4 Class Methods and Static Methods
   - 3.5 `__init_subclass__`
   - 3.6 Dataclasses and `__slots__`
4. [Functional Patterns](#4-functional-patterns)
   - 4.1 Closures
   - 4.2 Decorator Functions
   - 4.3 Higher-Order Functions
5. [Iteration and Generation](#5-iteration-and-generation)
   - 5.1 Iterator Protocol
   - 5.2 Generator Functions
   - 5.3 Generator Expressions
6. [Function Signatures](#6-function-signatures)
   - 6.1 Positional-Only Parameters
   - 6.2 Keyword-Only Parameters
   - 6.3 Mixed Signatures
7. [Namespaces and Scoping](#7-namespaces-and-scoping)
   - 7.1 Module-Level (Global) Variables
   - 7.2 Instance and Class Attributes
   - 7.3 Local Variables
   - 7.4 Closure Variables (Free Variables)
8. [Context Management](#8-context-management)
9. [Thread Safety](#9-thread-safety)
10. [Type Annotations](#10-type-annotations)
11. [Test Coverage Map](#11-test-coverage-map)

---

## 1. Design Patterns

### 1.1 Singleton

**File:** `backend/app/core/singleton.py`  
**Class:** `SingletonMeta(type)`

The Singleton pattern ensures a class has exactly one instance for the lifetime of the process. This matters for `DatabaseManager`, `SessionService`, and `UserProfileService` — creating multiple instances would open duplicate database connections or lose in-memory session state.

```python
# core/singleton.py
_SINGLETON_LOCK: threading.Lock = threading.Lock()   # module-level global lock

class SingletonMeta(type):
    _instances: dict[type, object] = {}              # class-level registry

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with _SINGLETON_LOCK:                    # acquire lock
                if cls not in cls._instances:        # double-check inside lock
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
```

The double-checked locking pattern avoids the cost of acquiring the lock on every call (the common case) while guaranteeing thread-safety on the first instantiation. The module-level `_SINGLETON_LOCK` is a **global variable** shared across all singleton subclasses.

`SingletonMeta.clear(target)` is a `@classmethod` that removes one or all stored instances — required for test isolation, where each test needs a fresh `DatabaseManager` backed by a temporary file.

**Used by:** `DatabaseManager`, `SessionService`, `UserProfileService`, `Settings`.

---

### 1.2 Decorator (Factory)

**File:** `backend/app/core/decorators.py`

Four decorator factories are implemented. Each is a function that returns a decorator, which itself returns a wrapper — three levels of nesting with `functools.wraps` preserving the original function's metadata.

**`@validate_score(*, lo, hi)`** — clamps float return values:
```python
def validate_score(*, lo: float = 0.0, hi: float = 1.0) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            if result is None:
                return None
            return float(max(lo, min(hi, result)))   # closure: lo, hi captured
        return wrapper
    return decorator
```

Applied to every `score()` method in the metric scorer hierarchy, so no scorer can accidentally emit a value outside [0, 1].

**`@log_call(*, level)`** — structured logging of entry, exit, and elapsed time.  
**`@retry(*, max_attempts, delay, exceptions)`** — retries any function on specified exception types.  
**`@memoize`** — direct-form decorator (no factory); caches results by positional args.

---

### 1.3 Template Method

**File:** `backend/app/services/metric_scorers.py`  
**Class:** `BaseMetricScorer`

The Template Method pattern defines a fixed algorithm skeleton in the base class while letting subclasses fill in one specific step. `update()` is the fixed algorithm; `score()` is the step delegated to subclasses:

```python
class BaseMetricScorer(ABC):
    def update(self, raw: float | None, *, valid: bool = True) -> MetricResult:
        # Fixed algorithm: EMA update → label → MetricResult
        if raw is not None and valid:
            self._ema_state = self._ema_fn(self._ema_state, raw)
        label = self._label_fn(self._ema_state)
        return MetricResult(metric=self.metric_name, raw=raw,
                            smoothed=self._ema_state, label=label, valid=valid)

    @abstractmethod
    def score(self, *args, **kwargs) -> float | None:
        ...   # subclasses fill in this step
```

Every caller uses `scorer.update(scorer.score(...))` — the same two-step call regardless of which metric. The internal smoothing, labeling, and packaging logic never duplicates.

---

### 1.4 Factory Method

**File:** `backend/app/services/metric_scorers.py`  
**Method:** `BaseMetricScorer.from_config(cfg, /)`  
**Function:** `build_scorers(cfg)`

`from_config` is a `@classmethod` named constructor — a Factory Method that creates an instance from a config dict rather than requiring the caller to know the constructor signature:

```python
@classmethod
def from_config(cls, cfg: dict[str, Any], /) -> "BaseMetricScorer":
    thresholds = cfg.get("thresholds", {}).get(cls.metric_name, {})
    return cls(
        alpha=float(cfg.get("ema_alpha", 0.30)),
        good_threshold=float(thresholds.get("good", _DEFAULT_GOOD)),
        okay_threshold=float(thresholds.get("okay", _DEFAULT_OKAY)),
    )
```

`build_scorers(cfg)` uses a list comprehension to call `from_config` on every concrete subclass polymorphically, returning a `{name: scorer}` dict in one line:

```python
def build_scorers(cfg: dict[str, Any]) -> dict[str, BaseMetricScorer]:
    classes = [EyeContactScorer, SmileScorer, PostureScorer,
               HeadStabilityScorer, BodyMovementScorer]
    return {cls.metric_name: cls.from_config(cfg) for cls in classes}
```

---

### 1.5 Strategy (via Polymorphism)

**File:** `backend/app/services/metric_scorers.py`

Each concrete scorer class is a Strategy — an interchangeable algorithm for computing one metric. Callers hold a `BaseMetricScorer` reference and call `score()` without knowing which implementation runs:

```python
scorers: dict[str, BaseMetricScorer] = build_scorers(cfg)
result = scorers["smile"].update(scorers["smile"].score(mouth, squint))
```

Switching from `SmileScorer` to a hypothetical `BlendshapeSmileScorer` requires only changing the `build_scorers` list — no caller changes.

---

## 2. Object-Oriented Programming

### 2.1 Classes, Attributes, Methods

Every service in the backend is a class. The distinction between class attributes and instance attributes is applied consistently and intentionally throughout.

**Class attribute** — shared by all instances, defined at class body level:
```python
# session_service.py
class SessionService(metaclass=SingletonMeta):
    METRICS: tuple[str, ...] = _METRIC_KEYS   # class constant

# metric_scorers.py
class BodyMovementScorer(BaseMetricScorer):
    FLOOR: float = 0.0003   # shared normalization anchor
    CEIL:  float = 0.018
```

**Instance attribute** — owned by each object, set in `__init__`:
```python
# metric_scorers.py  BaseMetricScorer.__init__
self._alpha: float     = alpha
self._ema_state: float = 0.5
self._ema_fn           = make_ema_fn(alpha=alpha)   # closure stored as attribute
self._label_fn         = make_threshold_checker(good=good_threshold, okay=okay_threshold)
```

**Method categories present in the codebase:**
- Instance methods: `update()`, `reset()`, `generate()`, `analyze_frame()`
- Class methods: `from_config()`, `set_anchors()`, `clear()`
- Static methods: `normalize_to_unit_range()`, `_interocular_distance()`, `_shoulder_width()`
- Abstract methods: `score()` in `BaseMetricScorer`
- Properties: `name`, `ema_value`, `pool_sizes`, `active_sessions`, `profile_count`, `text`, `word_count`

---

### 2.2 Inheritance

**File:** `backend/app/services/metric_scorers.py` and `feedback_engine.py`

Two independent inheritance hierarchies exist:

**Metric scorer hierarchy:**
```
BaseMetricScorer (ABC)
├── EyeContactScorer     metric_name = "eye_contact"
├── SmileScorer          metric_name = "smile"     (also overrides reset())
├── PostureScorer        metric_name = "posture"
├── HeadStabilityScorer  metric_name = "head_stability"  (extra attribute: _stability_coeff)
└── BodyMovementScorer   metric_name = "body_movement"   (class attrs FLOOR, CEIL)
```

Every subclass calls `super().__init__(alpha, good_threshold=..., okay_threshold=...)` to delegate common initialization to the parent. `SmileScorer` additionally overrides the EMA seed:

```python
class SmileScorer(BaseMetricScorer):
    def __init__(self, alpha: float = 0.45, *, good_threshold=0.50, okay_threshold=0.20):
        super().__init__(alpha, good_threshold=good_threshold, okay_threshold=okay_threshold)
        self._ema_state = 0.0   # override parent seed (smile starts at 0, not 0.5)
```

**Feedback engine hierarchy:**
```
BaseFeedbackEngine
└── CoachingFeedbackEngine   (overrides generate() with priority ordering)
```

`FeedbackEngine` is a backward-compatible alias for `CoachingFeedbackEngine`.

---

### 2.3 Polymorphism

**File:** `backend/app/services/metric_scorers.py`

Each subclass provides its own implementation of `score()`. The same call site works for all five metrics because the type is `BaseMetricScorer`:

```python
# EyeContactScorer.score — takes iris_offset (positional-only)
def score(self, iris_offset: float, /) -> float:
    return 1.0 - iris_offset

# SmileScorer.score — takes mouth_score + squint_score + squint_weight
def score(self, mouth_score: float, squint_score: float, /, squint_weight: float = 0.30) -> float:
    return (1.0 - squint_weight) * mouth_score + squint_weight * squint_score

# PostureScorer.score — takes tilt + lean + hip penalties
def score(self, tilt_norm: float, lean_penalty: float = 0.0, /, hip_penalty: float = 0.0) -> float:
    return float(np.clip((1.0 - tilt_norm) * (1.0 - lean_penalty) * (1.0 - hip_penalty), 0.0, 1.0))
```

`CoachingFeedbackEngine.generate()` also overrides the parent method — it calls `super().generate()` to get the base result structure, then re-orders recommendations by `_PRIORITY`:

```python
class CoachingFeedbackEngine(BaseFeedbackEngine):
    def generate(self, *, eye_contact, smile, ...) -> dict[str, Any]:
        self._generate_count += 1
        result = super().generate(...)        # delegate to parent
        # re-order recommendations by _PRIORITY
        ordered = [...]
        result["recommendations"] = ordered
        return result
```

---

### 2.4 Abstract Base Class

**File:** `backend/app/services/metric_scorers.py`

`BaseMetricScorer` inherits from `ABC` and declares `score()` as `@abstractmethod`. Python's ABC machinery raises `TypeError` at instantiation time if `score()` is not overridden:

```python
from abc import ABC, abstractmethod

class BaseMetricScorer(ABC):
    @abstractmethod
    def score(self, *args, **kwargs) -> float | None:
        """Must be overridden by each concrete metric class."""
```

**Test proof:**
```python
def test_cannot_instantiate_base():
    with pytest.raises(TypeError):
        BaseMetricScorer()   # TypeError: Can't instantiate abstract class
```

---

### 2.5 Encapsulation

Private state is signaled by the single-underscore convention throughout:

- `self._ema_state` — internal EMA value, not part of the public interface
- `self._label_fn` — closure stored as an attribute, implementation detail
- `self._frame_buffers` — in-memory session buffer in `SessionService`
- `self._last_idx` — anti-repeat state in `FeedbackEngine`
- `self._tokens` — internal token list in `SentenceAssembler`

Public access is provided only through `@property` (read-only) or explicit methods, never direct attribute assignment from outside the class.

---

## 3. Python-Specific OOP Mechanisms

### 3.1 Metaclass

**File:** `backend/app/core/singleton.py`

A metaclass is a class whose instances are classes. `SingletonMeta` inherits from `type` and overrides `__call__` — the method that runs when a class is called to create an instance:

```python
class SingletonMeta(type):
    _instances: dict[type, object] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with _SINGLETON_LOCK:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
```

Any class that sets `metaclass=SingletonMeta` automatically gets singleton behavior without inheriting from a base class. This keeps the class hierarchy clean — `SessionService` can be a singleton without any coupling to `DatabaseManager` or `UserProfileService`.

---

### 3.2 Special / Dunder Methods

Dunder methods are implemented across all major classes so they behave as natural Python objects — printable, measurable, iterable.

| Class | Dunder | Behavior |
|---|---|---|
| `SingletonMeta` | `__repr__` | Shows class name and instantiation state |
| `BaseMetricScorer` | `__repr__`, `__str__` | Shows metric name, α, EMA value |
| `MetricResult` | `__repr__` | Shows all fields in one line |
| `FrameWindowIterator` | `__iter__`, `__next__`, `__len__`, `__repr__` | Full iterator protocol |
| `SentenceTokenIterator` | `__iter__`, `__next__`, `__len__`, `__getitem__`, `__repr__` | Full sequence-like protocol |
| `SentenceAssembler` | `__iter__`, `__len__`, `__contains__`, `__repr__`, `__str__` | Iterable, measurable, membership test |
| `SessionService` | `__repr__`, `__str__`, `__len__` | Reports buffered session count |
| `UserProfileService` | `__repr__`, `__str__`, `__len__` | Reports stored profile count |
| `BaseFeedbackEngine` | `__repr__`, `__str__`, `__len__` | Reports message pool size |
| `CoachingFeedbackEngine` | `__repr__` | Includes call count |
| `FrameWindow` | `__repr__` | Shows start, count, mean confidence |
| `UserProfileData` | `__repr__` | Shows user_id, session count, offset |
| `SessionMetrics` | `__repr__` | Shows metric, mean, min, max |

**Example — `SentenceAssembler.__contains__`:**
```python
sa = SentenceAssembler()
sa.add_sign("Python")
assert "Python" in sa      # uses __contains__
```

**Example — `SessionService.__len__`:**
```python
service = SessionService()
service.start_session("sid-1")
assert len(service) == 1   # uses __len__ → active_sessions property
```

---

### 3.3 Properties

`@property` is used to expose computed state as an attribute without exposing mutable internals.

```python
# metric_scorers.py — BaseMetricScorer
@property
def ema_value(self) -> float:
    return self._ema_state       # read-only; _ema_state is private

@property
def name(self) -> str:
    return self.metric_name

# session_service.py
@property
def active_sessions(self) -> int:
    return len(self._frame_buffers)

# sentence_assembler.py
@property
def text(self) -> str:
    return self.separator.join(self._tokens)

@property
def word_count(self) -> int:
    return len(self._tokens)

# feedback_engine.py — CoachingFeedbackEngine
@property
def generate_count(self) -> int:
    return self._generate_count

# feedback_engine.py — BaseFeedbackEngine
@property
def pool_sizes(self) -> dict[str, int]:
    return {key: sum(len(msgs) for msgs in pool.values())
            for key, pool in _POOLS.items()}
```

---

### 3.4 Class Methods and Static Methods

**`@classmethod`** — receives the class as first argument, used for named constructors and class-state mutation:

```python
# metric_scorers.py — named constructor (Factory Method)
@classmethod
def from_config(cls, cfg: dict[str, Any], /) -> "BaseMetricScorer":
    ...

# metric_scorers.py — mutates class-level anchors
@classmethod
def set_anchors(cls, *, floor: float, ceil: float) -> None:
    cls.FLOOR = floor
    cls.CEIL  = ceil

# singleton.py — removes stored instance(s)
@classmethod
def clear(mcs, target: type | None = None) -> None:
    ...
```

**`@staticmethod`** — no implicit first argument, used for pure utility functions with logical affinity to the class:

```python
# metric_scorers.py — clamps to [lo, hi]
@staticmethod
def normalize_to_unit_range(value: float, /, lo: float = 0.0, hi: float = 1.0) -> float:
    ...

# interview_analyzer.py — computes interocular distance
@staticmethod
def _interocular_distance(lm: np.ndarray) -> float:
    return float(np.linalg.norm(lm[33] - lm[263])) + 1e-6
```

---

### 3.5 `__init_subclass__`

**File:** `backend/app/services/feedback_engine.py`

`__init_subclass__` is called automatically by Python when any subclass of `BaseFeedbackEngine` is defined. This is used to maintain a registry of all concrete feedback engines without any registration boilerplate in the subclasses:

```python
class BaseFeedbackEngine:
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not hasattr(BaseFeedbackEngine, "_subclasses"):
            BaseFeedbackEngine._subclasses: list[str] = []
        BaseFeedbackEngine._subclasses.append(cls.__name__)
```

After defining `CoachingFeedbackEngine`, `BaseFeedbackEngine._subclasses` contains `["CoachingFeedbackEngine"]` — automatically, with no explicit registration call.

---

### 3.6 Dataclasses and `__slots__`

**Files:** `core/iterators.py`, `services/metric_scorers.py`, `services/session_service.py`, `services/user_profile_service.py`

Dataclasses reduce boilerplate for data-holding classes. `__slots__` is added on hot-path classes to eliminate the per-instance `__dict__`, reducing memory usage and slightly improving attribute access speed.

```python
@dataclass(slots=True)
class MetricResult:
    metric:   str
    raw:      float | None
    smoothed: float
    label:    str
    valid:    bool
    # __repr__, __eq__ auto-generated; __slots__ avoids __dict__

@dataclass(slots=True)
class FrameWindow:
    frames:    list[dict[str, Any]]
    start_idx: int
    mean:      float = field(init=False)   # computed, not passed to __init__

    def __post_init__(self) -> None:
        confs = [f.get("confidence", 0.0) for f in self.frames]
        self.mean = sum(confs) / len(confs) if confs else 0.0
```

`__post_init__` is called after the dataclass-generated `__init__`, allowing derived fields (`mean`) to be computed from constructor arguments without overriding `__init__`.

---
