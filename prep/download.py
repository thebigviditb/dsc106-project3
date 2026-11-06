"""Mirror the CMIP6 zarr stores we need to data/raw/ with curl (retries + resume),
so a dropped connection doesn't throw away a 100 MB chunk.

Run from the project root:  .venv/bin/python prep/download.py [experiment ...]
"""
import json
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
BUCKET = "https://storage.googleapis.com/cmip6/CMIP6"
STORES = {
    "historical": "CMIP/NOAA-GFDL/GFDL-ESM4/historical/r1i1p1f1/Amon/tas/gr1/v20190726",
    "ssp126": "ScenarioMIP/NOAA-GFDL/GFDL-ESM4/ssp126/r1i1p1f1/Amon/tas/gr1/v20180701",
    "ssp245": "ScenarioMIP/NOAA-GFDL/GFDL-ESM4/ssp245/r1i1p1f1/Amon/tas/gr1/v20180701",
    "ssp585": "ScenarioMIP/NOAA-GFDL/GFDL-ESM4/ssp585/r1i1p1f1/Amon/tas/gr1/v20180701",
    "sftlf": "ScenarioMIP/NOAA-GFDL/GFDL-ESM4/ssp370/r1i1p1f1/fx/sftlf/gr1/v20180701",
}


def fetch(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    for _ in range(20):
        r = subprocess.run(["curl", "-sfL", "--retry", "10", "--retry-all-errors", "-C", "-",
                            "-o", str(part), url])
        if r.returncode == 0:
            part.rename(dest)
            return
        if r.returncode == 33:  # server refused resume; start over
            part.unlink(missing_ok=True)
        if r.returncode == 22:  # HTTP error: 416 = already complete, 404 = chunk not stored
            if part.exists() and part.stat().st_size > 0:
                part.rename(dest)
            return
    raise RuntimeError(f"failed: {url}")


def mirror(name):
    rel = STORES[name]
    base, local = f"{BUCKET}/{rel}", RAW / name
    meta_path = local / ".zmetadata"
    if not meta_path.exists():
        fetch(f"{base}/.zmetadata", meta_path)
    meta = json.loads(meta_path.read_text())["metadata"]
    keys = [k for k in meta if k.endswith((".zgroup", ".zattrs", ".zarray"))]
    for k in meta:
        if k.endswith(".zarray"):
            arr = meta[k]
            var = k[: -len("/.zarray")]
            counts = [math.ceil(s / c) for s, c in zip(arr["shape"], arr["chunks"])] or [1]
            sep = arr.get("dimension_separator", ".")
            idx = [[]]
            for n in counts:
                idx = [i + [j] for i in idx for j in range(n)]
            keys += [f"{var}/{sep.join(map(str, i)) or '0'}" for i in idx]
    todo = [k for k in keys if not (local / k).exists()]
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda k: fetch(f"{base}/{k}", local / k), todo))
    print(f"{name}: {len(keys)} files ok", flush=True)


if __name__ == "__main__":
    names = sys.argv[1:] or list(STORES)
    with ThreadPoolExecutor(len(names)) as pool:
        list(pool.map(mirror, names))
