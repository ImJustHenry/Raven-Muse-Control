"""Set up Android control by scanning the companion's pairing QR code.

    python tools/scan_secret.py                 # camera (glasses camera / Mac webcam)
    python tools/scan_secret.py --image qr.jpg  # a photo you took yourself

On the phone: Raven-Muse-Control > Start Bluetooth control, then
"3. Show controller pairing secret". Point the camera at the QR code.

The tool also looks for the phone's Bluetooth bridge and saves both into the
private config (~/.config/raven-muse-control/config.json, mode 0600). The
secret is never printed, logged or stored anywhere else. Delete any photo of
the QR code after use.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from muse.android import SERVICE  # noqa: E402
from muse.secret_qr import secret_from_camera, secret_from_image  # noqa: E402


def config_path():
    default = Path.home() / ".config" / "raven-muse-control" / "config.json"
    return Path(os.environ.get("RMC_CONFIG", str(default)))


def load(path):
    base = json.loads((ROOT / "config.example.json").read_text())
    if path.exists():
        base.update(json.loads(path.read_text()))
    return base


def save(path, config):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2) + "\n")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


async def find_bridges(timeout=10):
    from bleak import BleakScanner
    found = await BleakScanner.discover(timeout=timeout, return_adv=True, service_uuids=[SERVICE])
    return [(address, device.name or adv.local_name or "Android bridge", adv.rssi)
            for address, (device, adv) in found.items()]


def choose_address(bridges, current):
    if len(bridges) == 1:
        return bridges[0][0]
    if not bridges:
        if current:
            print("No bridge advertising right now; keeping the saved phone address.")
            return current
        raise SystemExit("No Android bridge found. On the phone tap 'Start Bluetooth control', "
                         "then re-run, or pass --address.")
    print("Several Android bridges found:")
    for i, (address, name, rssi) in enumerate(sorted(bridges, key=lambda b: -b[2]), 1):
        print(f"  {i}. {address}  {name}  signal {rssi}")
    pick = input("Number of your phone: ").strip()
    if not pick.isdigit() or not 1 <= int(pick) <= len(bridges):
        raise SystemExit("Unchanged")
    return sorted(bridges, key=lambda b: -b[2])[int(pick) - 1][0]


def main():
    parser = argparse.ArgumentParser(description="Scan the Android pairing QR code")
    parser.add_argument("--image", help="photo of the QR code instead of the camera")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--address", help="phone Bluetooth identifier; skips the Bluetooth scan")
    args = parser.parse_args()

    if args.image:
        secret = secret_from_image(args.image)
    else:
        print("Point the camera at the QR code on the phone (Ctrl+C to cancel)...")
        secret = secret_from_camera(args.timeout, on_wrong_code=lambda why: print(f"  {why}"))
    print("Pairing QR code read.")

    path = config_path()
    config = load(path)
    if args.address:
        address = args.address.strip()
    else:
        print("Looking for the phone's Bluetooth bridge (10 s)...")
        address = choose_address(asyncio.run(find_bridges()), config.get("phone_address", ""))
    replaced = bool(config.get("android_secret_hex")) and config["android_secret_hex"] != secret
    config.update(mode="android", phone_address=address, android_secret_hex=secret)
    save(path, config)
    print(f"Saved private config: {path}")
    print(f"  mode: android   phone: {address}")
    print("  secret: updated (replaced the previous one)" if replaced else "  secret: saved")
    print("Start Muse with: python main.py")


if __name__ == "__main__":
    main()
