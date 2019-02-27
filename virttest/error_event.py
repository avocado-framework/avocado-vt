"""
Global background error event bus for vt test object.
This aims to share error event bus with asynchronous tasks launched by
avocado-vt, so that those tasks that have no reference to test could error the
test.

IMPORTANT: only for internal use inside avocado-vt.
"""

from six.moves import queue


class EventBus(object):
    """Event Bus."""

    def __init__(self):
        """Create the error event bus with queue.Queue."""
        self.error_events = queue.Queue()

    def put(self, event, block=True, timeout=None):
        """Put an event into the event bus."""
        self.error_events.put(event, block, timeout)

    def get(self, block=True, timeout=None):
        """Remove and return an event from the event bus."""
        try:
            return self.error_events.get(block, timeout)
        except queue.Empty:
            raise
        else:
            self.error_events.task_done()

    def __len__(self):
        """Return the event count."""
        return self.error_events.qsize()

    def get_all(self):
        """Remove and return a list of all events from the event bus."""
        error_events = []
        while len(self):
            try:
                error_events.append(self.get(block=False))
            except queue.Empty:
                pass
        return error_events

    def clear(self):
        """Clear all events in the event bus."""
        self.get_all()


error_events_bus = EventBus()
