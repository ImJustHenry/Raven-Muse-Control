# Raven Muse Control

**A hands-free music remote for Raven Prism smart glasses.** Spotify or YouTube Music keeps playing on your phone; you see what's playing in the corner of your eye and control it by looking at a control and holding your gaze (dwell-to-click).

- A small now-playing card (cover art, title, artist, progress) sits on the right side of the display.
- Look at the card to open one page of six large controls: **Prev · Play/Pause · Next · Vol − · Vol + · Hide**.
- Commands go to the phone over an authenticated, encrypted Bluetooth LE link. The display only shows what the phone *reports*; a sent command is never shown as "done" until the phone confirms it.
- No music library, no streaming, no accounts, no internet permission on the phone app.

You can run it two ways:

| Mode | Needs | What it does |
|---|---|---|
| **Demo** (default) | A computer | Raven SDK simulator with a fake, silent phone. Good for trying the UI. |
| **Android phone** | A computer with Bluetooth LE + an Android 12+ phone | Controls real Spotify / YouTube Music on your phone. |

---

## 1. Demo in the simulator (about 10 minutes)

### Requirements
- Windows, macOS or Linux
- Python 3.11 or 3.12 ([python.org](https://www.python.org/downloads/), or on Windows `winget install Python.Python.3.12`)
- Git

### Install

Put this project and the Raven Framework side by side:

```
some-folder/
├── raven-framework/                      ← Raven SDK
└── Raven-Muse-Control_Source_v1.7_Reach/ ← this project
```

```bash
# 1. Get the Raven Framework at the tested commit
git clone https://github.com/RavenResonance/raven-framework.git
git -C raven-framework checkout b0efac742ed0ec6c9e76e1c52868ebd39afd531f

# 2. Create a virtual environment inside this project
cd Raven-Muse-Control_Source_v1.7_Reach
python -m venv .venv
```

Then install (pick your OS):

```bash
# Windows (PowerShell) — no activation needed
.venv\Scripts\python.exe -m pip install -e ..\raven-framework
.venv\Scripts\python.exe -m pip install -e ".[test]"

# macOS / Linux
.venv/bin/python -m pip install -e ../raven-framework
.venv/bin/python -m pip install -e ".[test]"
```

> The Raven Framework is proprietary software from Raven Resonance. Install it from their repository; do not redistribute it.

### Run

```bash
.venv\Scripts\python.exe main.py        # Windows
.venv/bin/python main.py                # macOS / Linux
```

The simulator window opens with a **DEMO** card on the right. Your mouse cursor stands in for your gaze:

- **Hover and hold** over the card to open the controls; hover and hold over a control to select it (a ring fills while you hold).
- **Click** also selects (stands in for a double blink).

Keyboard shortcuts (simulator only):

| Key | Action |
|---|---|
| Space | Play / pause |
| ← / → | Previous / next track |
| ↑ / ↓ | Volume up / down |
| E / Esc | Open / hide the controls |
| V | Voice command (typed in the simulator, e.g. "next song") |
| D | Demo: switch between Spotify and YouTube Music |
| L | Demo: simulate disconnects, missing metadata and other edge cases |
| Enter | Exit the app |

The simulator starts in its **Raw** view at 60 fps. Use the **Background** button at the bottom to see the HUD over a real room video (this view is slower because it blends every frame). Set `RMC_SIM_PREVIEW=blend` to start in that view.

---

## 2. Control a real Android phone

Tested on a Samsung Galaxy S25 Ultra with Spotify, from a Windows laptop. The phone runs a small companion app that exposes its media session over Bluetooth LE; the computer (later, the glasses) connects to it.

### 2a. Build the phone app

Requirements: **JDK 17**, **Android SDK platform 35 + build-tools 35.0.0**, **Gradle 8.11.1**. Android Studio provides all of these; on the command line:

```bash
cd android
# tell Gradle where the Android SDK is (example path)
echo sdk.dir=C\:\\Android\\Sdk > local.properties
gradle --no-daemon assembleDebug
```

The APK is written to `android/app/build/outputs/apk/debug/app-debug.apk`.

### 2b. Install it

Enable **Developer options → USB debugging** on the phone, connect it with USB, then:

```bash
adb install android/app/build/outputs/apk/debug/app-debug.apk
```

If an older Raven-Muse-Control app is already installed with a different signature, uninstall it first (`adb uninstall app.ravenmuse.control`).

### 2c. Set up the phone app

Open **Raven-Muse-Control** on the phone and tap, in order:

1. **Grant Nearby devices** — Bluetooth permission.
2. **Grant notification / media access** — lets the app see Spotify / YouTube Music playback controls. It does not read your notifications.
3. **Start Bluetooth control** — the status line should say *Advertising; pair the controller*.

### 2d. Pair the computer with the phone

On the phone tap **3. Show controller pairing secret**. On the computer run:

```bash
.venv\Scripts\python.exe tools\scan_secret.py
```

Hold the phone's QR code up to the computer's webcam (20–30 cm). The tool reads the secret, finds the phone over Bluetooth and saves both to a private config file (`~/.config/raven-muse-control/config.json`). The secret is never printed. No webcam? Use `--image photo.jpg`, or `python tools/configure.py` to type it in.

### 2e. Run

Start a song in Spotify or YouTube Music, then:

```bash
.venv\Scripts\python.exe main.py
```

The first time, the phone asks to **pair** with the computer — accept it. The card then shows your real song; the controls work your phone.

To go back to the demo without changing the config: `RMC_MODE=demo` (PowerShell: `$env:RMC_MODE="demo"`).

### Troubleshooting

| Problem | Fix |
|---|---|
| Card says *Connecting* forever | On the phone, tap **Start Bluetooth control** again; keep Bluetooth on. |
| *Bluetooth ValueError* (Windows) and the phone was already paired to this PC for audio | Windows cached the phone's old Bluetooth service list. Remove the phone in **Settings → Bluetooth & devices**, run `main.py` again and accept the pairing prompt on the phone. |
| A control is greyed out | The music app isn't offering that action right now (for example Spotify sometimes hides *Previous*). |
| *Open Spotify or YouTube Music* | Start playback in one of them; choose the target in the phone app's *Control target* menu if both are open. |
| Pairing secret leaked | Phone app → **Revoke controller / rotate secret**, then pair again. |

---

## 3. Configuration

`config.example.json` holds the defaults; your private copy lives at `~/.config/raven-muse-control/config.json` (or set `RMC_CONFIG`).

| Key | Default | Meaning |
|---|---|---|
| `mode` | `demo` | `demo`, `android` or `iphone` |
| `phone_address` | | Phone Bluetooth identifier (set by `scan_secret.py`) |
| `ui_corner` | `center_right` | HUD position: `center_right`, `center`, `bottom_right`, `bottom_left`, `top_right`, `top_left` |
| `dwell_ms` | `1100` | How long to hold your gaze to select (700–2200) |
| `auto_collapse_seconds` | `6` | Controls fold back to the card after you look away (2–30) |
| `voice_backend` | `typed` | `typed` (simulator), `vosk` (offline) or `openai` (needs `cloud_voice_consent: true`) |
| `artwork_enabled` | `true` | Show cover art from the phone |

Never commit or share the private config — it contains the pairing secret.

---

## 4. Tests

```bash
# Windows PowerShell
$env:QT_QPA_PLATFORM="offscreen"; $env:RMC_TEST_SDK="1"
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m tools.sdk_smoke
```

Expected: 210 passed, 1 skipped (a Linux-only Bluetooth test).

---

## 5. What has and hasn't been verified

**Verified**
- Full test suite and SDK smoke test in the Raven simulator (Windows 11, Python 3.12).
- Android companion builds (JDK 17, SDK 35, Gradle 8.11.1) and installs on a Galaxy S25 Ultra.
- Real phone over Bluetooth LE from Windows: encrypted pairing, authenticated link, live now-playing data, and play/pause confirmed by the phone's own reported state.

**Not yet verified**
- On actual Raven Prism glasses (real eye tracking, display, battery).
- Next / previous / volume and YouTube Music on a real phone, cover-art transfer, long-running reconnects.
- iPhone: an Apple Media Service adapter is included (`mode: iphone`) but has not been tested on hardware.
- Real voice recognition (the simulator uses typed input).

---

## 6. How it works

```
 Raven glasses / simulator                           Android phone
┌───────────────────────────┐   Bluetooth LE    ┌──────────────────────────────┐
│ main.py → MuseApp (muse/ui.py)                │ BridgeService (GATT server)   │
│  gaze targets, card, controls │ ◄──────────►  │  HMAC challenge per connection│
│ AndroidTransport            │  encrypted +   │  sequence-checked commands    │
│  (muse/android.py)          │  authenticated │ MediaAccess → Spotify / YTM   │
└───────────────────────────┘                  └──────────────────────────────┘
```

- `main.py` — entry point; picks the demo, Android or iPhone transport.
- `muse/ui.py` — the HUD (compact card + one page of controls) on the real Raven SDK widgets.
- `muse/gaze_target.py` — large gaze buttons with focus outline, dwell ring and selection check.
- `muse/android.py`, `muse/ble_base.py` — Bluetooth link: one background worker, bounded queue, no command replay after reconnect.
- `muse/iphone.py` — Apple Media Service adapter (untested on hardware).
- `muse/sim_display.py` — desktop-only simulator speed-up.
- `android/` — the companion app (Kotlin).

### Privacy and safety
- The phone app has no internet permission and reads only Spotify / YouTube Music playback sessions.
- Each connection is authenticated with a 32-byte secret kept in the Android Keystore; Bluetooth pairing alone is not enough to control the phone.
- Commands are never replayed after a reconnect, and the UI never claims a change the phone hasn't reported.
- No background microphone; voice is a deliberate, short capture.
