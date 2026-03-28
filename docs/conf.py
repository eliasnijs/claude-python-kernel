import os
import sys
sys.path.insert(0, os.path.abspath(".."))

project = "claude-python-kernel"
author = "eliasnijs"
release = "1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

html_theme = "sphinx_rtd_theme"
templates_path = ["_templates"]
exclude_patterns = ["_build"]
