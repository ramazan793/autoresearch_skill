#!/usr/bin/env python3
"""Which GPUs are safe to take, based on a sampling window.

Samples nvidia-smi every --interval s for --window s, averages utilization and
VRAM per GPU, lists compute processes with owners, and classifies each GPU:

  FREE    no meaningful util, no meaningful VRAM, no compute processes
  PARKED  idle util but a process is holding VRAM (someone's job — do NOT take)
  BUSY    actively used

Prints a table plus a CUDA_VISIBLE_DEVICES recommendation; --json for agents.
Exit code 0 if at least one FREE GPU, else 1. Indices are nvidia-smi (PCI)
order — export CUDA_DEVICE_ORDER=PCI_BUS_ID so CUDA numbering matches.
"""
import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict


def smi(query, fields):
    cmd = ["nvidia-smi", "--query-%s=%s" % (query, ",".join(fields)),
           "--format=csv,noheader,nounits"]
    try:
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             universal_newlines=True, timeout=20)
    except FileNotFoundError:
        sys.exit("nvidia-smi not found — is this a GPU machine?")
    if out.returncode != 0:
        sys.exit("nvidia-smi failed: %s" % out.stderr.strip())
    return [[c.strip() for c in line.split(",")]
            for line in out.stdout.splitlines() if line.strip()]


def num(s):
    try:
        return float(s)
    except ValueError:
        return None  # "[N/A]" etc.


def collect(args):
    samples = defaultdict(list)
    meta = {}
    n = max(1, int(round(args.window / args.interval)))
    for i in range(n):
        t0 = time.time()
        for r in smi("gpu", ["index", "uuid", "name", "utilization.gpu",
                             "memory.used", "memory.total"]):
            idx = int(r[0])
            meta[idx] = {"uuid": r[1], "name": r[2], "total_mb": num(r[5]) or 0.0}
            samples[idx].append((num(r[3]) or 0.0, num(r[4]) or 0.0))
        if i < n - 1:
            time.sleep(max(0.0, args.interval - (time.time() - t0)))

    by_uuid = {m["uuid"]: idx for idx, m in meta.items()}
    procs = defaultdict(list)
    for r in smi("compute-apps", ["gpu_uuid", "pid", "used_memory"]):
        if len(r) < 3 or r[0] not in by_uuid or num(r[1]) is None:
            continue
        procs[by_uuid[r[0]]].append({"pid": int(num(r[1])), "mem_mb": num(r[2])})

    pids = sorted({p["pid"] for pl in procs.values() for p in pl})
    users = {}
    if pids:
        out = subprocess.run(["ps", "-o", "pid=,user=", "-p", ",".join(map(str, pids))],
                             stdout=subprocess.PIPE, universal_newlines=True)
        for line in out.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[0].isdigit():
                users[int(parts[0])] = parts[1].strip()
    for pl in procs.values():
        for p in pl:
            p["user"] = users.get(p["pid"], "?")

    gpus = []
    for idx in sorted(samples):
        utils = [u for u, _ in samples[idx]]
        mems = [m for _, m in samples[idx]]
        total = meta[idx]["total_mb"]
        avg_util, peak_util = sum(utils) / len(utils), max(utils)
        avg_mem = sum(mems) / len(mems)
        plist = procs.get(idx, [])
        mem_floor = max(args.max_mem_frac * total, 1024.0)
        if plist:
            status = "BUSY" if avg_util > args.max_util else "PARKED"
        elif avg_util <= args.max_util and avg_mem <= mem_floor:
            status = "FREE"
        else:
            status = "BUSY"
        gpus.append({"index": idx, "name": meta[idx]["name"],
                     "avg_util": round(avg_util, 1), "peak_util": round(peak_util, 1),
                     "avg_mem_mb": round(avg_mem), "total_mb": round(total),
                     "procs": plist, "status": status})
    return gpus, len(samples[min(samples)]) if samples else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", type=float, default=15.0, help="sampling window, s (default 15)")
    ap.add_argument("--interval", type=float, default=1.0, help="sample period, s (default 1)")
    ap.add_argument("--max-util", type=float, default=5.0,
                    help="avg util %% at or below which a GPU counts as idle (default 5)")
    ap.add_argument("--max-mem-frac", type=float, default=0.05,
                    help="avg used-VRAM fraction counting as free (default 0.05, min 1 GiB)")
    ap.add_argument("--top", type=int, default=None, help="recommend at most N GPUs")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    gpus, nsamples = collect(args)
    if not gpus:
        sys.exit("no GPUs reported by nvidia-smi")

    free = [g["index"] for g in sorted((g for g in gpus if g["status"] == "FREE"),
                                       key=lambda g: (g["avg_util"], g["avg_mem_mb"]))]
    rec = free[:args.top] if args.top else free

    if args.json:
        print(json.dumps({"window_s": args.window, "samples": nsamples, "gpus": gpus,
                          "free": free, "recommended": ",".join(map(str, rec))}, indent=2))
    else:
        print("sampled %d snapshots over %.0fs" % (nsamples, args.window))
        hdr = "%3s  %-28s %9s %6s  %18s  %-22s %s"
        print(hdr % ("GPU", "name", "util avg", "peak", "VRAM avg (MiB)", "procs (owners)", "status"))
        for g in gpus:
            owners = sorted({p["user"] for p in g["procs"]})
            pstr = "%d (%s)" % (len(g["procs"]), ",".join(owners)) if g["procs"] else "-"
            print(hdr % (g["index"], g["name"][:28], "%.1f%%" % g["avg_util"],
                         "%.0f%%" % g["peak_util"],
                         "%d/%d" % (g["avg_mem_mb"], g["total_mb"]), pstr, g["status"]))
        if rec:
            print("\nFREE: %s  ->  export CUDA_VISIBLE_DEVICES=%s"
                  % (",".join(map(str, free)), ",".join(map(str, rec))))
        else:
            print("\nno FREE GPUs right now")
    sys.exit(0 if free else 1)


if __name__ == "__main__":
    main()
