"""Test the route classifier: OSM tags → CS2 category."""
from transporte.classifiers import classify_route


def test_light_rail_classifies_as_lrt():
    """METRO Blue/Green Line use route=light_rail."""
    assert classify_route({"route": "light_rail", "name": "METRO Green Line"}) == "lrt"


def test_tram_classifies_as_lrt():
    """European trams map to LRT in CS2 visualization."""
    assert classify_route({"route": "tram", "name": "Tram 4"}) == "lrt"


def test_train_classifies_as_commuter():
    """Northstar uses route=train."""
    assert classify_route({"route": "train", "name": "Northstar"}) == "commuter"


def test_commuter_rail_alias_classifies_as_commuter():
    """Some OSM data uses commuter_rail as the route value."""
    assert classify_route({"route": "commuter_rail", "name": "X"}) == "commuter"


def test_metro_rapid_classifies_as_brt():
    """METRO Rapid Bus (A/C/D/E/F Line) is BRT, detected via network=METRO."""
    assert classify_route({"route": "bus", "network": "METRO", "name": "METRO A Line"}) == "brt"


def test_metro_rapid_classifies_as_brt_name_only():
    """Fallback: name contains METRO and ' Line' but network may be absent."""
    assert classify_route({"route": "bus", "name": "METRO C Line"}) == "brt"


def test_local_bus_classifies_as_bus():
    """Regular Metro Transit local bus route."""
    assert classify_route({"route": "bus", "name": "Route 5", "network": "Metro Transit"}) == "bus"


def test_bus_without_name_classifies_as_bus():
    """Bus with no name fields still classifies — doesn't match BRT pattern."""
    assert classify_route({"route": "bus"}) == "bus"


def test_unknown_route_returns_none():
    """Routes we don't care about (ferry, hiking, etc.) return None."""
    assert classify_route({"route": "ferry"}) is None


def test_missing_route_returns_none():
    """No route tag at all → None."""
    assert classify_route({"name": "something"}) is None


def test_empty_tags_returns_none():
    assert classify_route({}) is None


def test_route_value_is_case_insensitive():
    """Defensive against weird OSM data — but real OSM uses lowercase."""
    assert classify_route({"route": "Light_Rail"}) == "lrt"
