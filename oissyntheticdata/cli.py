# -*- coding: utf-8 -*-
"""The command `oissyntheticdata` (short: `oissd`).

    oissyntheticdata [auto|profile|synth|check|settings] [--data DIR] ...     the commands of gov_one.py
    oissyntheticdata export [FOLDER] [--force]                               copy the two files to carry in
    oissyntheticdata --version
"""
import os
import sys

import gov_one

CARRY = ("gov_one.py", "analysis_template.py")


def _source(name):
    here = os.path.dirname(os.path.abspath(__file__))
    for folder in ((os.path.dirname(os.path.abspath(gov_one.__file__)),) if name == "gov_one.py"
                   else (here, os.path.dirname(os.path.abspath(gov_one.__file__)))):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            return p
    return None


def export(folder=".", force=False):
    """Copy gov_one.py and analysis_template.py into `folder`.  A file that is already there with
    other content is left alone unless force is True.  Returns the list of files written."""
    folder = os.path.abspath(folder)
    os.makedirs(folder, exist_ok=True)
    written = []
    for name in CARRY:
        src, dst = _source(name), os.path.join(folder, name)
        if src is None:
            print("  [!] %s was not found in this installation" % name)
            continue
        with open(src, "rb") as f:
            data = f.read()
        if os.path.exists(dst):
            with open(dst, "rb") as f:
                same = f.read() == data
            if same:
                print("  [=] %s is already there" % dst)
                continue
            if not force:
                print("  [!] %s exists with other content; not overwritten (add --force to replace it)" % dst)
                continue
        with open(dst, "wb") as f:
            f.write(data)
        written.append(dst)
        print("  [OK] %s" % dst)
    print("Carry these two files into the premises. Nothing else is needed there: no installation, no internet.")
    return written


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "export":
        rest = [a for a in argv[1:] if a != "--force"]
        if len(rest) > 1 or any(a.startswith("-") for a in rest):
            raise SystemExit("usage: oissyntheticdata export [FOLDER] [--force]")
        export(rest[0] if rest else ".", force="--force" in argv[1:])
        return
    if argv and argv[0] in ("--version", "-V"):
        print("oissyntheticdata %s (%s)" % (gov_one.VERSION.split()[1], gov_one.VERSION))
        return
    if argv and argv[0] in ("-h", "--help"):
        print("oissyntheticdata export [FOLDER] [--force]\n"
              "    copy gov_one.py and analysis_template.py into FOLDER, to carry into the premises\n"
              "oissyntheticdata --version\n\n"
              "Every other command is passed to gov_one.py:\n")
    gov_one.main(argv)


if __name__ == "__main__":
    main()
