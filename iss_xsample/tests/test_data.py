import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from iss_xsample.data import pad_setpoints, program_dataframe


@pytest.mark.parametrize("unit", ["ns", "us", "ms", "s"])
def test_setpoint_gaps_and_extension(unit):
    times = pd.date_range("2026-01-01", periods=3, freq="20s").as_unit(unit)
    frame = pd.DataFrame({"time": times, "data": [10.0, 20.0, 30.0]})
    original = frame.copy(deep=True)
    latest = times[-1] + pd.Timedelta(seconds=5)
    result = pad_setpoints(frame, latest)
    assert result["data"].tolist() == [10, 10, 20, 20, 30, 30]
    assert result["time"].tolist() == [
        times[0],
        times[1] - pd.Timedelta(milliseconds=50),
        times[1],
        times[2] - pd.Timedelta(milliseconds=50),
        times[2],
        latest,
    ]
    assert_frame_equal(frame, original)


def test_no_gap_at_threshold_and_no_backward_extension():
    times = pd.date_range("2026-01-01", periods=2, freq="15s")
    frame = pd.DataFrame({"time": times, "data": [10, 20]})
    result = pad_setpoints(frame, times[0])
    assert result["data"].tolist() == [10, 20]
    assert result["time"].tolist() == times.tolist()


def test_empty_and_single_point():
    empty = pd.DataFrame(
        {"time": pd.Series(dtype="datetime64[ns]"), "data": pd.Series(dtype=float)}
    )
    assert_frame_equal(pad_setpoints(empty, pd.Timestamp("2026-01-01")), empty)
    single = pd.DataFrame({"time": [pd.Timestamp("2026-01-01")], "data": [42]})
    assert pad_setpoints(single, None)["data"].tolist() == [42]


def test_timezone_preserved_across_dst():
    times = pd.date_range("2026-11-01 00:30", periods=3, freq="h", tz="US/Eastern")
    result = pad_setpoints(pd.DataFrame({"time": times, "data": [1, 2, 3]}), times[-1])
    assert str(result["time"].dt.tz) == "US/Eastern"
    assert result["time"].is_monotonic_increasing
    assert result["time"].iloc[-1] == times[-1]


def test_non_contiguous_program_keys_and_excel_roundtrip(program_steps, tmp_path):
    steps = {10: program_steps[0], 20: program_steps[1]}
    frame = program_dataframe(steps)
    assert list(frame) == ["param", "source", "gas", 1, "direction_1", 2, "direction_2"]
    assert frame[1].tolist() == [50, 10, 2.5, 5, -1, -1, -1, -1]
    assert frame.loc[3, "direction_1"] == "reactor"
    assert frame.loc[3, "direction_2"] == "exhaust"
    path = tmp_path / "program.xlsx"
    frame.to_excel(path)
    restored = pd.read_excel(path, index_col=0)
    np.testing.assert_allclose(restored[2], frame[2])
    assert restored.loc[3, "source"] == "GHS Ch1"


def test_empty_program():
    frame = program_dataframe({})
    assert frame.shape == (8, 3)
