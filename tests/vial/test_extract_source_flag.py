"""Tests for the --source CLI flag in vial.extract."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from vial.extract import parse_args


def test_default_source_is_pbf():
    args = parse_args(["--city", "minneapolis"])
    assert args.source == "pbf"


def test_source_overpass_accepted():
    args = parse_args(["--city", "minneapolis", "--source", "overpass"])
    assert args.source == "overpass"


def test_invalid_source_rejected():
    with pytest.raises(SystemExit):
        parse_args(["--city", "minneapolis", "--source", "garbage"])


def test_refresh_pbf_default_false():
    args = parse_args(["--city", "minneapolis"])
    assert args.refresh_pbf is False
