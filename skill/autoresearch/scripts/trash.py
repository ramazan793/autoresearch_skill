#!/usr/bin/env python3
"""Move files/dirs into the repo's trash/ instead of deleting.

Destination: <git root>/trash/ (or $TRASH_DIR). Nothing in trash/ is ever
overwritten: if the name is taken, the EXISTING trash entry is first shelved
under a timestamp suffix, and the incoming file keeps the clean name (newest =
clean name). The user empties trash/ manually.

Usage: trash.py PATH [PATH ...]
"""
import os
import shutil
import sys
import time


def repo_root(start):
    d = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.getcwd()
        d = parent


def shelve(dst):
    stamp = time.strftime("%Y%m%d_%H%M%S")
    shelved = "%s_%s" % (dst, stamp)
    i = 0
    while os.path.lexists(shelved):
        i += 1
        shelved = "%s_%s_%d" % (dst, stamp, i)
    os.rename(dst, shelved)
    return shelved


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip())
    trash = os.environ.get("TRASH_DIR") or os.path.join(repo_root(os.getcwd()), "trash")
    os.makedirs(trash, exist_ok=True)
    trash_abs = os.path.realpath(trash)
    status = 0
    for p in sys.argv[1:]:
        src = os.path.abspath(p.rstrip("/"))
        if not os.path.lexists(src):
            print("trash: missing, skipped: %s" % p, file=sys.stderr)
            status = 1
            continue
        src_real = os.path.realpath(src)
        if src_real == trash_abs or trash_abs.startswith(src_real + os.sep):
            print("trash: refusing to trash the trash dir itself: %s" % p, file=sys.stderr)
            status = 1
            continue
        dst = os.path.join(trash, os.path.basename(src))
        if os.path.lexists(dst):
            shelved = shelve(dst)
            print("trash: shelved existing %s -> %s"
                  % (os.path.basename(dst), os.path.basename(shelved)))
        shutil.move(src, dst)
        print("%s -> %s" % (p, dst))
    sys.exit(status)


if __name__ == "__main__":
    main()
