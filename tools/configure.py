"""Interactive private config; never paste its resulting secrets into Claude."""
import getpass
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = Path(os.environ.get("RMC_CONFIG", str(Path.home() / ".config" / "raven-muse-control" / "config.json")))
path.parent.mkdir(parents=True, exist_ok=True)
if path.exists() and input("Replace existing private config? Type YES: ") != "YES":
    raise SystemExit("Unchanged")
config = json.loads((root / "config.example.json").read_text())
mode = input("Mode [demo/iphone/android], default demo: ").strip() or "demo"
if mode not in {"demo", "iphone", "android"}:
    raise SystemExit("Unknown mode")
config["mode"] = mode
if mode != "demo":
    config["phone_address"] = input("OS Bluetooth address/identifier: ").strip()
    config["pair_on_connect"] = input("Request OS pairing on connect? [y/N]: ").lower() == "y"
if mode == "android":
    how = input("Read the phone's pairing secret from its QR code with the camera? [Y/n]: ").strip().lower()
    if how in {"", "y", "yes"}:
        import sys
        sys.path.insert(0, str(root))
        from muse.secret_qr import secret_from_camera
        print("Phone: Raven-Muse-Control > 3. Show controller pairing secret. Point the camera at it.")
        secret = secret_from_camera(60, on_wrong_code=lambda why: print(" ", why))
        print("Pairing QR code read.")
    else:
        secret = getpass.getpass("Private 64-character hex secret from Android: ").strip()
    if len(secret) != 64 or len(bytes.fromhex(secret)) != 32:
        raise SystemExit("Invalid secret")
    config["android_secret_hex"] = secret
if mode == "iphone":
    print("Link: 'connect' dials the phone (Mac/Windows). 'accessory' is Linux/RavenOS only:")
    print("the glasses advertise as an Apple Media Service accessory; pair once with")
    print("tools/iphone_pair.py. Phone address is optional in accessory mode.")
    link = input("iPhone link [connect/accessory], default connect: ").strip() or "connect"
    if link not in {"connect", "accessory"}:
        raise SystemExit("Unknown iPhone link")
    config["iphone_link"] = link
    if link == "accessory":
        config["pair_on_connect"] = False
        config["bluetooth_adapter"] = input("BlueZ adapter, default hci0: ").strip() or "hci0"
    print("Optional online cover lookup sends song title/artist/album to MusicBrainz;")
    print("cover requests go to Cover Art Archive/Internet Archive. No audio is sent.")
    print("Matches may differ from phone art. Read ARTWORK.md for rights/commercial terms.")
    if input("Enable online artwork? Type YES to consent (default OFF): ") == "YES":
        contact = input("Public contact URL/email for MusicBrainz User-Agent: ").strip()
        from muse.artwork_lookup import MusicBrainzLookup
        MusicBrainzLookup(contact)  # Validate only; no network request.
        config.update(artwork_lookup="musicbrainz", online_artwork_consent=True, artwork_contact=contact)
path.write_text(json.dumps(config, indent=2) + "\n")
os.chmod(path, 0o600)
print("Saved private configuration outside the source bundle:", path)
print("The default voice mode is typed simulator input.")
print("For glasses: configure Vosk or explicitly consented cloud speech, plus your Raven app credentials.")
