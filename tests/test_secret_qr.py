"""QR pairing-secret tests with generated images and a fake camera (no phone)."""
import importlib.util
import json
import os
import stat
import sys
import pytest
from muse.secret_qr import parse_payload, secret_from_camera, secret_from_image

SECRET = "0123456789abcdef" * 4
needs_cv2 = pytest.mark.skipif(importlib.util.find_spec("cv2") is None, reason="OpenCV not installed")


def qr_image(tmp_path, text):
    import cv2
    image = cv2.QRCodeEncoder.create().encode(text)
    image = cv2.resize(image, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
    image = cv2.copyMakeBorder(image, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    path = tmp_path / "qr.png"
    cv2.imwrite(str(path), image)
    return path


def test_parse_valid_payload_case_insensitive():
    assert parse_payload("RMC1:" + SECRET.upper()) == SECRET
    assert parse_payload("  rmc1:" + SECRET + "\n") == SECRET


@pytest.mark.parametrize("text", ["", SECRET, "RMC1:", "RMC1:" + SECRET[:-1],
                                  "RMC1:" + SECRET + "00", "RMC1:" + "g" * 64, "https://example.org"])
def test_parse_rejects_wrong_or_damaged_codes(text):
    with pytest.raises(ValueError):
        parse_payload(text)


@needs_cv2
def test_secret_from_generated_image(tmp_path):
    assert secret_from_image(qr_image(tmp_path, "RMC1:" + SECRET)) == SECRET


@needs_cv2
def test_image_without_qr_rejected(tmp_path):
    import cv2, numpy as np
    path = tmp_path / "blank.png"
    cv2.imwrite(str(path), np.full((200, 200), 255, dtype="uint8"))
    with pytest.raises(ValueError):
        secret_from_image(path)


class FakeCamera:
    def __init__(self, frames, opens=True):
        self.frames, self.opens, self.closed = list(frames), opens, False
    def open_camera(self): pass
    def is_camera_open(self): return self.opens
    def capture_camera_image(self): return self.frames.pop(0) if self.frames else None
    def close_camera(self): self.closed = True


@needs_cv2
def test_camera_skips_unrelated_codes_then_reads_secret(tmp_path):
    import cv2
    wrong = cv2.imread(str(qr_image(tmp_path, "https://example.org")))
    right = cv2.imread(str(qr_image(tmp_path, "RMC1:" + SECRET)))
    messages = []
    camera = FakeCamera([None, wrong, wrong, right])
    assert secret_from_camera(5, camera, messages.append) == SECRET
    assert camera.closed and len(messages) == 1


def test_camera_unavailable_and_timeout_close_camera():
    camera = FakeCamera([], opens=False)
    with pytest.raises(RuntimeError):
        secret_from_camera(1, camera)
    assert camera.closed
    camera = FakeCamera([])
    with pytest.raises(TimeoutError):
        secret_from_camera(0.3, camera)
    assert camera.closed


@needs_cv2
def test_tool_saves_private_config_without_printing_secret(tmp_path, monkeypatch, capsys):
    from tools import scan_secret
    target = tmp_path / "private" / "config.json"
    monkeypatch.setenv("RMC_CONFIG", str(target))
    image = qr_image(tmp_path, "RMC1:" + SECRET)
    monkeypatch.setattr(sys, "argv", ["scan_secret", "--image", str(image), "--address", "PHONE-ID"])
    scan_secret.main()
    out = capsys.readouterr().out
    assert SECRET not in out and SECRET.upper() not in out
    config = json.loads(target.read_text())
    assert config["mode"] == "android" and config["phone_address"] == "PHONE-ID"
    assert config["android_secret_hex"] == SECRET
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_choose_address_rules():
    from tools.scan_secret import choose_address
    assert choose_address([("A", "x", -40)], "") == "A"
    assert choose_address([], "SAVED") == "SAVED"
    with pytest.raises(SystemExit):
        choose_address([], "")
