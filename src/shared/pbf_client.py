"""
pbf_client.py
=============
Cliente de extracción PBF con API compatible con overpass_client.

Lee un .osm.pbf con pyosmium 4.x (`osmium.FileProcessor`), aplica FilterSpec,
y re-emite resultados en forma Overpass-compatible (dict con clave 'elements',
cada elemento con 'type', 'id', 'tags', 'geometry'/'members'/'lat,lon').

Diseñado como drop-in replacement de overpass_client para los extractores
existentes: la única diferencia es que toma FilterSpec en vez de QL string.

Uso:
    from shared.pbf_client import query
    data = query(pbf_path, bbox, filter_spec, label="apartments")
    # data["elements"] es lista con shape Overpass

Conversión a Overpass shape:
- way:      {"type": "way", "id": N, "tags": {...}, "geometry": [{"lat", "lon"}, ...]}
- node:     {"type": "node", "id": N, "tags": {...}, "lat": ..., "lon": ...}
- relation: {"type": "relation", "id": N, "tags": {...},
             "members": [{"role": "outer", "geometry": [{"lat", "lon"}, ...]}]}
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import osmium
from shapely.geometry import Point as _ShapelyPoint
from shapely.strtree import STRtree

from shared.pbf_filters import FilterSpec


def _osmium_tags(osm_obj: Any) -> dict[str, str]:
    """
    Convert a pyosmium TagList to a plain dict of str→str.

    pyosmium 4.x exposes tags as an iterable of (key, value) pairs via
    `obj.tags`. Empty TagList returns empty dict, never None.
    """
    return {tag.k: tag.v for tag in osm_obj.tags}


def _in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    """Bbox membership check. bbox is (south, west, north, east) inclusive."""
    south, west, north, east = bbox
    return south <= lat <= north and west <= lon <= east


def _node_to_overpass(node: Any) -> dict[str, Any] | None:
    """
    Convert an osmium.osm.Node to Overpass-shape dict.

    Returns None if the node has no valid location.
    """
    if not node.location.valid():
        return None
    return {
        "type": "node",
        "id": node.id,
        "tags": _osmium_tags(node),
        "lat": node.location.lat,
        "lon": node.location.lon,
    }


def _way_to_overpass(way: Any) -> dict[str, Any] | None:
    """
    Convert an osmium.osm.Way to Overpass-shape dict.

    Requires the FileProcessor was built with .with_locations() so that
    way.nodes have resolved coordinates. Returns None if locations are
    unresolved or empty.
    """
    try:
        coords: list[dict[str, float]] = []
        for noderef in way.nodes:
            if not noderef.location.valid():
                return None
            coords.append({"lat": noderef.location.lat, "lon": noderef.location.lon})
    except osmium.InvalidLocationError:
        return None
    if len(coords) < 2:
        return None
    return {
        "type": "way",
        "id": way.id,
        "tags": _osmium_tags(way),
        "geometry": coords,
    }


def _area_to_overpass(area: Any) -> dict[str, Any] | None:
    """
    Convert an osmium.osm.Area to Overpass-shape relation dict.

    Areas come from closed ways or multipolygon relations. We extract the
    outer ring (largest if multiple) and emit it as a single 'outer' member,
    matching how extract.py.coords_from_relation consumes relations.
    """
    try:
        # outer_rings() yields lists of NodeRefs for each outer ring
        outers = list(area.outer_rings())
    except (osmium.InvalidLocationError, RuntimeError):
        return None
    if not outers:
        return None

    # Pick the largest outer ring by node count (proxy for area)
    largest = max(outers, key=lambda ring: len(list(ring)))
    coords: list[dict[str, float]] = []
    for noderef in largest:
        if not noderef.location.valid():
            return None
        coords.append({"lat": noderef.location.lat, "lon": noderef.location.lon})
    if len(coords) < 3:
        return None

    # Areas in osmium have an orig_id() method that returns the underlying
    # way or relation ID (with sign indicating which). For relations from
    # multipolygons, we want the relation ID; for closed ways, the way ID.
    # area.id is the synthetic area ID; orig_id() is the source object's ID.
    rel_id = area.orig_id() if hasattr(area, "orig_id") else area.id

    return {
        "type": "relation",
        "id": rel_id,
        "tags": _osmium_tags(area),
        "members": [{
            "role": "outer",
            "type": "way",
            "geometry": coords,
        }],
    }


# Aproximación métrica: 1 grado de latitud ≈ 111,000 m. Aceptable para
# distancias pequeñas (<100m) y latitudes no polares.
_DEG_PER_METER = 1.0 / 111000.0


def _element_to_points(el: dict[str, Any]) -> list[_ShapelyPoint]:
    """Convierte un elemento Overpass-shape a lista de Points shapely."""
    if el["type"] == "node":
        return [_ShapelyPoint(el["lon"], el["lat"])]
    if el["type"] == "way":
        return [_ShapelyPoint(pt["lon"], pt["lat"]) for pt in el.get("geometry", [])]
    if el["type"] == "relation":
        pts: list[_ShapelyPoint] = []
        for m in el.get("members", []):
            for pt in m.get("geometry", []):
                pts.append(_ShapelyPoint(pt["lon"], pt["lat"]))
        return pts
    return []


def _apply_spatial_join(
    targets: list[dict[str, Any]],
    anchors: list[dict[str, Any]],
    buffer_m: float,
) -> list[dict[str, Any]]:
    """
    Devuelve targets con al menos un punto a buffer_m metros o menos de algún
    punto anchor. Replica el patrón Overpass `(nodes A)->.x; way(around.x:N);`.
    """
    # NOTE: buffer_m is converted to degrees using 1° ≈ 111km. This is exact
    # for latitude but overstates longitude at non-equatorial latitudes
    # (e.g., at 45°N, 1° lon ≈ 79km, so the buffer in lon is ~40% larger
    # than intended). Acceptable for 5–10m "around" semantics in our use
    # cases; revisit if larger buffers or polar regions are added.
    if not anchors or not targets:
        return []

    anchor_points: list[_ShapelyPoint] = []
    for a in anchors:
        anchor_points.extend(_element_to_points(a))
    if not anchor_points:
        return []

    tree = STRtree(anchor_points)
    buffer_deg = buffer_m * _DEG_PER_METER

    kept: list[dict[str, Any]] = []
    for t in targets:
        target_points = _element_to_points(t)
        matched = False
        for tp in target_points:
            candidates_idx = tree.query(tp.buffer(buffer_deg))
            for idx in candidates_idx:
                ap = anchor_points[idx]
                if tp.distance(ap) <= buffer_deg:
                    matched = True
                    break
            if matched:
                break
        if matched:
            kept.append(t)
    return kept


def _classify_geom_type(obj: Any) -> str | None:
    """Returns 'node', 'way', 'relation', or None (for area, which is handled separately)."""
    if obj.is_node():
        return "node"
    if obj.is_way():
        return "way"
    if obj.is_relation():
        return "relation"
    return None


def query(
    pbf_path: Path,
    bbox: tuple[float, float, float, float],
    filter_spec: FilterSpec,
    label: str = "query",
) -> dict[str, Any]:
    """
    Execute FilterSpec against a .osm.pbf and return Overpass-shape dict.

    Streams the file once via osmium.FileProcessor with locations resolved,
    classifies each object, applies clause matchers, emits Overpass-compatible
    JSON. Spatial joins applied as post-processing.

    Args:
        pbf_path: Path al .osm.pbf (debe existir).
        bbox: (south, west, north, east) en grados decimales.
        filter_spec: Estructura con clauses + spatial_joins opcionales.
        label: Etiqueta para logs.

    Returns:
        {"elements": [...]} con shape Overpass.

    Raises:
        FileNotFoundError: si pbf_path no existe.
    """
    pbf_path = Path(pbf_path)
    if not pbf_path.exists():
        raise FileNotFoundError(f"PBF no encontrado: {pbf_path}")

    print(f"        [pbf:{label}] reading {pbf_path.name} bbox={bbox}", flush=True)
    start = time.monotonic()

    # Decide if we need areas (when any clause requests relations OR ways
    # that could be closed polygons)
    needs_areas = any(
        "relation" in c.geom_types for c in filter_spec.clauses.values()
    )

    # Build FileProcessor — always need locations for way geometries
    fp = osmium.FileProcessor(str(pbf_path)).with_locations()
    if needs_areas:
        fp = fp.with_areas()

    elements_by_clause: dict[str, list[dict[str, Any]]] = {
        name: [] for name in filter_spec.clauses
    }
    seen: set[tuple[str, int]] = set()
    all_elements: list[dict[str, Any]] = []

    # IMPORTANT — pyosmium 4.x object lifetime:
    # Each `obj` is a transient view into the file reader. Once we advance the
    # iterator (`continue` or next loop), `obj` becomes invalid and accessing its
    # attributes raises RuntimeError. Therefore: extract everything we need into
    # plain Python dicts BEFORE the loop advances. The `_*_to_overpass()` helpers
    # fully materialize their output, and `all_elements`/`elements_by_clause` only
    # store these materialized dicts — never references to `obj` itself.
    for obj in fp:
        # Bbox check + classification varies by type
        if obj.is_node():
            if not obj.location.valid():
                continue
            if not _in_bbox(obj.location.lat, obj.location.lon, bbox):
                continue
            geom_type = "node"
            element = _node_to_overpass(obj)
        elif obj.is_way():
            # Bbox check: keep way if ANY node is inside (handles boundary-crossing ways)
            try:
                any_inside = False
                for noderef in obj.nodes:
                    if not noderef.location.valid():
                        continue
                    if _in_bbox(noderef.location.lat, noderef.location.lon, bbox):
                        any_inside = True
                        break
                if not any_inside:
                    continue
            except osmium.InvalidLocationError:
                continue
            geom_type = "way"
            element = _way_to_overpass(obj)
        elif hasattr(obj, "from_way"):
            # Bbox check: keep area if ANY point of ANY outer ring is inside bbox
            try:
                outers = list(obj.outer_rings())
                if not outers:
                    continue
                any_inside = False
                for ring in outers:
                    for noderef in ring:
                        if not noderef.location.valid():
                            continue
                        if _in_bbox(noderef.location.lat, noderef.location.lon, bbox):
                            any_inside = True
                            break
                    if any_inside:
                        break
                if not any_inside:
                    continue
            except (osmium.InvalidLocationError, RuntimeError):
                continue
            # Areas can satisfy "relation" or "way" geom types depending on source.
            # Treat all areas as relations for clause matching to support polygon shapes.
            geom_type = "relation"
            element = _area_to_overpass(obj)
        else:
            continue

        if element is None:
            continue

        # Match against each clause; collect into all matching clauses
        tags = element["tags"]
        matching_clauses = [
            name for name, clause in filter_spec.clauses.items()
            if clause.matches(geom_type, tags)
        ]
        if not matching_clauses:
            continue

        key = (element["type"], element["id"])
        for clause_name in matching_clauses:
            elements_by_clause[clause_name].append(element)
        if key not in seen:
            seen.add(key)
            all_elements.append(element)

    # Apply spatial joins: filter target_clause in-place
    for sj in filter_spec.spatial_joins:
        targets = elements_by_clause[sj.target_clause]
        anchors = elements_by_clause[sj.anchor_clause]
        kept = _apply_spatial_join(targets, anchors, sj.buffer_m)
        kept_ids = {(e["type"], e["id"]) for e in kept}
        target_ids = {(t["type"], t["id"]) for t in targets}
        # Remove from all_elements those targets that did NOT survive
        # SEMANTIC NOTE: if an element matched BOTH the target_clause and another
        # clause, dropping it via spatial join also removes it from all_elements
        # (the other-clause membership is lost). This matches our use case — the
        # only spatial-join target (`mixed_buildings`) doesn't overlap with other
        # clauses. If multi-clause matching with spatial joins is ever needed,
        # this filter needs revision.
        all_elements = [
            e for e in all_elements
            if (e["type"], e["id"]) not in target_ids
            or (e["type"], e["id"]) in kept_ids
        ]
        elements_by_clause[sj.target_clause] = kept

    elapsed = time.monotonic() - start
    print(
        f"        [pbf:{label}] OK {len(all_elements)} elementos en {elapsed:.1f}s",
        flush=True,
    )
    return {"elements": all_elements}


def query_with_retry(
    pbf_path: Path,
    bbox: tuple[float, float, float, float],
    filter_spec: FilterSpec,
    label: str = "query",
) -> dict[str, Any]:
    """
    Drop-in shim matching overpass_client.query_with_retry signature shape
    but operating on a local PBF. No real "retry" — local file ops don't
    fail by network. Raises FileNotFoundError if pbf_path missing.
    """
    return query(pbf_path, bbox, filter_spec, label)


def query_batch(
    pbf_path: Path,
    bbox: tuple[float, float, float, float],
    filter_specs: dict[str, FilterSpec],
    label: str = "batch",
) -> dict[str, dict[str, Any]]:
    """
    Execute MULTIPLE FilterSpecs against a .osm.pbf in a SINGLE pass.

    Streams the file ONE time and applies all filter_specs in parallel during
    the iteration. Much faster than calling query() N times because the
    expensive part (streaming the file, resolving locations, building areas)
    happens once instead of N times.

    Args:
        pbf_path: Path al .osm.pbf (debe existir).
        bbox: (south, west, north, east) en grados decimales.
        filter_specs: Dict mapping spec name → FilterSpec. Output preserves keys.
        label: Etiqueta para logs.

    Returns:
        Dict mapping each spec name to {"elements": [...]} (same shape per
        spec as query() output).

    Raises:
        FileNotFoundError: si pbf_path no existe.
    """
    pbf_path = Path(pbf_path)
    if not pbf_path.exists():
        raise FileNotFoundError(f"PBF no encontrado: {pbf_path}")

    if not filter_specs:
        return {}

    print(
        f"        [pbf:{label}] BATCH reading {pbf_path.name} bbox={bbox} "
        f"({len(filter_specs)} specs)",
        flush=True,
    )
    start = time.monotonic()

    # Determine if we need areas — any spec requests relations
    needs_areas = any(
        "relation" in c.geom_types
        for spec in filter_specs.values()
        for c in spec.clauses.values()
    )

    fp = osmium.FileProcessor(str(pbf_path)).with_locations()
    if needs_areas:
        fp = fp.with_areas()

    # Per-spec state: elements per clause, deduped set, all_elements list
    state: dict[str, dict[str, Any]] = {
        spec_name: {
            "elements_by_clause": {name: [] for name in spec.clauses},
            "seen": set(),
            "all_elements": [],
        }
        for spec_name, spec in filter_specs.items()
    }

    # IMPORTANT — pyosmium 4.x object lifetime: same invariant as query().
    # Each `obj` is a transient view. Extract everything into plain dicts
    # before the iterator advances.
    for obj in fp:
        # Classify + bbox-check ONCE for the object
        if obj.is_node():
            if not obj.location.valid():
                continue
            if not _in_bbox(obj.location.lat, obj.location.lon, bbox):
                continue
            geom_type = "node"
            element = _node_to_overpass(obj)
        elif obj.is_way():
            try:
                any_inside = False
                for noderef in obj.nodes:
                    if not noderef.location.valid():
                        continue
                    if _in_bbox(noderef.location.lat, noderef.location.lon, bbox):
                        any_inside = True
                        break
                if not any_inside:
                    continue
            except osmium.InvalidLocationError:
                continue
            geom_type = "way"
            element = _way_to_overpass(obj)
        elif hasattr(obj, "from_way"):
            try:
                outers = list(obj.outer_rings())
                if not outers:
                    continue
                any_inside = False
                for ring in outers:
                    for noderef in ring:
                        if not noderef.location.valid():
                            continue
                        if _in_bbox(noderef.location.lat, noderef.location.lon, bbox):
                            any_inside = True
                            break
                    if any_inside:
                        break
                if not any_inside:
                    continue
            except (osmium.InvalidLocationError, RuntimeError):
                continue
            geom_type = "relation"
            element = _area_to_overpass(obj)
        else:
            continue

        if element is None:
            continue

        tags = element["tags"]  # already extracted
        key = (element["type"], element["id"])

        # Match against EVERY spec's clauses
        for spec_name, spec in filter_specs.items():
            matching_clauses = [
                cname for cname, clause in spec.clauses.items()
                if clause.matches(geom_type, tags)
            ]
            if not matching_clauses:
                continue
            for cname in matching_clauses:
                state[spec_name]["elements_by_clause"][cname].append(element)
            if key not in state[spec_name]["seen"]:
                state[spec_name]["seen"].add(key)
                state[spec_name]["all_elements"].append(element)

    # Apply spatial joins per spec
    for spec_name, spec in filter_specs.items():
        s = state[spec_name]
        for sj in spec.spatial_joins:
            targets = s["elements_by_clause"][sj.target_clause]
            anchors = s["elements_by_clause"][sj.anchor_clause]
            kept = _apply_spatial_join(targets, anchors, sj.buffer_m)
            kept_ids = {(e["type"], e["id"]) for e in kept}
            target_ids = {(t["type"], t["id"]) for t in targets}
            s["all_elements"] = [
                e for e in s["all_elements"]
                if (e["type"], e["id"]) not in target_ids
                or (e["type"], e["id"]) in kept_ids
            ]
            s["elements_by_clause"][sj.target_clause] = kept

    result = {
        spec_name: {"elements": s["all_elements"]}
        for spec_name, s in state.items()
    }

    elapsed = time.monotonic() - start
    total_elements = sum(len(r["elements"]) for r in result.values())
    print(
        f"        [pbf:{label}] BATCH OK {total_elements} total elementos "
        f"across {len(filter_specs)} specs en {elapsed:.1f}s",
        flush=True,
    )
    return result
