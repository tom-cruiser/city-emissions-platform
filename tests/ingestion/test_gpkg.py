"""GeoPackage reading: header parsing on constructed blobs AND on the real committed polygons."""

import struct

import pytest

from ingestion import config
from ingestion.crosswalk import read_crosswalk
from ingestion.gpkg import GeoPackageError, describe_layers, parse_gpkg_blob, read_features
from ingestion.sample import UCDB_SAMPLE_PATH

UCDB_SAMPLE = config.SAMPLE_DIR / UCDB_SAMPLE_PATH

# A WKB point (little endian, type 1, x=1, y=2): the smallest valid payload.
WKB_POINT = struct.pack("<BIdd", 1, 1, 1.0, 2.0)


def _blob(*, little=True, indicator=1, srs_id=54009, empty=False, extended=False, envelope=None):
    flags = (1 if little else 0) | (indicator << 1) | (0b1_0000 if empty else 0) | (0b10_0000 if extended else 0)
    order = "<" if little else ">"
    n = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}[indicator]
    envelope = envelope or tuple(float(i) for i in range(n))
    return b"GP" + bytes([0, flags]) + struct.pack(f"{order}i{n}d", srs_id, *envelope) + WKB_POINT


@pytest.mark.parametrize("indicator,n", [(0, 0), (1, 4), (2, 6), (3, 6), (4, 8)])
@pytest.mark.parametrize("little", [True, False])
def test_header_envelope_sizes_and_byte_orders(indicator, n, little):
    g = parse_gpkg_blob(_blob(little=little, indicator=indicator))
    assert g.srs_id == 54009
    assert g.envelope == tuple(float(i) for i in range(n))
    assert g.wkb == WKB_POINT  # payload starts exactly after the envelope
    assert not g.empty


def test_empty_flag():
    assert parse_gpkg_blob(_blob(empty=True)).empty


@pytest.mark.parametrize("blob,message", [
    (b"XX" + bytes(30), "magic"),
    (_blob(extended=True), "Extended"),
    (_blob(indicator=1)[:30], "shorter"),
    (b"GP" + bytes([0, 0b1011]) + bytes(40), "indicator"),  # indicator 5 is reserved
    (b"GP" + bytes([1, 0b11]) + bytes(40), "version"),
])
def test_rejects_malformed_blobs(blob, message):
    with pytest.raises(GeoPackageError, match=message):
        parse_gpkg_blob(blob)


def test_rejects_non_geopackage(tmp_path):
    not_gpkg = tmp_path / "x.gpkg"
    not_gpkg.write_text("hello")
    with pytest.raises(GeoPackageError):
        describe_layers(not_gpkg)


# --- the real polygons in the committed sample ---------------------------------------------

def _wkb_bounds(wkb: bytes) -> tuple[float, float, float, float]:
    """Independent pure-Python WKB (Multi)Polygon reader: (minx, maxx, miny, maxy)."""
    xs, ys = [], []

    def geometry(pos):
        order = "<" if wkb[pos] == 1 else ">"
        (gtype,) = struct.unpack_from(f"{order}I", wkb, pos + 1)
        pos += 5
        if gtype == 3:  # Polygon
            (rings,) = struct.unpack_from(f"{order}I", wkb, pos)
            pos += 4
            for _ in range(rings):
                (npts,) = struct.unpack_from(f"{order}I", wkb, pos)
                pos += 4
                coords = struct.unpack_from(f"{order}{2 * npts}d", wkb, pos)
                xs.extend(coords[0::2])
                ys.extend(coords[1::2])
                pos += 16 * npts
        elif gtype == 6:  # MultiPolygon
            (parts,) = struct.unpack_from(f"{order}I", wkb, pos)
            pos += 4
            for _ in range(parts):
                pos = geometry(pos)
        else:
            raise AssertionError(f"unexpected WKB type {gtype}")
        return pos

    end = geometry(0)
    assert end == len(wkb), "trailing bytes after the geometry: header length was wrong"
    return min(xs), max(xs), min(ys), max(ys)


def test_sample_layer_is_mollweide():
    (layer,) = describe_layers(UCDB_SAMPLE)
    assert layer.table == config.GHS_UCDB_LAYER
    assert (layer.srs_organization, layer.srs_org_id) == config.GHS_UCDB_EXPECTED_SRS


def test_header_envelope_matches_real_polygon_coordinates():
    (layer,) = describe_layers(UCDB_SAMPLE)
    features = list(read_features(UCDB_SAMPLE, layer.table))
    assert len(features) == 25
    for attrs, geom in features:
        assert geom.srs_id == layer.srs_id
        assert len(geom.envelope) == 4, "R2024A writes XY envelopes"
        assert geom.envelope == pytest.approx(_wkb_bounds(geom.wkb), abs=1e-6), attrs["ID_UC_G0"]


def test_sample_contains_exactly_the_crosswalk_urban_centres():
    (layer,) = describe_layers(UCDB_SAMPLE)
    ids = sorted(attrs["ID_UC_G0"] for attrs, _ in read_features(UCDB_SAMPLE, layer.table))
    assert ids == sorted(int(r["edgar_uc_id"]) for r in read_crosswalk())


def test_sample_stays_small():
    assert UCDB_SAMPLE.stat().st_size < 1_000_000  # committed to git: keep it well under 1 MB
