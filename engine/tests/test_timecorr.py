from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from aiva.timecorr import osd
from aiva.timecorr.mapping import Piece, TimeMapping
from aiva.timecorr.parse import parse_filename, parse_osd

BASE = datetime(2026, 10, 28, 14, 30, 0)


def test_single_offset_correction():
    m = TimeMapping.from_start(BASE)
    m.corrections = [(BASE.isoformat(), (BASE - timedelta(seconds=222)).isoformat())]  # kamera 3:42 ileri
    assert m.to_camera(60) == BASE + timedelta(seconds=60)
    assert m.to_real(60) == BASE + timedelta(seconds=60 - 222)
    assert m.to_media(BASE + timedelta(seconds=60 - 222)) == [pytest.approx(60)]
    assert m.summary()["duzeltme_farki_sn"] == pytest.approx(-222)


def test_drift_two_references():
    m = TimeMapping.from_start(BASE)
    day = timedelta(days=1)
    # Kamera saati başta doğru, bir gün sonra 2 sn geri kalıyor
    m.corrections = [(BASE.isoformat(), BASE.isoformat()),
                     ((BASE + day).isoformat(), (BASE + day + timedelta(seconds=2)).isoformat())]
    half = 43200.0
    assert m.to_real(half) == pytest.approx(BASE + timedelta(seconds=half + 1), abs=timedelta(milliseconds=5))
    assert m.summary()["gunluk_kayma_sn"] == pytest.approx(2.0)
    back = m.to_media(m.to_real(half))
    assert back[0] == pytest.approx(half, abs=1e-3)


def test_pieces_with_gap_and_ranges():
    start = 1_700_000_000.0
    m = TimeMapping(pieces=[Piece(0.0, start), Piece(10.0, start + 600)])
    assert m.camera_sec(5) == start + 5
    assert m.camera_sec(12) == start + 612
    # 10–15 dk arası kamera saatine düşen kısım yalnızca ikinci parçadadır
    from aiva.timecorr.mapping import from_sec
    rng = m.media_range(from_sec(start + 605), from_sec(start + 615), duration=20.0)
    assert rng == [(pytest.approx(10.0), pytest.approx(15.0))]
    assert m.to_media(from_sec(start + 3)) == [pytest.approx(3.0)]


def test_contradictory_references_rejected():
    m = TimeMapping.from_start(BASE)
    m.corrections = [(BASE.isoformat(), (BASE + timedelta(seconds=100)).isoformat()),
                     ((BASE + timedelta(hours=1)).isoformat(), (BASE + timedelta(seconds=100)).isoformat())]
    with pytest.raises(ValueError, match="çelişkili"):
        m.validate()
    # Doğrulanmamış eski veride bile ters dönüşüm hata vermez
    assert m.to_media(BASE + timedelta(seconds=100)) is not None


def test_roundtrip_dict():
    m = TimeMapping(pieces=[Piece(0, 1.0)], corrections=[("2026-01-01T00:00:00", "2026-01-01T00:00:05")], source="osd")
    m2 = TimeMapping.from_dict(m.to_dict())
    assert m2.to_dict() == m.to_dict()


@pytest.mark.parametrize("text,expected", [
    ("28-10-2026 14:43:55", datetime(2026, 10, 28, 14, 43, 55)),
    ("2026/10/28 14:43:55", datetime(2026, 10, 28, 14, 43, 55)),
    ("Sal 28.10.2026 14:43:55", datetime(2026, 10, 28, 14, 43, 55)),
    ("10-28-2026 02:43:55 PM", datetime(2026, 10, 28, 14, 43, 55)),
    ("28-1O-2026 14:43:5S", datetime(2026, 10, 28, 14, 43, 55)),
    ("2026-10-28 14.43.55 CAM1", datetime(2026, 10, 28, 14, 43, 55)),
])
def test_parse_osd(text, expected):
    assert parse_osd(text) == expected


def test_parse_osd_time_only_uses_default_date():
    assert parse_osd("14:43:55", datetime(2026, 10, 28).date()) == datetime(2026, 10, 28, 14, 43, 55)
    assert parse_osd("KAMERA 01") is None


@pytest.mark.parametrize("name,expected", [
    ("CH01_20261028143000.dav", datetime(2026, 10, 28, 14, 30, 0)),
    ("2026-10-28_14-30-00.mp4", datetime(2026, 10, 28, 14, 30, 0)),
    ("NVR_ch2_main_20261028143000_20261028150000.mp4", datetime(2026, 10, 28, 14, 30, 0)),
    ("video.mp4", None),
])
def test_parse_filename(name, expected):
    assert parse_filename(name) == expected


@pytest.mark.slow
def test_osd_scan_detects_offset_and_jump(osd_video):
    path, scene = osd_video
    mapping, readings = osd.scan(path, scene.seconds, every=4.0)
    assert mapping is not None and len(readings) >= 4
    assert len(mapping.pieces) == 2
    assert mapping.to_camera(5.0) == pytest.approx(scene.camera_time(5.0), abs=timedelta(seconds=1.1))
    assert mapping.to_camera(15.0) == pytest.approx(scene.camera_time(15.0), abs=timedelta(seconds=1.1))
    assert mapping.gaps and abs(mapping.gaps[0]["t"] - 10.0) <= 1.0
    assert mapping.gaps[0]["jump"] == pytest.approx(600, abs=1.5)
