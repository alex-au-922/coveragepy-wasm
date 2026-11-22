from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class GuestCoverage:
    """Coverage settings and snapshot sink for one pytest test."""

    context: str
    branch: bool
    source: list[str]
    include: list[str] | None
    omit: list[str] | None
    _save: Callable[[bytes, bool], None] = field(repr=False)

    def save(self, snapshot: bytes, *, allow_empty: bool = False) -> None:
        """Submit a native Coverage.py file while the guest can still export it."""
        self._save(snapshot, allow_empty)
