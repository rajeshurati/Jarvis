"""Continuous, privacy-bounded room occupancy monitoring."""

from __future__ import annotations

import asyncio

from jarvis.application.identity_service import FaceAuthorizationService
from jarvis.capabilities.identity import IdentityError
from jarvis.capabilities.memory import MemoryStore, PresenceEventRecord


class PresenceMonitorService:
    """Poll transient face counts and persist only occupancy transitions."""

    def __init__(
        self,
        identity: FaceAuthorizationService,
        memory: MemoryStore,
        interval_seconds: float = 10,
        enabled: bool = True,
    ) -> None:
        if not 2 <= interval_seconds <= 300:
            raise ValueError("Presence interval must be between 2 and 300 seconds")
        self._identity = identity
        self._memory = memory
        self._interval = interval_seconds
        self._enabled = enabled
        self._occupied: bool | None = None
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def enable(self) -> None:
        """Enable polling without creating a second background task."""
        self._enabled = True

    def disable(self) -> None:
        """Pause camera polling while preserving local event history."""
        self._enabled = False

    async def start(self) -> None:
        """Start one background loop."""
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="jarvis-presence-monitor")

    async def stop(self) -> None:
        """Stop polling and wait for clean loop termination."""
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def sample(self) -> PresenceEventRecord | None:
        """Capture once and persist only an initial state or occupancy change."""
        try:
            faces = await asyncio.to_thread(self._identity.faces_current)
            self._last_error = None
        except IdentityError:
            self._last_error = "Webcam presence sampling failed."
            return None
        occupied = faces > 0
        if self._occupied is occupied:
            return None
        if self._occupied is None:
            state = "present" if occupied else "vacant"
        else:
            state = "entered" if occupied else "left"
        self._occupied = occupied
        return await asyncio.to_thread(self._memory.append_presence_event, state, faces)

    def summary(self) -> str:
        """Return the newest locally recorded occupancy state."""
        events = self._memory.list_presence_events(1)
        if not events:
            return "No room-presence event has been recorded yet."
        event = events[0]
        return f"Latest room state is {event.state}, with {event.faces} faces detected."

    async def _run(self) -> None:
        while not self._stop.is_set():
            if self._enabled:
                await self.sample()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue
