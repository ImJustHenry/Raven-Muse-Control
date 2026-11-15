"""Run on computer: python main.py. Deploy with Raven: python main.py deploy."""
import json
import os
from pathlib import Path


def load_config():
    private = Path.home() / ".config" / "raven-muse-control" / "config.json"
    path = Path(os.environ.get("RMC_CONFIG", str(private)))
    if not path.exists():
        path = Path(__file__).with_name("config.example.json")
    config = json.loads(path.read_text())
    if os.environ.get("RMC_MODE"):
        config["mode"] = os.environ["RMC_MODE"]
    if config.get("mode") not in {"demo", "iphone", "android"}:
        raise ValueError("mode must be demo, iphone, or android")
    return config


def make_transport(config):
    mode = config.get("mode", "demo")
    if mode == "demo":
        from muse.mvp_demo import CatalogDemoTransport
        return CatalogDemoTransport()
    if mode == "iphone":
        from muse.iphone import IphoneTransport
        return IphoneTransport(config.get("phone_address", ""), config.get("pair_on_connect", False),
                               config.get("iphone_link", "connect"),
                               config.get("bluetooth_adapter", "hci0"))
    from muse.android import AndroidTransport
    return AndroidTransport(config.get("phone_address", ""), config.get("android_secret_hex", ""),
                            config.get("pair_on_connect", False), config.get("artwork_enabled", True) is True)


if __name__ == "__main__":
    from raven_framework.core.run_app import RunApp
    from muse.ui import MuseApp
    from muse.sim_display import schedule_fast_preview
    config = load_config()

    def make():
        schedule_fast_preview()
        return MuseApp(config, make_transport(config))

    RunApp.run(make,
               app_id=os.environ.get("RMC_APP_ID", config.get("app_id", "")),
               app_key=os.environ.get("RMC_APP_KEY", config.get("app_key", "")))
