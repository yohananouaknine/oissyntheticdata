# -*- coding: utf-8 -*-
"""oissyntheticdata -- the name on PyPI of the single file gov_one.py.

    import oissyntheticdata as g        is the same as        import gov_one as g

Everything lives in gov_one.py (Python standard library only, offline).  This package adds
nothing to it except the command

    oissyntheticdata export [FOLDER]

which copies gov_one.py and analysis_template.py into a folder, so the two files can be carried
into premises where nothing can be installed.

Write your analysis scripts with `import gov_one as g`: that line works at home (installed) and
on the premises (gov_one.py next to the script), so the same script runs in both places.
"""
import gov_one as _g

__version__ = _g.VERSION.split()[1]


def __getattr__(name):                 # every name of gov_one, always its current value
    return getattr(_g, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_g)))
