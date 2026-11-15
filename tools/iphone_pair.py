"""One-time iPhone pairing + Apple Media Service check for Linux / RavenOS (BlueZ).

Run on the Linux machine or glasses, NOT on macOS:
    python tools/iphone_pair.py            # pair, then check AMS
    python tools/iphone_pair.py --check    # no pairing window; just look for a bonded iPhone

What happens:
1. This device advertises as an accessory that wants Apple Media Service.
2. On the iPhone: Settings > Bluetooth > tap "Raven Muse" under Other Devices.
3. Both screens show a 6-digit code; type y here only if the codes match.
4. The tool reports whether the iPhone now exposes AMS and prints its address.

Read-only: it lists services and sends no media commands. Nothing is logged
to disk. Pairing is accepted only during the time-limited window.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from muse.bluez_accessory import (AMS_SERVICE, BluezAccessory, PairingGate,  # noqa: E402
                                  connected_unpaired, require_linux)


async def ask(question):
    answer = await asyncio.to_thread(input, question)
    return answer.strip().lower() in {"y", "yes"}


async def confirm(device, passkey):
    if passkey is None:
        return await ask("\nThe iPhone asks to pair without a code. Allow? [y/N]: ")
    return await ask(f"\nDoes the iPhone show {passkey:06d}? [y/N]: ")


async def main(args):
    require_linux()
    accessory = BluezAccessory(args.adapter, args.name)
    try:
        await accessory.start()
        print(f"Advertising as '{args.name}' (soliciting Apple Media Service {AMS_SERVICE}).")
        if not args.check:
            await accessory.open_pairing(PairingGate(confirm, args.seconds))
            print(f"Pairing window open for {args.seconds}s.")
            print("On the iPhone: Settings > Bluetooth > Other Devices > tap "
                  f"'{args.name}', then accept Pair.")
            print("Start Spotify or YouTube Music playback on the iPhone too.")
        tried = set()
        deadline = asyncio.get_running_loop().time() + args.seconds
        while asyncio.get_running_loop().time() < deadline:
            objects = await accessory.objects()
            if not args.check:
                # Fallback if the phone connected but iOS did not start bonding itself.
                for path in connected_unpaired(objects, accessory.adapter_path):
                    if path not in tried:
                        tried.add(path)
                        print("Connected device not yet paired; requesting pairing...")
                        try:
                            await accessory.pair_device(path)
                        except Exception as error:
                            print(f"  pairing request failed: {type(error).__name__}")
            try:
                device = await accessory.wait_for_iphone(timeout=2, poll=1)
            except TimeoutError:
                continue
            print("\nSUCCESS: bonded iPhone connected and Apple Media Service is visible.")
            print(f"  name:    {device.name}")
            print(f"  address: {device.address}")
            print("Next: python tools/configure.py -> mode iphone, link accessory.")
            print("Optionally enter the address above so only this iPhone is accepted.")
            return 0
        print("\nNo bonded iPhone exposing Apple Media Service within the window.")
        print("If the iPhone paired but AMS never appeared, this device/OS cannot be")
        print("used as an AMS accessory; record that as a failed acceptance check.")
        return 1
    finally:
        await accessory.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--adapter", default="hci0")
    parser.add_argument("--name", default="Raven Muse")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--check", action="store_true", help="do not open a pairing window")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
