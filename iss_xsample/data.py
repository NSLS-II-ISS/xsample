"""Data preparation independent of Qt and beamline hardware."""

import numpy as np
import pandas as pd


def pad_setpoints(df, latest_time, delta_thresh=15):
    """Hold the previous setpoint across gaps and extend to the latest reading.

    A point 50 ms before each change keeps the original plotting convention.
    Compare explicit nanoseconds so pandas' datetime resolution does not change
    the gap threshold. The input frame is never modified.
    """
    if df.empty:
        return df.loc[:, ["time", "data"]].copy()
    timestamps = pd.DatetimeIndex(df["time"]).as_unit("ns")
    times = timestamps.asi8
    values = df["data"].to_numpy()
    gaps = np.flatnonzero(np.diff(times) > delta_thresh * 1_000_000_000) + 1
    padded_times = np.insert(times, gaps, times[gaps] - 50_000_000)
    padded_values = np.insert(values, gaps, values[gaps - 1])
    if latest_time is not None:
        latest = pd.Timestamp(latest_time)
        if (latest.tzinfo is None) != (timestamps.tz is None):
            raise ValueError(
                "Setpoint and latest reading timestamps must use matching timezones"
            )
        if latest.value > padded_times[-1]:
            padded_times = np.append(padded_times, latest.value)
            padded_values = np.append(padded_values, padded_values[-1])
    result_times = pd.to_datetime(padded_times)
    if timestamps.tz is not None:
        result_times = result_times.tz_localize("UTC").tz_convert(timestamps.tz)
    return pd.DataFrame({"time": result_times, "data": padded_values})


def program_dataframe(steps):
    """Serialize program steps in insertion order using the existing XLSX layout."""
    columns = {
        "param": [
            "temp",
            "duration",
            "rate",
            "flow1",
            "flow2",
            "flow3",
            "flow4",
            "flow5",
        ],
        "source": [0, 0, 0],
        "gas": [0, 0, 0],
    }
    first = next(iter(steps.values()), {})
    for i in range(1, 6):
        flow = first.get(f"flow_{i}")
        columns["source"].append(flow["source"] if flow else -1)
        columns["gas"].append(flow["name"] if flow else -1)
    for number, step in enumerate(steps.values(), start=1):
        values = [step["temp"], step["duration"], step["rate"]]
        directions = [None] * 3
        for i in range(1, 6):
            flow = step.get(f"flow_{i}")
            values.append(flow["flow"] if flow else -1)
            directions.append(
                ("reactor" if flow["to_reactor"] else "exhaust") if flow else -1
            )
        columns[number] = values
        columns[f"direction_{number}"] = directions
    return pd.DataFrame(columns)
