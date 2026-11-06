"""Pull CMIP6 GFDL-ESM4 near-surface air temperature (tas) from the public
Google Cloud bucket, make the six exploratory graphs, and export the coarsened
JSON the D3 page loads.

Run from the project root:  .venv/bin/python prep/prepare_data.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
FIGS = ROOT / "figures"
OUT = ROOT / "docs" / "data"
for d in (CACHE, FIGS, OUT):
    d.mkdir(parents=True, exist_ok=True)

# Local mirrors made by prep/download.py (GFDL-ESM4 r1i1p1f1 from the public CMIP6 bucket).
RAW = ROOT / "data" / "raw"
STORES = {e: RAW / e for e in ("historical", "ssp126", "ssp245", "ssp585")}
LAND_MASK = RAW / "sftlf"

SCENARIOS = ["ssp126", "ssp245", "ssp585"]
LABELS = {"ssp126": "Low emissions (SSP1-2.6)",
          "ssp245": "Middle (SSP2-4.5)",
          "ssp585": "High emissions (SSP5-8.5)"}
COLORS = {"ssp126": "#2a9d8f", "ssp245": "#e9a23b", "ssp585": "#c0392b", "historical": "#444444"}


def annual_tas(exp):
    """Annual-mean tas in °C on the native 1° x 1.25° grid, cached locally."""
    path = CACHE / f"tas_annual_{exp}.npz"
    if path.exists():
        z = np.load(path)
        return xr.DataArray(z["tas"], dims=("year", "lat", "lon"),
                            coords={"year": z["year"], "lat": z["lat"], "lon": z["lon"]}, name="tas")
    print(f"downloading {exp} ...", flush=True)
    ds = xr.open_zarr(STORES[exp], consolidated=True)
    raw = ds["tas"].load()  # fetch each chunk once, then average in memory
    tas = raw.groupby("time.year").mean("time") - 273.15
    tas = tas.drop_vars([c for c in tas.coords if c not in ("year", "lat", "lon")])
    tas = tas.load()
    if exp != "historical":
        tas = tas.sel(year=slice(2015, 2099))  # whole 5-year bins only
    np.savez(path, tas=tas.values.astype("float32"), year=tas.year.values,
             lat=tas.lat.values, lon=tas.lon.values)
    return tas


def weighted_mean(da, mask=None):
    w = np.cos(np.deg2rad(da.lat)) * xr.ones_like(da.isel(year=0, drop=True))
    if mask is not None:
        w = w.where(mask)
    return da.weighted(w.fillna(0)).mean(("lat", "lon"))


import sys
if len(sys.argv) > 1:  # download-only mode: prepare_data.py <experiment>
    annual_tas(sys.argv[1])
    sys.exit(0)

hist = annual_tas("historical")
runs = {s: xr.concat([hist, annual_tas(s)], dim="year") for s in SCENARIOS}

# Warming relative to pre-industrial (1850-1900), per grid cell.
baseline = hist.sel(year=slice(1850, 1900)).mean("year")
anom = {s: runs[s] - baseline for s in SCENARIOS}
glob = {s: weighted_mean(anom[s]) for s in SCENARIOS}

land = xr.open_zarr(LAND_MASK, consolidated=True)["sftlf"].load()
land = land.drop_vars([c for c in land.coords if c not in ("lat", "lon")]) > 50

plt.rcParams.update({"figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False,
                     "font.size": 10})


def rolling(da, n=10):
    return da.rolling(year=n, center=True, min_periods=n // 2).mean()


# Graph 1: global mean warming, one line per scenario
fig, ax = plt.subplots(figsize=(8, 4.5))
for s in SCENARIOS:
    g = glob[s]
    ax.plot(g.year.where(g.year >= 2014, drop=True), g.where(g.year >= 2014, drop=True),
            color=COLORS[s], label=LABELS[s], lw=1.6)
g = glob["ssp245"].sel(year=slice(1850, 2014))
ax.plot(g.year, g, color=COLORS["historical"], label="Historical", lw=1.6)
ax.axhline(0, color="#999", lw=0.8)
ax.set(title="1. Global mean warming since 1850–1900 (GFDL-ESM4)", xlabel="Year",
       ylabel="Warming (°C)")
ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(FIGS / "1_global_mean_by_scenario.png"); plt.close(fig)

# Graph 2: map of end-of-century warming, high emissions
recent = hist.sel(year=slice(1995, 2014)).mean("year")
change = {s: runs[s].sel(year=slice(2081, 2099)).mean("year") - recent for s in SCENARIOS}
fig, ax = plt.subplots(figsize=(9, 4.6))
lon180 = ((change["ssp585"].lon + 180) % 360) - 180
c585 = change["ssp585"].assign_coords(lon=lon180).sortby("lon")
pm = ax.pcolormesh(c585.lon, c585.lat, c585, cmap="RdBu_r", vmin=-12, vmax=12, shading="auto")
ax.contour(land.assign_coords(lon=((land.lon + 180) % 360) - 180).sortby("lon").lon,
           land.lat, land.assign_coords(lon=((land.lon + 180) % 360) - 180).sortby("lon"),
           levels=[0.5], colors="k", linewidths=0.4)
fig.colorbar(pm, ax=ax, label="Warming (°C)", shrink=0.85)
ax.set(title="2. Warming by 2081–2099 vs 1995–2014, high emissions (SSP5-8.5)",
       xlabel="Longitude", ylabel="Latitude")
fig.tight_layout(); fig.savefig(FIGS / "2_end_of_century_map.png"); plt.close(fig)

# Graph 3: warming by latitude, as a multiple of the global mean
fig, ax = plt.subplots(figsize=(8, 4.5))
for s in SCENARIOS:
    zonal = change[s].mean("lon")
    gm = float(weighted_mean(change[s].expand_dims(year=[0])).squeeze())
    ax.plot(zonal.lat, zonal / gm, color=COLORS[s], label=LABELS[s], lw=1.6)
ax.axhline(1, color="#999", lw=0.8, ls="--")
ax.text(-88, 1.08, "global average", color="#777", fontsize=8)
ax.set(title="3. Warming by latitude, as a multiple of the global average (2081–2099 vs 1995–2014)",
       xlabel="Latitude (°S ← → °N)", ylabel="× global mean warming")
ax.title.set_fontsize(9.5)
ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(FIGS / "3_warming_by_latitude.png"); plt.close(fig)

# Graph 4: land vs ocean warming over time
fig, ax = plt.subplots(figsize=(8, 4.5))
for s in ["ssp245", "ssp585"]:
    ax.plot(anom[s].year, rolling(weighted_mean(anom[s], land)), color=COLORS[s], lw=1.8,
            label=f"Land, {LABELS[s]}")
    ax.plot(anom[s].year, rolling(weighted_mean(anom[s], ~land)), color=COLORS[s], lw=1.8,
            ls="--", label=f"Ocean, {LABELS[s]}")
ax.axhline(0, color="#999", lw=0.8)
ax.set(title="4. Land warms faster than ocean (10-year rolling mean)", xlabel="Year",
       ylabel="Warming since 1850–1900 (°C)")
ax.legend(frameon=False, fontsize=8)
fig.tight_layout(); fig.savefig(FIGS / "4_land_vs_ocean.png"); plt.close(fig)

# Graph 5: latitude x year heatmap (Hovmöller), high emissions
zon = rolling(anom["ssp585"].mean("lon"))
fig, ax = plt.subplots(figsize=(9, 4.6))
pm = ax.pcolormesh(zon.year, zon.lat, zon.T, cmap="RdBu_r", vmin=-12, vmax=12, shading="auto")
fig.colorbar(pm, ax=ax, label="Warming since 1850–1900 (°C)", shrink=0.85)
ax.set(title="5. When each latitude warms: zonal mean, SSP5-8.5 (10-year rolling)",
       xlabel="Year", ylabel="Latitude")
fig.tight_layout(); fig.savefig(FIGS / "5_hovmoller.png"); plt.close(fig)

# Graph 6: a few places vs the global mean
CITIES = {"San Diego": (32.7, -117.2), "Phoenix": (33.4, -112.1),
          "Mumbai": (19.1, 72.9), "Svalbard": (78.2, 15.6)}
CITY_COLORS = ["#1f77b4", "#ff7f0e", "#9467bd", "#17becf"]
fig, ax = plt.subplots(figsize=(8, 4.5))
for (name, (la, lo)), col in zip(CITIES.items(), CITY_COLORS):
    series = anom["ssp585"].sel(lat=la, lon=lo % 360, method="nearest")
    ax.plot(series.year, rolling(series), color=col, lw=1.6, label=name)
ax.plot(glob["ssp585"].year, rolling(glob["ssp585"]), color="k", lw=2.2, ls="--",
        label="Global mean")
ax.axhline(0, color="#999", lw=0.8)
ax.set(title="6. Your place is not the global average (SSP5-8.5, 10-year rolling)",
       xlabel="Year", ylabel="Warming since 1850–1900 (°C)")
ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(FIGS / "6_cities_vs_global.png"); plt.close(fig)

# Export for D3: 5° grid (5 lat x 4 lon native cells), 5-year means, three scenarios.
def coarse(da):
    return da.coarsen(lat=5, lon=4).mean()

def five_year(da):
    return da.coarsen(year=5).mean().assign_coords(year=da.year.values[::5])

out = {"model": "GFDL-ESM4 r1i1p1f1", "variable": "tas (near-surface air temperature)",
       "baseline": "1850-1900 mean", "units": "°C", "scenarios": LABELS}
grids, global_series = {}, {}
for s in SCENARIOS:
    g = five_year(coarse(anom[s]))
    grids[s] = np.round(g.values.astype("float64"), 2).reshape(g.sizes["year"], -1).tolist()
    global_series[s] = np.round(five_year(glob[s]).values.astype("float64"), 2).tolist()
out["years"] = [int(y) for y in g.year.values]
out["lats"] = [round(float(v), 2) for v in g.lat.values]
out["lons"] = [round(float(((v + 180) % 360) - 180), 2) for v in g.lon.values]
out["global"] = global_series
out["grid"] = grids  # grid[scenario][yearIndex][latIndex * nLon + lonIndex]
(OUT / "warming.json").write_text(json.dumps(out, separators=(",", ":")))

print("figures ->", FIGS)
print("json    ->", OUT / "warming.json", f"{(OUT / 'warming.json').stat().st_size / 1e6:.1f} MB")
for s in SCENARIOS:
    print(s, "global 2081-2099 vs 1850-1900:",
          round(float(glob[s].sel(year=slice(2081, 2099)).mean()), 2), "°C")
