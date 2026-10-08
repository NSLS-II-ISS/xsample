=====
Usage
=====

Existing beamline startup code can instantiate the GUI with its configured
hardware objects:

.. code-block:: python

    from iss_xsample.xsample import XsampleGui

    window = XsampleGui(**beamline_configuration)
    window.show()

A Qt application and event loop must already exist when embedding the GUI.
For standalone use, provide an importable callable returning the same keyword
arguments::

    pixi run start --factory beamline_startup:create_xsample_config

The factory runs after the Qt application has been created. It must supply the
gas cart, GHS channel/manifold mappings, switching manifold mapping, RunEngine,
archiver, total flow meter, and a nonempty sample environment mapping. Supply
RGA, mobile gas system, condition valves, PDU, and reset callback when using
those controls. See the repository README for a complete factory example.

``pixi run smoke`` loads the UI and renders a plot without initializing any
beamline devices. It does not validate live hardware connectivity.

Developer commands::

    pixi run check
    pixi run docs
    pixi run build

To refresh dependencies, use ``pixi update``, rerun the checks, and commit the
updated lockfile.
