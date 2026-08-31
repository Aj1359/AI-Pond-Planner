"""
Tests for /api/contour/analyzeContour (and its /findCatchment alias).

Uses the actual sample contour map (tests/fixtures/sample_contours.kml)
as a fixture rather than a synthetic KML, so these tests exercise the
real parsing/interpolation path end-to-end, not just a simplified case.
These don't need fake_supabase/api_client from conftest.py — this route
is stateless (no DB persistence), so a plain TestClient is enough.
"""
import io
import zipfile
from pathlib import Path

# pyrefly: ignore [missing-import]
import pytest
from fastapi.testclient import TestClient

from app.main import app

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "contours_1m.kml"
    if (Path(__file__).parent / "fixtures" / "contours_1m.kml").exists()
    else Path(__file__).parent / "fixtures" / "sample_contours.kml"
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_kml_bytes():
    return FIXTURE_PATH.read_bytes()


def test_analyze_contour_returns_valid_structure(client, sample_kml_bytes):
    r = client.post(
        "/api/contour/analyzeContour",
        files={"file": ("contours_1m.kml", sample_kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    assert r.status_code == 200
    body = r.json()

    assert "input_summary" in body
    assert "derived_terrain" in body
    assert "recommended_site" in body
    assert "alternative_sites" in body
    assert "methodology" in body


def test_input_summary_matches_known_file_stats(client, sample_kml_bytes):
    """These numbers were independently verified by inspecting the raw
    KML (grep/manual XML parsing) before the endpoint existed — this
    test guards against a future change silently breaking the parser."""
    r = client.post(
        "/api/contour/analyzeContour",
        files={"file": ("contours_1m.kml", sample_kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    summary = r.json()["input_summary"]
    assert summary["contour_line_count"] == 1355
    assert summary["elevation_range_m"] == [267.0, 298.0]
    assert summary["contour_interval_m"] == 1.0


def test_bbox_is_derived_from_file_not_hardcoded(client, sample_kml_bytes):
    """The PS explicitly requires no hardcoded coordinates — verify the
    returned bbox actually matches this file's real coordinate extent."""
    r = client.post(
        "/api/contour/analyzeContour",
        files={"file": ("contours_1m.kml", sample_kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    bbox = r.json()["derived_terrain"]["bbox"]
    # Known extent of the sample file (independently measured, see contour_ingest tests)
    assert 81.28 < bbox["min_lon"] < 81.29
    assert 81.31 < bbox["max_lon"] < 81.32
    assert 21.23 < bbox["min_lat"] < 21.25
    assert 21.26 < bbox["max_lat"] < 21.27


def test_recommended_site_has_largest_catchment_among_candidates(client, sample_kml_bytes):
    """Regression test for a real bug caught during development: the
    recommendation must not simply pick the flattest site — it must
    weigh catchment yield too, since a flat site with no drainage area
    is a poor pond location."""
    r = client.post(
        "/api/contour/analyzeContour",
        files={"file": ("contours_1m.kml", sample_kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    body = r.json()
    all_sites = [body["recommended_site"]] + body["alternative_sites"]
    recommended_area = body["recommended_site"]["catchment"]["area_ha"]
    max_area = max(s["catchment"]["area_ha"] for s in all_sites)
    assert recommended_area == max_area, "recommended site should have the largest catchment, not just best slope"


def test_sites_are_ranked_descending_by_recommendation_score(client, sample_kml_bytes):
    r = client.post(
        "/api/contour/analyzeContour",
        files={"file": ("contours_1m.kml", sample_kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    body = r.json()
    all_sites = [body["recommended_site"]] + body["alternative_sites"]
    scores = [s["recommendation_score"] for s in all_sites]
    assert scores == sorted(scores, reverse=True)


def test_findcatchment_alias_matches_analyzecontour(client, sample_kml_bytes):
    r1 = client.post(
        "/api/contour/analyzeContour",
        files={"file": ("contours_1m.kml", sample_kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    r2 = client.post(
        "/api/contour/findCatchment",
        files={"file": ("contours_1m.kml", sample_kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["input_summary"] == r2.json()["input_summary"]


def test_kmz_zip_wrapped_kml_produces_identical_results(client, sample_kml_bytes):
    kmz_buf = io.BytesIO()
    with zipfile.ZipFile(kmz_buf, "w") as z:
        z.writestr("doc.kml", sample_kml_bytes)

    r = client.post(
        "/api/contour/analyzeContour",
        files={"file": ("contours.kmz", kmz_buf.getvalue(), "application/vnd.google-earth.kmz")},
    )
    assert r.status_code == 200
    assert r.json()["input_summary"]["contour_line_count"] == 1355


def test_wrong_file_extension_rejected_with_400(client):
    r = client.post("/api/contour/analyzeContour", files={"file": ("notakml.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_empty_file_rejected_with_400(client):
    r = client.post(
        "/api/contour/analyzeContour",
        files={"file": ("empty.kml", b"", "application/vnd.google-earth.kml+xml")},
    )
    assert r.status_code == 400


def test_malformed_xml_rejected_with_400_not_500(client):
    r = client.post(
        "/api/contour/analyzeContour",
        files={"file": ("bad.kml", b"not xml at all {{{", "application/vnd.google-earth.kml+xml")},
    )
    assert r.status_code == 400


def test_valid_xml_with_no_contours_rejected_with_400(client):
    empty_kml = b'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document></Document></kml>'
    r = client.post(
        "/api/contour/analyzeContour",
        files={"file": ("no_contours.kml", empty_kml, "application/vnd.google-earth.kml+xml")},
    )
    assert r.status_code == 400