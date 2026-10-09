"""Export the sample input of the Al Khaburah flood study.

Run from the full Madar Oman platform checkout (it uses the platform's own
readers), not from this repository:

    CLOUD_DATA_ROOT=~/cloud-data uv run python submission/madar-oman-poc/scripts/export_sample.py

It reads Sentinel-1 RTC (VV) from the Microsoft Planetary Computer for one
viewing geometry (descending, relative orbit 93), clips every pass to the study
grid (EPSG:32640, 20 m) and writes backscatter in dB x 100 as int16 GeoTIFFs,
plus the exclusion mask (slope over 5 degrees, or ESA WorldCover permanent
water). No credentials are needed. This is the exact scene list and these are
the exact parameters behind data/sample_input/.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import rasterio

from cloud.aoi import geometry, landcover
from cloud.aoi.components import flood
from cloud.aoi.components.oilspill import _passes, _read_pass, _search
from cloud.spill import detect

OUT = Path(__file__).resolve().parents[1] / "data" / "sample_input"
AREA = {"type": "Polygon", "coordinates": [[[56.98, 23.86], [57.16, 23.86], [57.16, 24.06],
                                             [56.98, 24.06], [56.98, 23.86]]]}
GEOMETRY = "descending_93"
START, END = dt.date(2021, 9, 1), dt.date(2021, 10, 31)
NODATA = -32768


def write(path: Path, array: np.ndarray, grid, dtype: str, nodata) -> None:
    with rasterio.open(path, "w", driver="GTiff", height=grid.height, width=grid.width, count=1,
                       dtype=dtype, crs=f"EPSG:{grid.epsg}", transform=grid.transform,
                       nodata=nodata, compress="deflate", predictor=2, tiled=True) as dst:
        dst.write(array.astype(dtype), 1)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    area = geometry.describe(AREA)
    grid = geometry.make_grid(area, 20)
    bbox = list(area["bbox"])
    groups = _passes(_search(bbox, START - dt.timedelta(days=flood.BASELINE_DAYS), END))
    manifest = {"crs": f"EPSG:{grid.epsg}", "resolution_m": grid.resolution, "bbox_wgs84": bbox,
                "geometry": GEOMETRY, "event_date": "2021-10-03", "encoding": "VV gamma0 in dB x 100, int16",
                "source": "Sentinel-1 RTC, Microsoft Planetary Computer (collection sentinel-1-rtc)",
                "licence": "Copernicus Sentinel data 2021 (free, full and open)", "passes": []}
    baseline_left = flood.MIN_BASELINE_PASSES + 2
    for group in groups:                                  # most recent first
        if flood.geometry_of(group) != GEOMETRY:
            continue
        when = group[0].datetime.date()
        role = "analysis" if when >= START else "baseline"
        if role == "baseline":
            if baseline_left == 0:
                continue
        vv = _read_pass(group, grid, bands=("vv",)).get("vv")
        if vv is None or not np.isfinite(vv).any():
            continue
        if role == "baseline":
            baseline_left -= 1
        db = detect.to_db(vv)
        packed = np.where(np.isfinite(db), np.clip(np.round(db * 100), -32000, 32000), NODATA)
        name = f"s1_vv_{when:%Y%m%d}_{role}.tif"
        write(OUT / name, packed, grid, "int16", NODATA)
        manifest["passes"].append({"file": name, "date": when.isoformat(), "role": role,
                                   "scenes": [item.id for item in group]})
        print(name)
    ctx = SimpleNamespace(area=area, warn=lambda *a: print("WARN", a[0]))
    excluded = flood._steep(ctx, grid) | flood._permanent_water(ctx, grid)
    write(OUT / "excluded_slope_or_permanent_water.tif", excluded, grid, "uint8", None)
    write(OUT / "inside_area.tif", grid.mask, grid, "uint8", None)
    manifest["passes"].sort(key=lambda p: p["date"])
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
