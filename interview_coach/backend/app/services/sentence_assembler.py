"""Assemble recognized signs into a sentence."""

from __future__ import annotations

from typing import Generator, List

from app.core.iterators import SentenceTokenIterator


class SentenceAssembler:
    def __init__(self, *, max_history: int = 20, separator: str = " "):
        self.max_history = max_history
        self.separator = separator
        self._tokens: List[str] = []

    def add_sign(self, label: str, /, *, capitalize: bool = True) -> str:
        token = label.strip()
        if capitalize:
            token = token.title()
        if not token:
            return self.text
        self._tokens.append(token)
        if len(self._tokens) > self.max_history:
            self._tokens = self._tokens[-self.max_history :]
        return self.text

    @property
    def text(self) -> str:
        return self.separator.join(self._tokens)

    def clear(self) -> None:
        self._tokens.clear()

    def token_stream(self) -> Generator[str, None, None]:
        """Generator wrapper around sentence tokens."""
        yield from SentenceTokenIterator(self.text)