# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information


project = 'Social Interaction Cloud'
copyright = '2025, Koen Hindriks'
author = 'Koen Hindriks'
version = '2.0.38'
release = '2.0.38'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

import os
import sys
sys.path.insert(0, os.path.abspath('../../'))

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.githubpages',
    'sphinx.ext.napoleon',  # For Google/NumPy style docstrings
    'sphinx_togglebutton',
    'sphinx_copybutton',
]

togglebutton_hint = ""

templates_path = ['_templates']
exclude_patterns = []

language = 'en'

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

# Logo and favicon configuration
html_logo = '_static/sic_mini_logo.svg'
html_favicon = '_static/sic_mini_logo.svg'

# Theme options to show logo and project name
html_theme_options = {
    'logo_only': False,
}

# Custom CSS to make the logo smaller
html_css_files = [
    'custom.css',
]

# -- Autodoc configuration ---------------------------------------------------
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'exclude-members': '__weakref__'
}

# Mock imports for optional dependencies that may not be installed
autodoc_mock_imports = [
    'panda_py',  # Franka robot library
    'motpy',     # Object tracking library
    'cv2.ximgproc',  # OpenCV contrib module
]

# Suppress warnings for modules that cannot be imported
suppress_warnings = ['autodoc']

# -- Napoleon configuration --------------------------------------------------
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = True
