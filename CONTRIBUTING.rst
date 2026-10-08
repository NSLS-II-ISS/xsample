============
Contributing
============

Create a branch, install Pixi, and set up the locked environment::

    pixi install --locked

After making changes, format the code and run the checks::

    pixi run format
    pixi run check
    pixi run docs
    pixi run build

Tests run offscreen using fake beamline devices. Add regression tests for
changes to data preparation, polling, program handling, or Qt signal behavior.
A passing test suite does not verify live beamline operation.

Maintain dependency ranges in ``pyproject.toml``. Run ``pixi update`` to refresh
the lockfile, validate the result, and include ``pixi.lock`` in the pull request.
Explain the resulting behavior and relevant validation in the pull request.
