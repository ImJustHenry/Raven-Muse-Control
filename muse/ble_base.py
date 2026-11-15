"""One worker owns the BLE client. No Bluetooth work runs on the Qt UI thread."""
import asyncio
from dataclasses import replace
import queue
import threading
import time
from bleak import BleakClient
from .model import State


class BleTransport:
    def __init__(self, address, pair_on_connect=False, require_address=True):
        if require_address and not address:
            raise ValueError("Configure the phone's Bluetooth address/identifier first")
        self.address, self.pair_on_connect = address, pair_on_connect
        self.lock = threading.RLock()
        self.state = State(message="Connecting to phone")
        self.outgoing = queue.Queue(maxsize=2)
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=lambda: asyncio.run(self._run()), daemon=True)
            self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)

    def snapshot(self):
        with self.lock:
            return self.state

    def update(self, **fields):
        with self.lock:
            self.state = replace(self.state, **fields)

    def clear_queue(self):
        while True:
            try:
                self.outgoing.get_nowait()
            except queue.Empty:
                return

    def send(self, op):
        s = self.snapshot()
        if not s.can(op):
            raise ValueError("This player does not currently expose that action")
        try:
            self.outgoing.put_nowait((op, s.player, time.monotonic()))
        except queue.Full:
            raise ValueError("Wait for the previous command") from None
        self.update(message="Queued locally - not yet confirmed by phone")

    async def _run(self):
        try:
            await self._loop()
        finally:
            try:
                await self.link_close()
            except Exception:
                pass

    async def _loop(self):
        while not self.stop.is_set():
            self.clear_queue()  # never replay commands after reconnecting
            with self.lock:
                self.state = self.state.offline("Connecting - open the music app on your phone")
            try:
                target = await self.connect_target()
                async with BleakClient(target, timeout=20) as client:
                    if self.pair_on_connect:
                        try:
                            await client.pair()
                        except NotImplementedError:
                            pass  # macOS prompts through CoreBluetooth when required
                    await self.setup(client)
                    while client.is_connected and not self.stop.is_set():
                        await self.tick(client)
                        try:
                            op, player, created = self.outgoing.get_nowait()
                        except queue.Empty:
                            await asyncio.sleep(.08)
                            continue
                        state = self.snapshot()
                        if time.monotonic() - created > 2:
                            self.update(message="Command expired; select it again")
                        elif player != state.player or not state.can(op):
                            self.update(message="Player/capability changed; select again")
                        else:
                            await self.execute(client, op, player)
            except Exception as error:
                # Do not log configuration, secrets, or transcript content.
                with self.lock:
                    self.state = self.state.offline(
                        f"Bluetooth {type(error).__name__}: check phone, pairing and permissions")
            finally:
                self.clear_queue()
                with self.lock:
                    self.state = self.state.offline(self.state.message)
            for _ in range(20):
                if self.stop.is_set():
                    break
                await asyncio.sleep(.1)

    async def connect_target(self):
        """Address or bleak BLEDevice to connect to. Subclasses may discover it."""
        return self.address

    async def link_close(self):
        """Release link resources (for example a BlueZ advertisement) on shutdown."""

    async def setup(self, client):
        raise NotImplementedError

    async def tick(self, client):
        raise NotImplementedError

    async def execute(self, client, op, player):
        raise NotImplementedError
