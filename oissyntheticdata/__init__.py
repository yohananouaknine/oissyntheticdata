# -*- coding: utf-8 -*-
"""
oissyntheticdata — pure-Python sequential CART synthesis, in the synthpop tradition.

Zero third-party dependencies (standard library only). Designed for secure
research environments: develop and debug your analysis on the synthetic data
off-site, then run the final code on the real data on-premises.

Single table
------------
    import oissyntheticdata
    oissyntheticdata.synthesize_file("real.csv", "synthetic.csv",
                            drop=["national_id"], min_leaf=5)

Related tables (referential integrity preserved)
-------------------------------------------------
    oissyntheticdata.synthesize_relational_files(
        {"inmates": "inmates.csv", "judgements": "judgements.csv"},
        schema={
            "inmates":    {"key": "prisoner_id"},
            "judgements": {"key": "judgement_id",
                           "parent": "inmates", "foreign_key": "prisoner_id"},
        },
        out_dir="out", min_leaf=5)
"""

from ._io import read_table, write_table
from ._synth import synthesize
from ._relational import synthesize_relational, synthesize_relational_files

__version__ = "1.0.0"
__all__ = [
    "read_table", "write_table", "synthesize", "synthesize_file",
    "synthesize_relational", "synthesize_relational_files",
]


def synthesize_file(in_path, out_path, n=None, visit=None, drop=None,
                    min_leaf=5, max_depth=12, smoothing=0.0, seed=12345):
    """Read a CSV/XLSX, synthesize one flat table, and write a CSV."""
    header, cols = read_table(in_path)
    out_header, out_cols = synthesize(
        header, cols, n=n, visit=visit, drop=drop,
        min_leaf=min_leaf, max_depth=max_depth, smoothing=smoothing, seed=seed)
    write_table(out_path, out_header, out_cols)
    nrows = len(out_cols[out_header[0]]) if out_header else 0
    return nrows, len(out_header)
