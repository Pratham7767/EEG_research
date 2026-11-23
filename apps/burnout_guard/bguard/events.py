"""Tiny pub/sub bus (adapted from SpeechEEG_Recorder/core/device_manager.py)."""
import logging

logger = logging.getLogger(__name__)


class EventBus:
    """Multiple listeners per event; a failing listener never breaks the others."""

    def __init__(self):
        self._listeners = {}

    def subscribe(self, event, callback):
        self._listeners.setdefault(event, []).append(callback)

        def _unsubscribe():
            try:
                self._listeners[event].remove(callback)
            except (KeyError, ValueError):
                pass
        return _unsubscribe

    def emit(self, event, *args, **kwargs):
        for callback in list(self._listeners.get(event, [])):
            try:
                callback(*args, **kwargs)
            except Exception:
                logger.exception("listener for %r failed", event)
