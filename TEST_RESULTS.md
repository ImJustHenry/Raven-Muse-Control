# Test results — v1.7 music remote (2026-11-14)

## Automated (Windows 11, Python 3.12, Raven SDK b0efac7)

- `RMC_TEST_SDK=1 python -m pytest -q`: **210 passed, 1 skipped**. The skip is a Linux-only BlueZ test.
- `python -m tools.sdk_smoke`: passes in the real Raven `SimulatorRunApp` (compact card, expanded controls, idle collapse).

## Android companion

- Built with Temurin JDK 17, Android SDK 35 / build-tools 35.0.0, Gradle 8.11.1 (`gradle --no-daemon assembleDebug`).
- Installed via adb on a Samsung Galaxy S25 Ultra.

## Real phone (Windows laptop BLE → Galaxy S25 Ultra, Spotify)

- Encrypted Bluetooth pairing and per-connection HMAC authentication succeeded.
- Live title, artist, play state and volume were read from the phone.
- Play, pause, next, volume up and volume down were sent; play/pause were confirmed by the phone's own reported state, and Next visibly changed the track.
- Spotify did not offer *Previous* during the test, so that control was correctly disabled.

## Not yet verified

- Real Raven Prism glasses (eye tracking, waveguide display, battery).
- YouTube Music, cover-art transfer, long-running reconnects.
- iPhone (Apple Media Service adapter is included but untested on hardware).
- Real voice recognition (the simulator uses typed input).
