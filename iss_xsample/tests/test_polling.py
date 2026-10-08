import threading
from unittest.mock import Mock

from PyQt5.QtCore import QThread

from iss_xsample.polling import ArchiverPoller


def test_slow_requests_do_not_overlap_and_deliver_on_gui_thread(qtbot, qapp):
    started = threading.Event()
    release = threading.Event()
    worker_threads = []

    def read(start, end):
        worker_threads.append(threading.get_ident())
        started.set()
        assert release.wait(5)
        assert end - start == 7200
        return {"reading": 42}

    archiver = Mock(tables_given_times=Mock(side_effect=read))
    poller = ArchiverPoller(archiver)
    delivered = []
    poller.ready.connect(
        lambda result: delivered.append((result, QThread.currentThread()))
    )
    try:
        assert poller.request(2)
        qtbot.waitUntil(started.is_set)
        assert not poller.request(3)
        with qtbot.waitSignal(poller.ready, timeout=5000):
            release.set()
        assert archiver.tables_given_times.call_count == 1
        assert worker_threads[0] != threading.get_ident()
        snapshot, thread = delivered[0]
        assert thread == qapp.thread()
        assert snapshot.tables == {"reading": 42}
        assert snapshot.timewindow == 2
        with qtbot.waitSignal(poller.ready, timeout=5000):
            assert poller.request(2)
    finally:
        release.set()
        poller.close()


def test_errors_are_reported_and_next_poll_can_retry(qtbot):
    poller = ArchiverPoller(
        Mock(tables_given_times=Mock(side_effect=[RuntimeError("offline"), {}]))
    )
    with qtbot.waitSignal(poller.failed, timeout=5000) as error:
        assert poller.request(1)
    assert error.args == ["offline"]
    with qtbot.waitSignal(poller.ready, timeout=5000):
        assert poller.request(1)
    poller.close()


def test_close_ignores_late_results(qtbot):
    release = threading.Event()
    poller = ArchiverPoller(
        Mock(tables_given_times=Mock(side_effect=lambda *args: release.wait(5)))
    )
    ready = Mock()
    poller.ready.connect(ready)
    assert poller.request(1)
    poller.close()
    assert not poller.request(1)
    release.set()
    qtbot.waitUntil(lambda: not poller._busy)
    ready.assert_not_called()
