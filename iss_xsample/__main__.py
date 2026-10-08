"""Launch with a beamline factory, or check the installed UI without hardware."""

import argparse
import importlib
import sys
from importlib.resources import as_file, files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--factory",
        metavar="MODULE:CALLABLE",
        help="callable returning XsampleGui keyword arguments",
    )
    mode.add_argument(
        "--smoke-test",
        action="store_true",
        help="load both UI files and render a plot, then exit",
    )
    args = parser.parse_args(argv)

    from PyQt5 import QtWidgets, uic

    from iss_xsample.xsample import XsampleGui

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([sys.argv[0]])
    if args.smoke_test:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        from iss_xsample.gas_type import GasType

        with as_file(files("iss_xsample").joinpath("ui/xsample_new.ui")) as path:
            window = uic.loadUi(str(path))
        gas = GasType(gas_name="He")
        canvas = FigureCanvasQTAgg(Figure())
        canvas.figure.subplots().plot([0, 1], [0, 1])
        canvas.draw()
        app.processEvents()
        window.close()
        gas.close()
        canvas.close()
        print("UI resources, Qt, and Matplotlib smoke test passed.")
        return 0

    module, separator, name = args.factory.partition(":")
    if not separator or not module or not name:
        parser.error("--factory must have the form MODULE:CALLABLE")
    factory = getattr(importlib.import_module(module), name)
    window = XsampleGui(**factory())
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
