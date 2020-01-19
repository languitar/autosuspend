#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import os.path

# needs_sphinx = '1.0'

extensions = [
    "sphinx.ext.ifconfig",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.autodoc",
    "sphinx_autodoc_typehints",
    "sphinxcontrib.plantuml",
    "sphinx_issues",
]
templates_path = ['_templates']
source_suffix = '.rst'

master_doc = 'index'

project = 'autosuspend'
copyright = '2017, Johannes Wienke'
author = 'Johannes Wienke'

with open(os.path.join(
        os.path.abspath(os.path.dirname(os.path.realpath(__file__))),
        '../..',
        'VERSION'), 'r') as version_file:
    lines = version_file.readlines()
version = lines[0].strip()
release = lines[1].strip()

language = None

exclude_patterns = []

pygments_style = 'sphinx'

todo_include_todos = False

rst_epilog = '''
.. _autosuspend: https://github.com/languitar/autosuspend
.. _Python 3: https://docs.python.org/3/
.. _setuptools: https://setuptools.readthedocs.io
.. _configparser: https://docs.python.org/3/library/configparser.html
.. _psutil: https://github.com/giampaolo/psutil
.. _lxml: http://lxml.de/
.. _MPD: http://www.musicpd.org/
.. _python-mpd2: https://pypi.python.org/pypi/python-mpd2
.. _dbus-python: https://cgit.freedesktop.org/dbus/dbus-python/
.. _Kodi: https://kodi.tv/
.. _requests: https://pypi.python.org/pypi/requests
.. _systemd: https://www.freedesktop.org/wiki/Software/systemd/
.. _systemd service files: http://www.freedesktop.org/software/systemd/man/systemd.service.html
.. _broadcast-logging: https://github.com/languitar/broadcast-logging
.. _tvheadend: https://tvheadend.org/
.. _XPath: https://www.w3.org/TR/xpath/
.. _logind: https://www.freedesktop.org/wiki/Software/systemd/logind/
.. _iCalendar: https://tools.ietf.org/html/rfc5545
.. _dateutil: https://dateutil.readthedocs.io
.. _python-icalendar: https://icalendar.readthedocs.io
.. _tzlocal: https://pypi.org/project/tzlocal/
.. _requests-file: https://github.com/dashea/requests-file
.. _Plex: https://www.plex.tv/
.. _portalocker: https://portalocker.readthedocs.io

.. |project| replace:: {project}
.. |project_bold| replace:: **{project}**
.. |project_program| replace:: :program:`{project}`'''.format(project=project)

# Intersphinx

intersphinx_mapping = {'python': ('https://docs.python.org/3.7', None)}

# HTML options

html_theme = 'sphinx_rtd_theme'
# html_theme_options = {}

# html_static_path = ['_static']

html_sidebars = {
    '**': [
        'relations.html',  # needs 'show_related': True theme option to display
        'searchbox.html',
    ]
}

# MANPAGE options

man_pages = [
    ('man_command',
     'autosuspend',
     'autosuspend Documentation',
     [author],
     1),
    ('man_config',
     'autosuspend.conf',
     'autosuspend config file Documentation',
     [author],
     5),
]
man_show_urls = True

# issues
issues_github_path = 'languitar/autosuspend'

# napoleon
napoleon_google_docstring = True
napoleon_numpye_docstring = False
napoleon_include_init_with_doc = True

typehints_fully_qualified = True


def setup(app):
    app.add_config_value(
        'is_preview',
        os.environ.get('READTHEDOCS_VERSION', 'latest') == '',
        'env',
    )
