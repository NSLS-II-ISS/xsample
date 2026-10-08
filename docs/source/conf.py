"""Sphinx configuration for the installed package."""

from iss_xsample import __version__

project = "iss-xsample"
author = "Brookhaven National Lab"
copyright = "2026, Brookhaven National Lab"
version = release = __version__
extensions = ["sphinx.ext.autodoc", "sphinx.ext.autosummary", "sphinx.ext.githubpages"]
autosummary_generate = True
master_doc = "index"
language = "en"
html_theme = "sphinx_rtd_theme"
