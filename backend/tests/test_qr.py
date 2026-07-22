import uuid

from app.services.qr import decode_qr, generate_qr


def test_qr_round_trips_for_20_random_uuids():
    for _ in range(20):
        qr_id = str(uuid.uuid4())
        png = generate_qr(qr_id)
        assert decode_qr(png) == qr_id


def test_decode_qr_returns_none_for_unreadable_image():
    blank_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
        b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    assert decode_qr(blank_png) is None
