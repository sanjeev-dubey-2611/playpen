#!/usr/bin/env python3
"""Run player9 on every scenario x seeds in PARALLEL, capture full stats.

Usage: uv run run_all_rooms.py [--seeds 1 2 42] [--player 9] [--out results]
                               [--workers N]
"""
import argparse
import csv
import json
import os
import re
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


def parse(out):
    d = {"note": "", "valid": None, "area": None, "perimeter": None,
         "gates": None, "second_gate_bonus": None, "score": None, "cpu_s": None}
    for line in out.splitlines():
        if line.startswith("note:"):
            d["note"] = line.split("note:", 1)[1].strip()
        elif line.startswith("valid:"):
            d["valid"] = line.split("valid:", 1)[1].strip().startswith("True")
        elif line.startswith("area="):
            for k, v in re.findall(r"(area|perimeter|gates)=([\d.]+)", line):
                d[k] = float(v)
            m = re.search(r"second_gate_bonus=(\w+)", line)
            if m:
                d["second_gate_bonus"] = m.group(1) == "True"
        elif line.startswith("SCORE:"):
            d["score"] = float(line.split("SCORE:", 1)[1].strip())
        elif "player CPU time" in line:
            m = re.search(r"([\d.]+)s", line)
            if m:
                d["cpu_s"] = float(m.group(1))
    return d


def run_one(job):
    sc, seed, player, cpu_limit, timeout = job
    t0 = time.time()
    try:
        r = subprocess.run(
            ["uv", "run", "main.py", "--player", player,
             "--scenario", sc, "--seed", str(seed), "--cpu-limit", str(cpu_limit)],
            capture_output=True, text=True, timeout=timeout,
        )
        out = r.stdout + "\n" + r.stderr
        status = "ok" if r.returncode == 0 else f"exit{r.returncode}"
    except subprocess.TimeoutExpired:
        out = ""
        status = "timeout"
    wall = time.time() - t0
    d = parse(out)
    return {"scenario": Path(sc).stem, "scenario_path": sc, "seed": seed,
            "status": status, "wall_s": round(wall, 1), **d}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 42])
    ap.add_argument("--player", default="9")
    ap.add_argument("--out", default="results")
    ap.add_argument("--cpu-limit", type=int, default=300)
    ap.add_argument("--timeout", type=int, default=400)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    args = ap.parse_args()

    scenarios = sorted(
        str(p) for p in Path("scenarios").rglob("*.json")
        if "invalid" not in p.name.lower()
    )
    jobs = [(sc, seed, args.player, args.cpu_limit, args.timeout)
            for sc in scenarios for seed in args.seeds]
    total = len(jobs)
    print(f"running {total} jobs on {args.workers} workers", flush=True)

    rows = []
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one, j): j for j in jobs}
        for fut in as_completed(futs):
            row = fut.result()
            rows.append(row)
            done += 1
            print(f"[{done}/{total}] {row['scenario']:<32} seed{row['seed']} "
                  f"score={row['score']} valid={row['valid']} {row['status']} "
                  f"wall={row['wall_s']}s", flush=True)

    rows.sort(key=lambda r: (r["scenario"], r["seed"]))
    cols = ["scenario", "seed", "score", "valid", "area", "perimeter", "gates",
            "second_gate_bonus", "note", "cpu_s", "wall_s", "status", "scenario_path"]
    with open(f"{args.out}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})
    with open(f"{args.out}.json", "w") as f:
        json.dump(rows, f, indent=2)

    valid = [r for r in rows if r["valid"]]
    print("\n=== SUMMARY ===")
    print(f"runs: {len(rows)}  valid: {len(valid)}  "
          f"total_score: {sum(r['score'] or 0 for r in rows):.0f}")
    print(f"wrote {args.out}.csv and {args.out}.json")


if __name__ == "__main__":
    main()
