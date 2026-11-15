"""Public Apple Media Service client. No iPhone player or Spotify account API."""
import asyncio
from collections import deque
from dataclasses import replace
import time
from .ble_base import BleTransport
from .model import State, finite, supported_player

SERVICE = "89d3502b-0f36-433a-8ef4-c502ad55f8dc"
REMOTE = "9b3c81d8-57b1-4a8a-b8df-0e56f7ca51c2"
UPDATE = "2f7cabce-808d-411f-9a0c-bb92ba96c102"
ATTRIBUTE = "c6b2f38c-23ab-46d8-a6ab-a3a870bbd5d7"
SERVICE_CHANGED = "00002a05-0000-1000-8000-00805f9b34fb"
COMMANDS = {"play": 0, "pause": 1, "toggle": 2, "next": 3, "previous": 4,
            "volume_up": 5, "volume_down": 6, "repeat": 7, "shuffle": 8,
            "forward": 9, "back": 10}


def parse_update(data):
    if len(data) < 3:
        raise ValueError("Short AMS event")
    return data[0], data[1], bool(data[2] & 1), bytes(data[3:]).decode("utf-8", errors="replace")


def apply_attribute(state, entity, attr, value, truncated=False, now=None):
    now = time.monotonic() if now is None else now
    fields = {"truncated": truncated, "revision": state.revision + 1}
    if entity == 0 and attr == 0:
        fields["player"] = value
    elif entity == 0 and attr == 1:
        parts = value.split(",")
        if len(parts) == 3:
            try:
                playing = int(parts[0]) in {1, 2, 3}
            except ValueError:
                return state
            fields.update(playing=playing, rate=(finite(parts[1], -16) or 0) if playing else 0,
                          position=finite(parts[2]), sampled_at=now)
    elif entity == 0 and attr == 2:
        volume = finite(value)
        fields["volume"] = min(1, volume) if volume is not None else None
    elif entity == 2:
        if attr == 0:
            fields["artist"] = value
        elif attr == 1:
            fields["album"] = value
        elif attr == 2:
            fields["title"] = value
        elif attr == 3:
            fields["duration"] = finite(value)
    return replace(state, **fields)


class IphoneTransport(BleTransport):
    """link="connect": dial the phone address (macOS/Windows/Linux central).
    link="accessory": Linux/BlueZ only; advertise as an AMS accessory and use the
    already-bonded iPhone that connects in (see muse/bluez_accessory.py).
    """
    def __init__(self, address, pair_on_connect=False, link="connect", adapter="hci0"):
        if link not in {"connect", "accessory"}:
            raise ValueError("iphone_link must be 'connect' or 'accessory'")
        self.link = link
        self.accessory = None
        if link == "accessory":
            from .bluez_accessory import require_linux, valid_adapter
            require_linux()
            if not valid_adapter(adapter):
                raise ValueError("bluetooth_adapter must look like hci0")
            self.adapter = adapter
            # Address is optional here: if set, only that bonded iPhone is accepted.
            # Pairing is never requested by the running app; use tools/iphone_pair.py.
            super().__init__(address, False, require_address=False)
        else:
            super().__init__(address, pair_on_connect)

    async def connect_target(self):
        if self.link != "accessory":
            return self.address
        if self.accessory is None:
            from .bluez_accessory import BluezAccessory
            accessory = BluezAccessory(self.adapter, allowed_address=self.address)
            try:
                await accessory.start()
            except Exception:
                await accessory.close()
                raise
            self.accessory = accessory
        self.update(message="Waiting for paired iPhone - keep its Bluetooth on")
        return await self.accessory.wait_for_iphone(timeout=20)

    async def link_close(self):
        if self.accessory is not None:
            accessory, self.accessory = self.accessory, None
            await accessory.close()

    async def setup(self, client):
        if not client.services.get_service(SERVICE):
            raise ValueError("iPhone did not publish Apple Media Service")
        for char in (REMOTE, UPDATE):
            if not client.services.get_characteristic(char):
                raise ValueError("Required AMS characteristic not available")
        self.full_reads = deque(maxlen=16)
        self.supported = set()
        self.changed = False
        self.has_attribute = client.services.get_characteristic(ATTRIBUTE) is not None
        self.state = State(connected=True, message="Waiting for iPhone media metadata")

        def remote_event(_, data):
            self.supported = set(data)
            self._capabilities()

        def entity_event(_, data):
            try:
                entity, attr, truncated, value = parse_update(data)
            except ValueError:
                return
            with self.lock:
                self.state = apply_attribute(self.state, entity, attr, value, truncated)
            if truncated and self.has_attribute:
                key = bytes([entity, attr])
                if key not in self.full_reads:
                    self.full_reads.append(key)
            self._capabilities()

        await client.start_notify(REMOTE, remote_event)
        await client.start_notify(UPDATE, entity_event)
        if client.services.get_characteristic(SERVICE_CHANGED):
            await client.start_notify(SERVICE_CHANGED, lambda *_: setattr(self, "changed", True))
        # Serialize writes; Apple's attribute selector is shared state.
        await client.write_gatt_char(UPDATE, bytes([0, 0, 1, 2]), response=True)
        await client.write_gatt_char(UPDATE, bytes([2, 0, 1, 2, 3]), response=True)

    def _capabilities(self):
        state = self.snapshot()
        caps = frozenset(k for k, v in COMMANDS.items() if v in self.supported)
        if not supported_player(state.player):
            caps = frozenset()
            message = "Start Spotify or YouTube Music on the phone"
        else:
            message = "iPhone connected - displaying reported media state"
        self.update(capabilities=caps, message=message)

    async def tick(self, client):
        if self.changed:
            # Reconnect to rediscover services instead of using stale GATT handles.
            raise ConnectionError("iPhone services changed")
        if self.full_reads:
            key = self.full_reads.popleft()
            await client.write_gatt_char(ATTRIBUTE, key, response=True)
            value = bytes(await client.read_gatt_char(ATTRIBUTE)).decode("utf-8", errors="replace")
            with self.lock:
                self.state = apply_attribute(self.state, key[0], key[1], value)
            self._capabilities()

    async def execute(self, client, op, player):
        if self.snapshot().player != player:
            self.update(message="Player changed - command cancelled")
            return
        await client.write_gatt_char(REMOTE, bytes([COMMANDS[op]]), response=True)
        self.update(message="Sent to iPhone; playback changes only when the app reports them")
        # A GATT write confirms forwarding, not execution. Never synthesize success state.
        await asyncio.sleep(.08)
