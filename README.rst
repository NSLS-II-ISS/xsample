===========
iss-xsample
===========

A PyQt5 interface for ISS gas handling, sample temperature programs, and
archived flow and temperature plots. Licensed under the 3-clause BSD license.

Run with Pixi
-------------

Install `Pixi <https://pixi.sh>`_, then from this checkout::

    pixi install --locked
    pixi run smoke
    pixi run check

The committed ``pixi.lock`` provides a reproducible Linux x86-64 environment
with Python 3.12. ``smoke`` loads both UI resources and renders a Matplotlib
plot offscreen, without connecting to hardware. ``check`` runs Ruff, formatting
checks, and tests using fake devices.

The full application requires the beamline devices, RunEngine, and archiver.
Existing startup code can continue to construct
``iss_xsample.xsample.XsampleGui(...)``. To launch from Pixi, provide an importable
factory that returns its constructor keyword arguments::

    pixi run start --factory beamline_startup:create_xsample_config

For example, in your beamline startup module:

.. code-block:: python

    def create_xsample_config():
        # These objects are supplied by your beamline configuration.
        return dict(
            gas_cart=gas_cart,
            mobile_gh_system=mobile_gh_system,
            total_flow_meter=total_flow_meter,
            rga_channels=rga_channels,
            rga_masses=rga_masses,
            ghs=ghs,
            switch_manifold=switch_manifold,
            RE=RE,
            archiver=archiver,
            sample_envs_dict=sample_envs_dict,
            reset_rga=reset_rga,
            flow_condition_valves=flow_condition_valves,
            pdu=pdu,
        )

Install any site-specific device packages into the environment and make the
startup module importable. A desktop display is required for interactive use.
There is no default beamline configuration in this repository.

Development
-----------

Dependencies and tasks are declared in ``pyproject.toml``. To update the
resolved versions, run ``pixi update`` and then ``pixi run check``. Review and
commit ``pixi.lock`` with dependency changes. Useful commands::

    pixi run test
    pixi run lint
    pixi run format
    pixi run docs
    pixi run build
    pixi run benchmark

For a pip installation with Python 3.11 or newer, use ``pip install .`` or
``pip install -e '.[dev,docs]'``. Pixi is the tested, locked development path.
Both Qt Designer UI files are included in wheels and source distributions.

The archiver poller permits one request at a time and delivers a complete
snapshot on the Qt thread. Failed requests are logged and retried on the next
poll. Timestamp padding is vectorized, preserves timezone information, and
handles empty data and pandas datetime resolutions explicitly. Excel import
blocks intermediate table signals to avoid recalculating loaded values.

The included padding benchmark compares identical output for 20,000 readings
with gaps (median of five runs). On the development host, the previous loop
took 228 ms and the vectorized implementation took 13 ms, about 17 times
faster. This measures data preparation, not end-to-end GUI or network latency.
