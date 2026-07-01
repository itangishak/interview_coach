"""Assemble recognized signs into a sentence.

Demonstrates:
  - OOP: class, instance attributes, methods
  - Generator (token_stream)
  - Iterator (SentenceTokenIterator via token_stream)
  - @property (text, word_count)
  - Positional-only parameter (add_sign label /)
  - Keyword-only parameters (capitalize, separator)
  - __repr__, __str__, __len__, __iter__, __contains__
  - Global module constant (_DEFAULT_MAX_HISTORY)
"""
from __future__ import annotations

from typing import Generator, Iterator

from app.core.iterators import SentenceTokenIterator

# ── Module-level (global namespace) constant ─────────────────────────────────
_DEFAULT_MAX_HISTORY: int = 20


class SentenceAssembler:
    """Assembles a sequence of sign labels into a spoken sentence.

    Demonstrates:
      - Instance attributes: _tokens, max_history, separator
      - @property: text, word_count
      - Generator method: token_stream
      - __iter__ (delegates to SentenceTokenIterator — iterator pattern)
      - __len__, __contains__, __repr__, __str__
      - Positional-only parameter in add_sign
    """

    def __init__(
        self,
        *,
        max_history: int = _DEFAULT_MAX_HISTORY,
        separator: str = " ",
    ) -> None:
        """Keyword-only: max_history, separator."""
        self.max_history: int  = max_history
        self.separator:   str  = separator
        self._tokens:     list[str] = []

    def add_sign(
        self,
        label: str,        # positional-or-keyword
        /,                 # everything before / is positional-only
        *,                 # everything after * is keyword-only
        capitalize: bool = True,
    ) -> str:
        """Append a sign label and return the current sentence.

        Positional-only: label.
        Keyword-only:    capitalize.
        """
        token = label.strip()
        if capitalize:
            token = token.title()
        if not token:
            return self.text
        self._tokens.append(token)
        # Trim to max_history using slice assignment (avoids recreation)
        if len(self._tokens) > self.max_history:
            self._tokens = self._tokens[-self.max_history:]
        return self.text

    def clear(self) -> None:
        """Remove all accumulated tokens."""
        self._tokens.clear()

    # ── @property ─────────────────────────────────────────────────────
    @property
    def text(self) -> str:
        """Current sentence as a single string."""
        return self.separator.join(self._tokens)

    @property
    def word_count(self) -> int:
        """Number of tokens currently accumulated."""
        return len(self._tokens)

    # ── Generator method ──────────────────────────────────────────────
    def token_stream(self) -> Generator[str, None, None]:
        """Generator: yield each token in the current sentence one by one.

        Internally delegates to SentenceTokenIterator (iterator protocol).
        Demonstrates generator wrapping an iterator.
        """
        yield from SentenceTokenIterator(self.text, sep=self.separator)

    # ── __iter__ — makes SentenceAssembler itself iterable ───────────
    def __iter__(self) -> Iterator[str]:
        """Return a SentenceTokenIterator over the current text.

        Demonstrates __iter__ enabling for-loops directly on the assembler.
        """
        return iter(SentenceTokenIterator(self.text, sep=self.separator))

    # ── Dunder methods ────────────────────────────────────────────────
    def __len__(self) -> int:
        return self.word_count

    def __contains__(self, word: str) -> bool:
        """Support 'word in assembler' membership test."""
        return word.title() in self._tokens or word in self._tokens

    def __repr__(self) -> str:
        return (
            f"SentenceAssembler("
            f"words={self.word_count}, "
            f"max_history={self.max_history}, "
            f"text={self.text!r})"
        )

    def __str__(self) -> str:
        return self.text
