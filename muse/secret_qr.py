"""Read the Android companion's pairing secret from its QR code.

Payload: "RMC1:" + 64 lowercase hex characters (the same 32-byte secret the
companion shows as text). Frames are decoded in memory only: never saved,
logged or printed, because the image contains the secret.
"""
import time

PREFIX = "RMC1:"
HEX = set("0123456789abcdef")


def parse_payload(text):
    """Return the 64-char hex secret from a QR payload, or raise ValueError."""
    text = str(text or "").strip()
    if not text.upper().startswith(PREFIX):
        raise ValueError("Not a Raven-Muse-Control pairing QR code")
    secret = text[len(PREFIX):].strip().lower()
    if len(secret) != 64 or not set(secret) <= HEX:
        raise ValueError("Pairing QR code is damaged or incomplete")
    return secret


def decode_frame(frame):
    """Decode one OpenCV image (numpy array). Returns the payload text or ''."""
    import cv2
    if frame is None:
        return ""
    data, _, _ = cv2.QRCodeDetector().detectAndDecode(frame)
    return data or ""


def secret_from_image(path):
    import cv2
    frame = cv2.imread(str(path))
    if frame is None:
        raise ValueError("Could not read that image file")
    data = decode_frame(frame)
    if not data:
        raise ValueError("No QR code found in the image; try a sharper, closer photo")
    return parse_payload(data)


def secret_from_camera(timeout=60.0, camera=None, on_wrong_code=None):
    """Scan with the Raven SDK camera: glasses camera on device, webcam in the simulator.

    Ignores unrelated QR codes until a valid Raven-Muse-Control code appears.
    """
    if camera is None:
        import os
        from raven_framework.peripherals.camera import Camera
        camera = Camera(os.environ.get("RMC_APP_ID", ""), os.environ.get("RMC_APP_KEY", ""))
    camera.open_camera()
    try:
        if not camera.is_camera_open():
            raise RuntimeError("Camera unavailable; check camera permission or use --image")
        deadline = time.monotonic() + timeout
        last_wrong = ""
        while time.monotonic() < deadline:
            data = decode_frame(camera.capture_camera_image())
            if data:
                try:
                    return parse_payload(data)
                except ValueError as error:
                    if on_wrong_code and str(error) != last_wrong:
                        on_wrong_code(str(error))
                    last_wrong = str(error)
            time.sleep(0.1)
        raise TimeoutError("No pairing QR code seen; hold the phone steady about 20-30 cm away")
    finally:
        camera.close_camera()
