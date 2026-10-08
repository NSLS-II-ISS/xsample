from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest


@pytest.fixture
def gui(qtbot, monkeypatch):
    from iss_xsample.xsample import XsampleGui

    # Isolate timer callbacks; tests explicitly request the update under test.
    monkeypatch.setattr(XsampleGui, "read_archiver", lambda self: None)
    monkeypatch.setattr(XsampleGui, "update_status", lambda self: None)
    monkeypatch.setattr(XsampleGui, "update_sample_env_status", lambda self: None)

    def signal(value=0):
        return Mock(get=Mock(return_value=value))

    channels = {str(i): defaultdict(signal) for i in range(1, 3)}
    sample = Mock(pv=signal(25), current_pv_reading=Mock(return_value=25))
    cart = {
        i: {"mfc": SimpleNamespace(sp=signal(), rb=signal()), "vlv": Mock()}
        for i in range(1, 5)
    }
    window = XsampleGui(
        gas_cart=cart,
        ghs={
            "channels": channels,
            "manifolds": {str(i): {"gas_selector": signal()} for i in range(1, 6)},
        },
        switch_manifold={},
        RE=Mock(side_effect=lambda plan: list(plan)),
        archiver=Mock(),
        total_flow_meter=Mock(get=Mock(return_value=SimpleNamespace(rb=0))),
        sample_envs_dict={"test": sample},
    )
    qtbot.addWidget(window)
    for timer in (
        window.timer_read_archiver,
        window.timer_update_time,
        window.timer_sample_env_status,
    ):
        timer.stop()
    return window


@pytest.fixture
def program_steps():
    def step(temp, duration, flow, to_reactor):
        return {
            "temp": temp,
            "duration": duration,
            "rate": 2.5,
            "flow_1": {
                "source": "GHS Ch1",
                "name": "He",
                "flow": flow,
                "to_reactor": to_reactor,
            },
            **{f"flow_{i}": None for i in range(2, 6)},
        }

    return {0: step(50, 10, 5, True), 1: step(75, 10, 8, False)}


@pytest.fixture
def readings():
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=3, freq="20s"),
            "data": [25.0, 50.0, 75.0],
        }
    )
