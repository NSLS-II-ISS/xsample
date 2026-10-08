==================
Supported versions
==================

Package metadata requires Python 3.11 or newer. The reproducible development
and CI environment targets Python 3.12 on Linux x86-64.

Runtime dependency ranges are maintained in ``pyproject.toml``; exact versions
are recorded in ``pixi.lock``. The application uses PyQt5, NumPy 2, pandas 2.2
or newer, Matplotlib 3.9 or newer, Bluesky 1.13 or newer, and openpyxl 3.1.5 or
newer. Upper bounds are declared for major upgrades that need separate testing.
