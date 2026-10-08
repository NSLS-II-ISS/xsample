"""Compare vectorized padding with the previous per-row membership loop."""

import statistics
import time

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from iss_xsample.data import pad_setpoints


def previous_padding(frame, latest):
    times = frame["time"].to_numpy(dtype="datetime64[ns]")
    values = frame["data"].to_numpy()
    gaps = np.flatnonzero(np.diff(times).astype(np.int64) * 1e-9 > 15) + 1
    padded_times, padded_values = [], []
    for index in range(len(times)):
        if index in gaps:
            padded_times.append(times[index] - np.timedelta64(50, "ms"))
            padded_values.append(values[index - 1])
        padded_times.append(times[index])
        padded_values.append(values[index])
    if padded_times[-1] < latest:
        padded_times.append(latest)
        padded_values.append(padded_values[-1])
    return pd.DataFrame({"time": padded_times, "data": padded_values})


def main():
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=20_000, freq="20s").as_unit(
                "ns"
            ),
            "data": np.arange(20_000, dtype=float),
        }
    )
    latest = frame["time"].iloc[-1].to_datetime64() + np.timedelta64(5, "s")
    assert_frame_equal(previous_padding(frame, latest), pad_setpoints(frame, latest))
    timings = []
    for function in (previous_padding, pad_setpoints):
        samples = []
        for _ in range(5):
            start = time.perf_counter()
            function(frame, latest)
            samples.append(time.perf_counter() - start)
        timings.append(statistics.median(samples))
    print("20,000 readings, median of 5 runs; identical output verified")
    print(f"Previous loop: {timings[0] * 1000:.2f} ms")
    print(f"Vectorized:    {timings[1] * 1000:.2f} ms")
    print(f"Speedup:       {timings[0] / timings[1]:.1f}x")


if __name__ == "__main__":
    main()
