#!/usr/bin/env python3
"""Benchmark player9 vs player10 across all scenarios (seed 42), capturing
score, area, perimeter, winning method, and the delta (p9 - p10).

Runs both players in parallel subprocesses per scenario. Writes a CSV + a
ranked gap report (rooms where p10 beats p9, worst first) to stdout.
"""
import csv
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


def parse(out):
    d = {"note": "", "score": None, "area": None, "perimeter": None, "valid": None}
    for line in out.splitlines():
        if line.startswith("note:"):
            d["note"] = line.split("note:", 1)[1].strip()[:60]
        elif line.startswith("valid:"):
            d["valid"] = line.split("valid:", 1)[1].strip().startswith("True")
        elif line.startswith("area="):
            m = re.search(r"area=([\d.]+) perimeter=([\d.]+)", line)
            if m:
                d["area"] = float(m.group(1))
                d["perimeter"] = float(m.group(2))
        elif line.startswith("SCORE:"):
            d["score"] = float(line.split("SCORE:", 1)[1].strip())
    return d


def run(player, scenario, seed=42, cpu=300, timeout=360):
    try:
        r = subprocess.run(
            ["uv", "run", "main.py", "--player", str(player),
             "--scenario", scenario, "--seed", str(seed), "--cpu-limit", str(cpu)],
            capture_output=True, text=True, timeout=timeout,
        )
        return parse(r.stdout + "\n" + r.stderr)
    except subprocess.TimeoutExpired:
        return {"note": "TIMEOUT", "score": None, "area": None,
                "perimeter": None, "valid": None}


def run_pair(scenario):
    t0 = time.time()
    p9 = run(9, scenario)
    p10 = run(10, scenario)
    return scenario, p9, p10, time.time() - t0


def main():
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    scenarios = sorted(
        str(p) for p in Path("scenarios").rglob("*.json")
        if "invalid" not in p.name.lower()
    )
    if only:
        scenarios = [s for s in scenarios if any(o in s for o in only)]
    rows = []
    workers = 2
    print(f"benchmarking {len(scenarios)} scenarios, p9 vs p10, {workers} workers",
          flush=True)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(run_pair, s): s for s in scenarios}
        done = 0
        for fut in as_completed(futs):
            sc, p9, p10, dt = fut.result()
            done += 1
            s9 = p9["score"] if p9["score"] is not None else 0.0
            s10 = p10["score"] if p10["score"] is not None else 0.0
            delta = s9 - s10
            rows.append({
                "scenario": Path(sc).stem, "path": sc,
                "p9_score": s9, "p10_score": s10, "delta": delta,
                "p9_area": p9["area"], "p10_area": p10["area"],
                "p9_note": p9["note"], "p10_note": p10["note"],
            })
            flag = "WIN" if delta >= -1 else ("TIE" if abs(delta) < 1 else "LOSS")
            print(f"[{done}/{len(scenarios)}] {Path(sc).stem:<40} "
                  f"p9={s9:>10.1f} p10={s10:>10.1f} d={delta:>+10.1f} {flag} "
                  f"({dt:.0f}s)", flush=True)

    rows.sort(key=lambda r: r["delta"])
    with open("bench_p9_p10.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    wins = sum(1 for r in rows if r["delta"] >= -1)
    losses = [r for r in rows if r["delta"] < -1]
    print("\n=== SUMMARY ===")
    print(f"scenarios: {len(rows)}  p9>=p10: {wins}  p9<p10: {len(losses)}")
    print(f"total p9: {sum(r['p9_score'] for r in rows):.0f}  "
          f"total p10: {sum(r['p10_score'] for r in rows):.0f}")
    print("\n=== ROOMS WHERE P10 BEATS P9 (worst first) ===")
    for r in losses:
        print(f"  {r['scenario']:<40} p9={r['p9_score']:>9.0f} "
              f"p10={r['p10_score']:>9.0f} gap={r['delta']:>+9.0f}  "
              f"p9:[{r['p9_note'][:28]}] p10:[{r['p10_note'][:28]}]")


if __name__ == "__main__":
    main()
