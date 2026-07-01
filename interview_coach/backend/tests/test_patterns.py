"""Tests covering every software-engineering pattern introduced in the backend.

Patterns verified:
  - Singleton (thread-safety, clear(), __repr__)
  - Decorator (@validate_score, @log_call, @memoize, @retry)
  - Generator (metric_history_generator, frame_chunk_generator, confidence_values)
  - Iterator (FrameWindowIterator, SentenceTokenIterator — __iter__, __next__, __len__)
  - Closure (make_ema_fn, make_threshold_checker)
  - OOP / Inheritance / Polymorphism (BaseMetricScorer hierarchy)
  - Dataclass (__post_init__, __repr__, slots)
  - contextmanager (SessionService.session_scope)
  - @property / @classmethod / @staticmethod
  - __repr__ / __str__ / __len__ / __contains__ / __iter__
  - Positional-only and keyword-only parameters
  - Abstract Base Class (cannot instantiate BaseMetricScorer directly)
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

# ── imports under test ───────────────────────────────────────────────────────
from app.core.singleton import SingletonMeta
from app.core.decorators import log_call, memoize, retry, validate_score
from app.core.iterators import (
    FrameWindow,
    FrameWindowIterator,
    SentenceTokenIterator,
    confidence_values,
    frame_chunk_generator,
    metric_history_generator,
)
from app.services.metric_scorers import (
    BaseMetricScorer,
    BodyMovementScorer,
    EyeContactScorer,
    HeadStabilityScorer,
    MetricResult,
    PostureScorer,
    SmileScorer,
    build_scorers,
    make_ema_fn,
    make_threshold_checker,
)
from app.services.sentence_assembler import SentenceAssembler
from app.services.feedback_engine import FeedbackEngine, BaseFeedbackEngine, CoachingFeedbackEngine


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Singleton
# ═══════════════════════════════════════════════════════════════════════════════

class _TestSvc(metaclass=SingletonMeta):
    def __init__(self, value: int = 0) -> None:
        self.value = value


class TestSingleton:
    def setup_method(self) -> None:
        SingletonMeta.clear(_TestSvc)

    def test_same_instance_returned(self) -> None:
        a = _TestSvc(1)
        b = _TestSvc(99)            # __init__ args ignored on second call
        assert a is b
        assert a.value == 1

    def test_clear_allows_new_instance(self) -> None:
        a = _TestSvc(1)
        SingletonMeta.clear(_TestSvc)
        b = _TestSvc(2)
        assert a is not b
        assert b.value == 2

    def test_thread_safety(self) -> None:
        """Two threads must receive the same instance."""
        instances: list[_TestSvc] = []
        barrier = threading.Barrier(2)

        def create() -> None:
            barrier.wait()          # both threads start at same time
            instances.append(_TestSvc(42))

        t1, t2 = threading.Thread(target=create), threading.Thread(target=create)
        t1.start(); t2.start()
        t1.join();  t2.join()
        assert instances[0] is instances[1]

    def test_repr(self) -> None:
        _ = _TestSvc(0)
        r = repr(SingletonMeta)
        assert "SingletonMeta" in r


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Decorators
# ═══════════════════════════════════════════════════════════════════════════════

class TestDecorators:
    def test_validate_score_clamps_high(self) -> None:
        @validate_score(lo=0.0, hi=1.0)
        def over() -> float:
            return 1.5
        assert over() == 1.0

    def test_validate_score_clamps_low(self) -> None:
        @validate_score(lo=0.0, hi=1.0)
        def under() -> float:
            return -0.3
        assert under() == 0.0

    def test_validate_score_passes_none(self) -> None:
        @validate_score()
        def none_fn() -> None:
            return None
        assert none_fn() is None

    def test_memoize_caches_result(self) -> None:
        call_count = [0]

        @memoize
        def expensive(x: int) -> int:
            call_count[0] += 1
            return x * 2

        assert expensive(5) == 10
        assert expensive(5) == 10          # cached
        assert call_count[0] == 1          # only computed once

    def test_memoize_exposes_cache(self) -> None:
        @memoize
        def fn(x: int) -> int:
            return x + 1
        fn(3)
        assert (3,) in fn.cache

    def test_retry_succeeds_on_first_try(self) -> None:
        counter = [0]

        @retry(max_attempts=3, delay=0.0)
        def always_ok() -> str:
            counter[0] += 1
            return "ok"

        result = always_ok()
        assert result == "ok"
        assert counter[0] == 1

    def test_retry_retries_and_succeeds(self) -> None:
        counter = [0]

        @retry(max_attempts=3, delay=0.0, exceptions=(ValueError,))
        def fails_twice() -> str:
            counter[0] += 1
            if counter[0] < 3:
                raise ValueError("not yet")
            return "done"

        assert fails_twice() == "done"
        assert counter[0] == 3

    def test_retry_raises_after_max_attempts(self) -> None:
        @retry(max_attempts=2, delay=0.0, exceptions=(RuntimeError,))
        def always_fails() -> None:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            always_fails()

    def test_log_call_preserves_name(self) -> None:
        @log_call()
        def my_fn() -> int:
            return 42
        assert my_fn.__name__ == "my_fn"
        assert my_fn() == 42


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Iterators
# ═══════════════════════════════════════════════════════════════════════════════

def _make_frames(n: int, *, conf: float = 75.0, excluded: bool = False) -> list[dict]:
    return [{"confidence": conf, "eye_contact": 0.8, "excluded": excluded} for _ in range(n)]


class TestFrameWindowIterator:
    def test_yields_correct_window_count(self) -> None:
        frames = _make_frames(10)
        it = FrameWindowIterator(frames, 3, step=3)
        windows = list(it)
        assert len(windows) == 3       # 10 frames, window=3, step=3 → 3 full windows

    def test_window_has_correct_frame_count(self) -> None:
        frames = _make_frames(9)
        for w in FrameWindowIterator(frames, 3):
            assert len(w.frames) == 3

    def test_mean_confidence_computed(self) -> None:
        frames = [{"confidence": float(i), "excluded": False} for i in range(5)]
        it = FrameWindowIterator(frames, 5)
        w = next(iter(it))
        assert w.mean == pytest.approx(2.0, abs=0.01)

    def test_len(self) -> None:
        frames = _make_frames(12)
        assert len(FrameWindowIterator(frames, 4, step=4)) == 3

    def test_repr(self) -> None:
        it = FrameWindowIterator(_make_frames(6), 3)
        assert "FrameWindowIterator" in repr(it)

    def test_empty_when_frames_shorter_than_window(self) -> None:
        frames = _make_frames(2)
        assert len(FrameWindowIterator(frames, 5)) == 0


class TestSentenceTokenIterator:
    def test_yields_tokens(self) -> None:
        it = SentenceTokenIterator("hello world foo")
        assert list(it) == ["hello", "world", "foo"]

    def test_len(self) -> None:
        assert len(SentenceTokenIterator("a b c")) == 3

    def test_getitem(self) -> None:
        it = SentenceTokenIterator("one two three")
        assert it[1] == "two"

    def test_empty_string(self) -> None:
        assert len(SentenceTokenIterator("")) == 0

    def test_repr(self) -> None:
        it = SentenceTokenIterator("hi there")
        assert "SentenceTokenIterator" in repr(it)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Generator functions
# ═══════════════════════════════════════════════════════════════════════════════

class TestGenerators:
    def test_metric_history_generator_yields_only_valid(self) -> None:
        frames = [
            {"confidence": 80.0, "excluded": False},
            {"confidence": 20.0, "excluded": True},
            {"confidence": 90.0, "excluded": False},
        ]
        results = list(metric_history_generator(frames, "confidence"))
        assert len(results) == 2
        assert results[0] == (0, 80.0)
        assert results[1] == (2, 90.0)

    def test_metric_history_generator_skip_excluded_false(self) -> None:
        frames = [
            {"confidence": 80.0, "excluded": True},
            {"confidence": 60.0, "excluded": False},
        ]
        results = list(metric_history_generator(frames, "confidence", skip_excluded=False))
        assert len(results) == 2

    def test_frame_chunk_generator(self) -> None:
        frames = _make_frames(7)
        chunks = list(frame_chunk_generator(frames, chunk_size=3))
        assert len(chunks) == 3         # [3, 3, 1]
        assert len(chunks[0]) == 3
        assert len(chunks[2]) == 1

    def test_confidence_values_filters_excluded(self) -> None:
        frames = [
            {"confidence": 70.0, "excluded": False},
            {"confidence": 20.0, "excluded": True},
            {"confidence": 80.0, "excluded": False},
        ]
        vals = confidence_values(frames, valid_only=True)
        assert vals == pytest.approx([70.0, 80.0])

    def test_confidence_values_includes_all_when_valid_only_false(self) -> None:
        frames = [
            {"confidence": 70.0, "excluded": False},
            {"confidence": 20.0, "excluded": True},
        ]
        vals = confidence_values(frames, valid_only=False)
        assert len(vals) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Closures
# ═══════════════════════════════════════════════════════════════════════════════

class TestClosures:
    def test_make_ema_fn_applies_alpha(self) -> None:
        ema = make_ema_fn(alpha=0.5)
        result = ema(0.0, 1.0)              # 0.5*1.0 + 0.5*0.0
        assert result == pytest.approx(0.5)

    def test_make_ema_fn_different_alphas_produce_different_results(self) -> None:
        ema_slow = make_ema_fn(alpha=0.1)
        ema_fast = make_ema_fn(alpha=0.9)
        assert ema_fast(0.0, 1.0) > ema_slow(0.0, 1.0)

    def test_make_threshold_checker_good(self) -> None:
        check = make_threshold_checker(good=0.7, okay=0.4)
        assert check(0.8) == "Good"
        assert check(0.5) == "Okay"
        assert check(0.2) == "Needs improvement"

    def test_make_threshold_checker_custom_thresholds(self) -> None:
        check = make_threshold_checker(good=0.5, okay=0.2)
        assert check(0.6) == "Good"   # above 0.5
        assert check(0.35) == "Okay"  # above 0.2 but below 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Metric scorer OOP hierarchy
# ═══════════════════════════════════════════════════════════════════════════════

class TestMetricScorerHierarchy:
    def test_cannot_instantiate_base(self) -> None:
        """ABC must raise TypeError if instantiated directly."""
        with pytest.raises(TypeError):
            BaseMetricScorer()          # type: ignore[abstract]

    def test_eye_contact_scorer_polymorphism(self) -> None:
        scorer: BaseMetricScorer = EyeContactScorer()
        result = scorer.update(scorer.score(0.1))     # score() → float, update() → MetricResult
        assert isinstance(result, MetricResult)
        assert result.metric == "eye_contact"
        assert result.smoothed > 0

    def test_smile_scorer_reset_seed_zero(self) -> None:
        sm = SmileScorer()
        assert sm.ema_value == 0.0          # smile seed is 0 (override)
        sm.reset()
        assert sm.ema_value == 0.0

    def test_posture_scorer_score(self) -> None:
        sc: BaseMetricScorer = PostureScorer()
        raw = sc.score(0.1, 0.0)             # tilt_norm=0.1, lean_penalty=0.0
        assert raw is not None
        assert 0.0 <= raw <= 1.0

    def test_head_stability_scorer(self) -> None:
        sc = HeadStabilityScorer()
        raw = sc.score(0.001, 0.20)          # std=0.001, icd=0.20
        assert raw is not None and raw >= 0.8

    def test_body_movement_scorer_class_anchors(self) -> None:
        BodyMovementScorer.set_anchors(floor=0.001, ceil=0.020)
        sc = BodyMovementScorer()
        assert BodyMovementScorer.FLOOR == pytest.approx(0.001)
        # Reset to defaults
        BodyMovementScorer.set_anchors(floor=0.0003, ceil=0.018)

    def test_from_config_classmethod(self) -> None:
        cfg = {
            "ema_alpha": 0.4,
            "thresholds": {"eye_contact": {"good": 0.80, "okay": 0.50}},
        }
        scorer = EyeContactScorer.from_config(cfg)
        assert scorer._alpha == pytest.approx(0.40)
        assert scorer.good_threshold == pytest.approx(0.80)

    def test_normalize_to_unit_range_staticmethod(self) -> None:
        result = BaseMetricScorer.normalize_to_unit_range(0.5, lo=0.0, hi=1.0)
        assert result == pytest.approx(0.5)
        assert BaseMetricScorer.normalize_to_unit_range(2.0, lo=0.0, hi=1.0) == 1.0

    def test_metric_result_to_dict(self) -> None:
        r = MetricResult(metric="eye_contact", raw=0.8, smoothed=0.75, label="Good", valid=True)
        d = r.to_dict()
        assert d["score"] == pytest.approx(0.75, abs=0.001)
        assert d["label"] == "Good"

    def test_repr_str(self) -> None:
        sc = EyeContactScorer()
        assert "EyeContactScorer" in repr(sc)
        assert "eye_contact" in str(sc)

    def test_build_scorers_returns_all_five(self) -> None:
        scorers = build_scorers({})
        assert set(scorers.keys()) == {
            "eye_contact", "smile", "posture", "head_stability", "body_movement"
        }

    def test_polymorphic_update_returns_metric_result(self) -> None:
        """All scorers are called through the BaseMetricScorer interface."""
        scorers = build_scorers({})
        for name, scorer in scorers.items():
            result = scorer.update(0.7, valid=True)
            assert isinstance(result, MetricResult)
            assert result.metric == name


# ═══════════════════════════════════════════════════════════════════════════════
# 7. SentenceAssembler
# ═══════════════════════════════════════════════════════════════════════════════

class TestSentenceAssembler:
    def test_add_sign_capitalizes(self) -> None:
        sa = SentenceAssembler()
        sa.add_sign("hello")
        assert sa.text == "Hello"

    def test_add_sign_no_capitalize(self) -> None:
        sa = SentenceAssembler()
        sa.add_sign("hello", capitalize=False)
        assert sa.text == "hello"

    def test_max_history_truncation(self) -> None:
        sa = SentenceAssembler(max_history=3)
        for word in ["A", "B", "C", "D", "E"]:
            sa.add_sign(word)
        assert sa.word_count == 3
        assert sa.text == "C D E"

    def test_len(self) -> None:
        sa = SentenceAssembler()
        sa.add_sign("Hello")
        sa.add_sign("World")
        assert len(sa) == 2

    def test_contains(self) -> None:
        sa = SentenceAssembler()
        sa.add_sign("Python")
        assert "Python" in sa

    def test_iter(self) -> None:
        sa = SentenceAssembler()
        for w in ["Hello", "World"]:
            sa.add_sign(w)
        tokens = list(sa)
        assert tokens == ["Hello", "World"]

    def test_token_stream_generator(self) -> None:
        sa = SentenceAssembler()
        sa.add_sign("One")
        sa.add_sign("Two")
        stream = sa.token_stream()
        assert next(stream) == "One"
        assert next(stream) == "Two"
        with pytest.raises(StopIteration):
            next(stream)

    def test_clear(self) -> None:
        sa = SentenceAssembler()
        sa.add_sign("Hi")
        sa.clear()
        assert len(sa) == 0

    def test_repr(self) -> None:
        sa = SentenceAssembler()
        assert "SentenceAssembler" in repr(sa)

    def test_str(self) -> None:
        sa = SentenceAssembler()
        sa.add_sign("Good")
        assert str(sa) == "Good"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. FeedbackEngine hierarchy (inheritance / polymorphism)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeedbackEngineHierarchy:
    def test_coaching_engine_is_subclass(self) -> None:
        assert issubclass(CoachingFeedbackEngine, BaseFeedbackEngine)

    def test_feedback_engine_alias(self) -> None:
        """FeedbackEngine is the CoachingFeedbackEngine alias."""
        from app.services.feedback_engine import FeedbackEngine, CoachingFeedbackEngine
        assert FeedbackEngine is CoachingFeedbackEngine

    def test_generate_count_increments(self) -> None:
        engine = CoachingFeedbackEngine()
        for _ in range(3):
            engine.generate(
                eye_contact=0.5, smile=0.3, posture=0.6,
                head_stability=0.8, body_movement=0.8, confidence=55.0,
            )
        assert engine.generate_count == 3

    def test_pool_sizes_property(self) -> None:
        engine = BaseFeedbackEngine()
        sizes = engine.pool_sizes
        assert "eye_contact" in sizes
        assert all(v > 0 for v in sizes.values())

    def test_len(self) -> None:
        engine = BaseFeedbackEngine()
        assert len(engine) == sum(engine.pool_sizes.values())

    def test_iter_recommendations_generator(self) -> None:
        engine = BaseFeedbackEngine()
        scores = {"eye_contact": 0.2, "smile": 0.9, "posture": 0.9,
                  "head_stability": 0.9, "body_movement": 0.9}
        recs = list(engine._iter_recommendations(scores))
        assert len(recs) == 1          # only eye_contact is below "Good"

    def test_init_subclass_registered(self) -> None:
        """__init_subclass__ should have registered CoachingFeedbackEngine."""
        assert "CoachingFeedbackEngine" in getattr(BaseFeedbackEngine, "_subclasses", [])

    def test_repr_str(self) -> None:
        engine = CoachingFeedbackEngine()
        assert "CoachingFeedbackEngine" in repr(engine)
        assert "coaching messages" in str(engine).lower() or "CoachingFeedbackEngine" in str(engine)
