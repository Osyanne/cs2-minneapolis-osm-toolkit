"""Tests del pipeline services.extract (Sesión 3)."""
import sys, os, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


def _make_fixture_response():
    """Mock de respuesta Overpass con 1 hospital way, 1 clinic node, 1 park way,
    1 library con name, 1 museum sin name (que debe rechazarse), 1 restaurant
    (irrelevante, debe rechazarse)."""
    return {
        "elements": [
            {
                "type": "way", "id": 1,
                "tags": {"amenity": "hospital", "name": "Hennepin Healthcare HCMC"},
                "geometry": [
                    {"lat": 44.97, "lon": -93.26},
                    {"lat": 44.97, "lon": -93.25},
                    {"lat": 44.98, "lon": -93.25},
                    {"lat": 44.98, "lon": -93.26},
                    {"lat": 44.97, "lon": -93.26},
                ],
            },
            {
                "type": "node", "id": 2,
                "tags": {"amenity": "clinic", "name": "MinuteClinic"},
                "lat": 44.95, "lon": -93.28,
            },
            {
                "type": "way", "id": 3,
                "tags": {"leisure": "park", "name": "Minnehaha Park"},
                "geometry": [
                    {"lat": 44.91, "lon": -93.20},
                    {"lat": 44.91, "lon": -93.21},
                    {"lat": 44.92, "lon": -93.21},
                    {"lat": 44.92, "lon": -93.20},
                    {"lat": 44.91, "lon": -93.20},
                ],
            },
            {
                "type": "way", "id": 4,
                "tags": {"amenity": "library", "name": "Hennepin Library Central"},
                "geometry": [
                    {"lat": 44.97, "lon": -93.27},
                    {"lat": 44.97, "lon": -93.26},
                    {"lat": 44.98, "lon": -93.26},
                    {"lat": 44.98, "lon": -93.27},
                    {"lat": 44.97, "lon": -93.27},
                ],
            },
            # Museum sin name — debe rechazarse
            {"type": "node", "id": 5, "tags": {"tourism": "museum"}, "lat": 1, "lon": 1},
            # Restaurant — irrelevante
            {"type": "node", "id": 6, "tags": {"amenity": "restaurant"}, "lat": 1, "lon": 1},
        ]
    }


def test_extract_writes_two_data_objects(tmp_path, monkeypatch):
    from services import extract
    monkeypatch.setattr(extract, "query_with_retry",
                        lambda q, label="services": _make_fixture_response())
    out_path = tmp_path / "datos_servicios.js"
    extract.run(bbox="44.86,-93.38,45.05,-93.17", out_path=out_path)

    content = out_path.read_text(encoding="utf-8")
    assert "DATA_SERVICES_POLYGONS" in content
    assert "DATA_SERVICES_POINTS" in content
    assert "DATA_SERVICES_META" in content


def test_extract_splits_polygons_and_points(tmp_path, monkeypatch):
    from services import extract
    monkeypatch.setattr(extract, "query_with_retry",
                        lambda q, label="services": _make_fixture_response())
    out_path = tmp_path / "datos_servicios.js"
    extract.run(bbox="44.86,-93.38,45.05,-93.17", out_path=out_path)

    content = out_path.read_text(encoding="utf-8")
    # El hospital (way cerrado) va a polygons.health
    assert "Hennepin Healthcare HCMC" in content
    # La clínica (node) va a points.health
    assert "MinuteClinic" in content
    # El park (way cerrado) va a polygons.parks
    assert "Minnehaha Park" in content
    # La library (way cerrado con name) va a polygons.admin
    assert "Hennepin Library Central" in content


def test_extract_skips_unclassified(tmp_path, monkeypatch):
    from services import extract
    monkeypatch.setattr(extract, "query_with_retry",
                        lambda q, label="services": _make_fixture_response())
    out_path = tmp_path / "datos_servicios.js"
    extract.run(bbox="44.86,-93.38,45.05,-93.17", out_path=out_path)

    content = out_path.read_text(encoding="utf-8")
    # restaurant id=6 no debe aparecer
    assert '"id":6' not in content
    # museum sin name id=5 tampoco
    assert '"id":5' not in content


def test_extract_preserves_subtype_in_feature(tmp_path, monkeypatch):
    from services import extract
    monkeypatch.setattr(extract, "query_with_retry",
                        lambda q, label="services": _make_fixture_response())
    out_path = tmp_path / "datos_servicios.js"
    extract.run(bbox="44.86,-93.38,45.05,-93.17", out_path=out_path)

    content = out_path.read_text(encoding="utf-8")
    # El subtype "hospital" y "clinic" deben estar en el output
    assert '"subtype":"hospital"' in content
    assert '"subtype":"clinic"' in content
    assert '"subtype":"library"' in content


def test_extract_meta_has_bbox_and_total(tmp_path, monkeypatch):
    from services import extract
    monkeypatch.setattr(extract, "query_with_retry",
                        lambda q, label="services": _make_fixture_response())
    out_path = tmp_path / "datos_servicios.js"
    extract.run(bbox="44.86,-93.38,45.05,-93.17", out_path=out_path)

    content = out_path.read_text(encoding="utf-8")
    # Meta debe tener bbox y total_features
    meta_match = re.search(r"const DATA_SERVICES_META\s*=\s*(\{[^;]+\});", content)
    assert meta_match, "DATA_SERVICES_META no encontrado"
    meta = json.loads(meta_match.group(1))
    assert meta["bbox"] == "44.86,-93.38,45.05,-93.17"
    # 4 features clasificados (hospital, clinic, park, library)
    assert meta["total_features"] == 4
    assert "generated_at" in meta


def test_extract_all_five_categories_present_even_if_empty(tmp_path, monkeypatch):
    from services import extract
    monkeypatch.setattr(extract, "query_with_retry",
                        lambda q, label="services": _make_fixture_response())
    out_path = tmp_path / "datos_servicios.js"
    extract.run(bbox="44.86,-93.38,45.05,-93.17", out_path=out_path)

    content = out_path.read_text(encoding="utf-8")
    # Las 5 claves siempre presentes en POLYGONS y POINTS, incluso vacías
    for key in ["health", "education", "fire", "admin", "parks"]:
        # Debe estar en al menos uno de los dos objetos
        assert f'"{key}":' in content, f"falta clave '{key}'"
