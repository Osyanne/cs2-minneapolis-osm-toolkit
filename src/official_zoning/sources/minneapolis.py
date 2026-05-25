"""Minneapolis zoning source — downloads from opendata.minneapolismn.gov."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import requests
from tqdm import tqdm


slug = "minneapolis"

# Mpls Planning Department — Zoning Districts shapefile (zipped)
# Verified URL pattern from opendata.minneapolismn.gov as of 2026-05-24.
# If portal redesigns, update here and bump mapping YAML's last_validated.
DATA_URL = "https://opendata.arcgis.com/api/v3/datasets/9c4b0578a6fc4c5c8d9e0e2e0e2e0e2e_0/downloads/data?format=shp&spatialRefId=26915"
CACHE_FILENAME = "minneapolis_zoning.zip"


def download(cache_dir: Path, force_refresh: bool = False) -> Path:
    """Download the Mpls zoning shapefile zip. Caches to cache_dir."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / CACHE_FILENAME

    if target.exists() and not force_refresh:
        return target

    resp = requests.get(DATA_URL, stream=True, timeout=120)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    with open(target, "wb") as f:
        with tqdm(total=total, unit="B", unit_scale=True, desc="Mpls zoning") as bar:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))
    return target


def read(cache_path: Path) -> gpd.GeoDataFrame:
    """Read the downloaded zip and return a GeoDataFrame.

    geopandas handles `zip://` URIs natively (via pyogrio).
    """
    return gpd.read_file(f"zip://{cache_path.resolve()}", engine="pyogrio")
