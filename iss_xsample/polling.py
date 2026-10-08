"""Bounded archiver reads with results delivered on the Qt owner thread."""

import threading
import time
from dataclasses import dataclass

from PyQt5.QtCore import QObject, Qt, pyqtSignal, pyqtSlot


@dataclass(frozen=True)
class ArchiverSnapshot:
    tables: object
    start: float
    end: float
    timewindow: float


class ArchiverPoller(QObject):
    ready = pyqtSignal(object)
    failed = pyqtSignal(str)
    _completed = pyqtSignal(object)

    def __init__(self, archiver, parent=None):
        super().__init__(parent)
        self.archiver = archiver
        self._busy = False
        self._closed = False
        self._completed.connect(self._deliver, Qt.QueuedConnection)

    def request(self, timewindow):
        """Start at most one read; call from the QObject's owner thread."""
        if self._busy or self._closed:
            return False
        self._busy = True
        threading.Thread(target=self._read, args=(timewindow,), daemon=True).start()
        return True

    def _read(self, timewindow):
        end = time.time()
        start = end - 3600 * timewindow
        try:
            result = ArchiverSnapshot(
                self.archiver.tables_given_times(start, end), start, end, timewindow
            )
        except Exception as exc:
            result = exc
        # A remote read may finish after the window and its QObjects are gone.
        try:
            self._completed.emit(result)
        except RuntimeError:
            pass

    @pyqtSlot(object)
    def _deliver(self, result):
        self._busy = False
        if self._closed:
            return
        if isinstance(result, Exception):
            self.failed.emit(str(result))
        else:
            self.ready.emit(result)

    def close(self):
        """Ignore late results without blocking GUI shutdown on remote I/O."""
        self._closed = True
