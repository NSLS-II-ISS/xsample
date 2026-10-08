"""ISS gas handling and sample environment controls."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("iss-xsample")
except PackageNotFoundError:
    __version__ = "0.0.0"
