"""Offline tests for the Linux AMS accessory link. Fake BlueZ object trees only;
these do NOT show that RavenOS, BlueZ or a real iPhone accept the accessory."""
import asyncio
import importlib.util
import sys
import pytest
from muse import bluez_accessory as bz
from muse.iphone import IphoneTransport

ADAPTER = "/org/bluez/hci0"
PHONE = ADAPTER + "/dev_AA_BB_CC_DD_EE_FF"


def tree(connected=True, resolved=True, paired=True, ams=True, address="AA:BB:CC:DD:EE:FF"):
    objects = {
        ADAPTER: {"org.bluez.Adapter1": {"Powered": True}},
        PHONE: {"org.bluez.Device1": {"Address": address, "Name": "Phone", "Connected": connected,
                                      "ServicesResolved": resolved, "Paired": paired}},
        PHONE + "/service0001": {"org.bluez.GattService1": {"UUID": "0000180a-0000-1000-8000-00805f9b34fb"}},
    }
    if ams:
        objects[PHONE + "/service0010"] = {"org.bluez.GattService1": {"UUID": bz.AMS_SERVICE.upper()}}
    return objects


def test_advertisement_solicits_ams_as_connectable_peripheral():
    props = bz.advertisement_properties("A very long accessory name here")
    assert props["Type"] == "peripheral"
    assert props["SolicitUUIDs"] == [bz.AMS_SERVICE]
    assert len(props["LocalName"]) <= 20


def test_finds_bonded_connected_iphone_with_ams():
    path, props = bz.find_iphone(tree(), ADAPTER)
    assert path == PHONE and props["Address"] == "AA:BB:CC:DD:EE:FF"


@pytest.mark.parametrize("changes", [{"connected": False}, {"resolved": False},
                                     {"paired": False}, {"ams": False}])
def test_rejects_devices_that_are_not_ready_or_not_bonded(changes):
    assert bz.find_iphone(tree(**changes), ADAPTER) is None


def test_allowed_address_filter_and_other_adapter():
    assert bz.find_iphone(tree(), ADAPTER, "aa:bb:cc:dd:ee:ff") is not None
    assert bz.find_iphone(tree(), ADAPTER, "11:22:33:44:55:66") is None
    assert bz.find_iphone(tree(), "/org/bluez/hci1") is None


def test_check_without_bond_only_when_explicitly_requested():
    assert bz.find_iphone(tree(paired=False), ADAPTER, require_bonded=False) is not None


def test_connected_unpaired_lists_only_devices():
    assert bz.connected_unpaired(tree(paired=False), ADAPTER) == [PHONE]
    assert bz.connected_unpaired(tree(), ADAPTER) == []


@pytest.mark.parametrize("name", ["hci0", "hci12"])
def test_valid_adapter(name):
    assert bz.valid_adapter(name)


@pytest.mark.parametrize("name", ["", "hci", "eth0", "hci0/../x", None])
def test_invalid_adapter(name):
    assert not bz.valid_adapter(name)


def test_pairing_gate_window_and_confirmation():
    now = [0.0]
    gate = bz.PairingGate(lambda device, passkey: passkey == 123456, seconds=60, clock=lambda: now[0])
    assert asyncio.run(gate.confirm(PHONE, 123456))
    assert not asyncio.run(gate.confirm(PHONE, 111111))
    now[0] = 61
    assert not gate.is_open() and not asyncio.run(gate.confirm(PHONE, 123456))


def test_pairing_gate_rejects_if_window_expires_during_prompt():
    now = [0.0]
    async def slow_yes(device, passkey):
        now[0] = 500
        return True
    gate = bz.PairingGate(slow_yes, seconds=30, clock=lambda: now[0])
    assert not asyncio.run(gate.confirm(PHONE, 1))


def test_link_must_be_known():
    with pytest.raises(ValueError):
        IphoneTransport("x", link="bluetooth-magic")


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="non-Linux guard")
def test_accessory_link_refused_off_linux():
    with pytest.raises(ValueError, match="Linux"):
        IphoneTransport("", link="accessory")


class FakeAccessory:
    started = closed = 0
    def __init__(self, adapter, allowed_address=""):
        self.adapter, self.allowed = adapter, allowed_address
    async def start(self):
        FakeAccessory.started += 1
    async def wait_for_iphone(self, timeout=20):
        return "fake-ble-device"
    async def close(self):
        FakeAccessory.closed += 1


def test_accessory_transport_uses_discovered_device_and_cleans_up(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(bz, "BluezAccessory", FakeAccessory)
    FakeAccessory.started = FakeAccessory.closed = 0
    transport = IphoneTransport("", link="accessory", adapter="hci0")
    assert transport.pair_on_connect is False
    async def run():
        assert await transport.connect_target() == "fake-ble-device"
        assert await transport.connect_target() == "fake-ble-device"
        assert FakeAccessory.started == 1  # advertisement reused across reconnects
        await transport.link_close()
        assert FakeAccessory.closed == 1 and transport.accessory is None
    asyncio.run(run())


def test_worker_closes_link_on_shutdown(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    transport = IphoneTransport("", link="accessory")
    closed = []
    async def link_close():
        closed.append(True)
    transport.link_close = link_close
    transport.stop.set()
    asyncio.run(transport._run())
    assert closed == [True]


def test_connect_link_unchanged():
    transport = IphoneTransport("PHONE-ID")
    assert asyncio.run(transport.connect_target()) == "PHONE-ID"
    with pytest.raises(ValueError):
        IphoneTransport("")


@pytest.mark.skipif(importlib.util.find_spec("dbus_fast") is None, reason="dbus-fast not installed")
def test_dbus_interfaces_and_variant_normalization():
    from dbus_fast import Variant
    plain = bz.normalize({PHONE: {"org.bluez.Device1": {"Connected": Variant("b", True)}}})
    assert plain[PHONE]["org.bluez.Device1"]["Connected"] is True
    gate = bz.PairingGate(lambda *_: False)
    Advertisement, Agent = bz._interfaces("Raven Muse", gate)
    adv = Advertisement().introspect()
    assert {p.name for p in adv.properties} == {"Type", "SolicitUUIDs", "LocalName"}
    agent = Agent().introspect()
    assert {"RequestConfirmation", "RequestAuthorization", "Release", "Cancel"} <= {m.name for m in agent.methods}
