"""Pipeline orchestrator — reproject, spatial filter, map zoning codes to CS2 zones."""
from __future__ import annotations

import geopandas as gpd
from shapely.geometry import box

from official_zoning.mapping import Mapping


WGS84 = "EPSG:4326"


def process(
    gdf: gpd.GeoDataFrame,
    mapping: Mapping,
    bbox_wgs84: list[float],
) -> gpd.GeoDataFrame:
    """Reproject, spatial filter, and map zoning codes to CS2 zones.

    Args:
        gdf: Input GeoDataFrame (CRS as declared in mapping.crs_in).
        mapping: Per-city translation table.
        bbox_wgs84: [south, west, north, east] in WGS84 lat/lon for the city.

    Returns:
        GeoDataFrame in EPSG:4326 with `cs2_zone` column populated.
        Polygons outside bbox or with unmappable codes (under SKIP) are dropped.
    """
    # 1. Reproject to WGS84
    reprojected = gdf.to_crs(WGS84)

    # 2. Spatial filter by bbox
    south, west, north, east = bbox_wgs84
    bbox_geom = box(west, south, east, north)
    in_bbox = reprojected[reprojected.geometry.intersects(bbox_geom)].copy()

    # 3. Translate zoning codes via mapping
    in_bbox["cs2_zone"] = in_bbox[mapping.source_field].apply(mapping.translate)

    # 4. Drop rows whose zone is None (unmapped + SKIP strategy)
    return in_bbox[in_bbox["cs2_zone"].notna()].copy()
