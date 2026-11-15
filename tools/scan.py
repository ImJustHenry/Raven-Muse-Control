"""Local BLE discovery. No connection, commands, or external networking."""
import argparse
import asyncio
from bleak import BleakScanner

async def scan(kind):
    services = ["7c27f100-6baa-4ad0-8e3b-31f62b88ac50"] if kind == "android" else None
    found = await BleakScanner.discover(timeout=10, return_adv=True, service_uuids=services)
    for address, (device, advertisement) in found.items():
        print(address, "|", device.name or advertisement.local_name or "Unnamed BLE device")
    if not found:
        print("No devices found. Check Bluetooth, permissions, discoverability, and the Android bridge.")
    if kind == "iphone":
        print("An iPhone may not advertise AMS. Pair through OS settings and use its OS BLE identifier.")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--kind", choices=["android", "iphone"], default="android")
    args = p.parse_args()
    asyncio.run(scan(args.kind))
