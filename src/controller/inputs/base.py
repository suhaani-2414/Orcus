"""Input source interface.

Every modality (voice, gesture, keyboard) implements this and yields normalized
Events. The rest of the system consumes Events without knowing the source.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from controller.decision.schemas import Event


class InputSource(ABC):
    @abstractmethod
    def events(self) -> Iterator[Event]:
        """Yield normalized events until the source is exhausted or stopped."""
        raise NotImplementedError
