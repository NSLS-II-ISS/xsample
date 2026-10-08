============
Installation
============

Install `Pixi <https://pixi.sh>`_ and run these commands from the repository::

    pixi install --locked
    pixi run smoke
    pixi run check

The lockfile targets Linux x86-64 with Python 3.12. The smoke test runs
offscreen without beamline hardware. A desktop Qt session is needed for
interactive operation.

Alternatively, install using Python 3.11 or newer::

    pip install .

Development tools are available through ``pip install -e '.[dev,docs]'``.
Runtime dependencies, including Excel support, are declared in
``pyproject.toml``.
