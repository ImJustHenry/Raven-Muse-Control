# Current scope (2026-11-14, user decision) — overrides everything below

The user asked to remove Reach/SOS and the Muse hub menu; keep only the music controls.
- Removed from the Python app: muse/reach_ui.py, reach_core.py, reach_link.py, experience.py (lyrics/identify/saved hub), reach_main.py, tools/reach_smoke.py, tools/mvp_smoke.py and their tests. Android transport no longer creates a ReachLink. The original v1.7 archive (../Raven-Muse-Control_Source_v1.7_Reach.zip) still has them.
- UI is now: compact now-playing card → one flat expanded page of Previous / Play-Pause / Next / Vol - / Vol + / Hide. No sub-menus. Voice remains on the V key.
- Do not re-add Reach, the hub, or menu pages unless the user asks. Sections below about Reach/hub are historical.
- The Android companion (android/) still contains Reach screens/permissions; it has not been stripped or rebuilt.
- UI follows the SDK design guide ../raven-framework/AGENTS.md: theme font roles only (TextBox font_type small/body/headline; button labels use RAVEN_CORE body size), minimal text (no instruction/hint line), right-side placement, large targets, fade_in at end of __init__. Keep it that way.
- User choices (2026-11-14) that override the right-side/corner guidance: the HUD is vertically centred on the right edge (`ui_corner` default "center_right"; "center" and corners still selectable), and the SDK Home (four-circle) button is hidden in MuseApp.__init__. Enter still exits in the simulator.
- Android companion: Reach removed (Reach*.kt, SMS/location permissions, Reach GATT characteristics). Built 2026-11-14 on Windows with Temurin JDK 17, Android SDK at C:\Android\Sdk (platform 35, build-tools 35.0.0), Gradle at C:\Android\gradle-8.11.1 (`gradle --no-daemon assembleDebug`; android/local.properties points at the SDK). Installed on the user's Galaxy S25 Ultra via adb.
- Real-phone result (2026-11-14, Windows bleak → S25 Ultra, Spotify): authenticated BLE link, now-playing metadata and volume read, play and pause each confirmed by phone-reported state. Not yet exercised: next/previous/volume commands, YouTube Music, artwork, reconnect. Spotify reported no `previous` capability at that time.
- Windows gotcha: Windows cached the phone's old GATT table (phone was already paired for audio), hiding the Raven service. Fix was bleak `unpair()` then reconnect + `pair()` (accept on phone). Uncached discovery (`use_cached_services=False`) fails on this phone with "Catastrophic failure".
- Run with `python main.py`. muse/sim_display.py switches the desktop simulator to its Raw view at 60 fps (the SDK's blended preview runs ~16 fps); RMC_SIM_PREVIEW=blend restores it.

# Muse + Raven Reach: implementation context — v1.7

(Historical. The REACH_*.md docs, ios-speech-proof/, MVP_ENGINEERING.md and SOURCE_MANIFEST*.json were deleted 2026-11-14 during repo cleanup; they remain in the original v1.7 zip.)

Reach is a distinct mode, defaulting to simulation. Its source implements two-phase reviewed requests, fixed phrases, phone-location disclosure, authenticated/encrypted BLE request/response handling, duplicate guards, and explicit unknown-delivery states. Android native paths are not built/device-validated here. Its real calls are phone-dialer notification handoffs, not hands-free call control; local TTS is not cellular uplink speech. Incoming call control and active call states are simulated only. The iPhone speech proof is separate and unverified, not iPhone parity. Emergency functionality is absent/disabled.

Preserve the music/lyrics/discoveries project. Do not treat user enablement flags as a verification result; do not infer injury or inability to speak; do not add automated emergency calls or call recording. No automatic retry after an ambiguous send and no automatic hangup on gaze loss.

The source archive includes the complete code and original demo media. SDK dependency is separately authorized at b0efac742ed0ec6c9e76e1c52868ebd39afd531f. Use the native build/device plan before reporting real phone success. The previous Android build evidence is historical; v1.7 changes native code and permissions.

---

# Historical music implementation context — v1.6 (superseded where noted above)

## Current handoff — read this first

This source implements the explicitly requested hackathon lyric/recognition/bookmark MVP on the supplied v1.4 source, not the separate v1.5 sensor/timer wishlist. Read README.md and MVP_ENGINEERING.md first; their v1.6 scope/defaults override conflicting historical notes below.

- Preserve the inherited Android QR secret pairing and Linux/iPhone accessory work. The v1.4 PDF reports an Android build/install; all Android source is unchanged here. Real control remains unverified.
- The default demo transport is now CatalogDemoTransport, a no-audio fake-phone clock for three original spoken-word recordings. The old DemoTransport remains for baseline tests.
- Local catalog data and LRC parsing live in muse/lyrics.py and muse/demo_catalog/. No commercial lyric API or scraping exists. Real-phone lyric integration is OFF by default.
- muse/recognition.py actually matches local waveforms; only the supplied three recordings are supported. Listen uses deliberate, consented six-second SDK microphone capture. Demo clip is a separate labelled FIXTURE lane, never a claim of live microphone recognition.
- Ambient timing is independent of phone state and expires after 20 seconds from capture start. Never fake pause/skip tracking of an external speaker.
- Saved to Muse is private local metadata (muse/discoveries.py), not a streaming library or service-side like. Search QR codes are search links, not exact tracks or successful provider saves.
- ExperienceMixin adds persistent lyric/identify/saved pages using real SDK buttons. No rebuild on refresh, no QWidget.render override, one action per dwell and navigation re-arming remain essential.
- Original demo audio is only played by an external test harness, not by the glasses app. No new network calls were introduced.
- Pinned SDK AsyncRunner completion receives no arguments; use a captured result container. The inherited voice callback was corrected accordingly.
- Current test result: 228 passed, 1 platform-appropriate skip; both actual SDK smokes pass. Digital acoustic fixtures and fake microphones do not validate real microphone/room/optical behavior.
- This release is 1.6.0 to avoid colliding with the attached, unimplemented v1.5 tilt/lighting proposal. The unchanged Android companion retains its v1.3.1/versionCode 3 metadata.

## Historical remote/artwork guidance below

These sections describe the inherited v1.3 architecture. Their old version, demo-track, native-build and test-status statements are historical. Retain the relevant Bluetooth/security/UI safeguards, but use the v1.6 summary and TEST_RESULTS.md for present scope and evidence.

## Product decision — do not lose this

The user named the project **Raven-Muse-Control**. It is a hands-free REMOTE for Spotify and YouTube Music already running on an iPhone or Android phone. The phone keeps its existing account, subscription, streaming engine, and output route. Muse reads available now-playing data and sends supported media controls.

Do not reintroduce a separate music library, a native audio player, a music catalog backend, account OAuth, playlist editing, YouTube scraping, Spotify Web API playback, smart-home controls, or car controls. Those are outside the corrected scope. Three demo tracks in muse/demo.py are simulated state fixtures; they are not playable music or a user library.

## Current UI requirement — v1.3 compact player with cover art

The user explicitly wants the music UI small in the corner of the eye. The default is a 256 x 112 pixel bottom-right card inside the existing display, not a large centered page. The whole card is one gaze target. It expands to 432 x 320 controls in the same corner. All six targets are 128 x 104 with 16-pixel hitbox gaps, vector icons and labels; the primary play/pause target is accented. Tools and status use that same expanded footprint. The rest of the app canvas stays transparent/unlit; retain the SDK's Home control.

The v1.2 paint layer (`muse/gaze_target.py`) subclasses the real Raven Button and preserves its input and dwell/cancellation timers. It adds a clear focus outline, a progress ring driven by the SDK's actual progress, and a short selection check. The check means input was accepted, never that phone playback has been confirmed. Preserve this distinction. The quiet source line retains a visible DEMO marker; real music metadata is not rewritten.

Do not shrink three playback hit regions into the compact card: Raven's published gaze accuracy is approximate, and tiny adjacent targets would be unreliable. Opening the card never dispatches a music command; a gaze/pointer re-arm guard prevents accidental activation under the newly expanded panel. Preserve one activation per dwell hold.

Hide/Escape and inactivity outside the panel return it to compact state. Auto-collapse is suspended during interaction, recording, recognition, and dialogs. Physical gaze-away behavior still needs hardware validation. Selecting Voice collapses the panel before the bounded microphone capture; there is no always-on wake-word listener. See muse/corner.py for geometry and the corner SDK tests for behavior.

The v1.3 cover-art change extends the Android bridge and subscribes to the iPhone AMS album attribute; it adds no streaming features. Preserve the 64 x 64 non-interactive cover on the compact card. `muse/artwork.py` owns a bounded memory cache and single background worker; `cover_view.py` paints on Qt; `artwork_lookup.py` provides consent-gated MusicBrainz/CAA lookup for iPhone only. `ArtworkStore.kt` compresses exposed Android bitmaps off the main thread. See ARTWORK.md for the f105 chunk protocol. New metadata must clear the old cover; stale replies must not be published. An amber marker means metadata-matched online art, not an exact phone image. Online lookup defaults OFF; never enable it silently or replace a missing image with an invented cover. The original geometric demo images are explicitly simulated. Existing configs still work. App coordinates do not change the physical waveguide position.

## User-facing scope

- Core: play, pause, next, previous, title, artist, reported play state.
- Conditional: volume, duration/progress, skip forward/back.
- Optional iPhone-only where advertised: shuffle/repeat cycle commands.
- Voice and gaze are central. Gaze targets are large, and holding a target should not repeatedly skip songs.
- The user must be able to test the same app on a computer through Raven Framework's actual SDK simulator, without owning glasses or providing credentials.
- A second computer test lane controls a real phone through the computer's BLE adapter. This is different from demo simulation.

## Current architecture

- main.py selects a transport and calls the real vendor RunApp.run.
- muse/ui.py subclasses the real RavenApp and uses SDK Button/TextBox widgets. Qt's QWidget.render must remain untouched; use build_page for layout.
- muse/model.py is the shared capability-driven state model. None means unknown.
- muse/demo.py is an explicit no-audio fake phone for computer tests.
- muse/iphone.py uses the public Apple Media Service BLE protocol directly. There is no iPhone native player app to build.
- muse/android.py talks to the native Android BLE companion with an authenticated custom protocol.
- Android MediaAccess uses an enabled notification listener to obtain allowed media sessions, selects only Spotify/YouTube Music, and dispatches supported controls.
- Android BridgeService is a connectedDevice foreground service, not a mediaPlayback service. The companion has no INTERNET permission.
- muse/voice.py implements exact command parsing, bounded WAV preparation, local Vosk or opt-in cloud transcription. Typed input is a simulator test seam, not actual speech recognition.

No app-to-app command handler assumes that a successful transport write means playback changed. The display continues to use actual reported state. Stale/unsupported commands fail safely, and reconnection clears pending actions.

## What was actually tested in this session

- Python core tests, including parser, model, demo, Android protocol, AMS parsing, fake-GATT adapters, secret/nonce framing, scope boundaries, and WAV preparation.
- Real Raven SDK widget tests: compact default, expand without playback, gaze re-arm, actual click/dwell controls, metadata elision, disabled actions, typed commands while compact, source changes, same-corner tool pages, auto-collapse guards, and voice collapsing the panel.
- The full vendor RunApp simulator was launched in software-rendered Linux mode, exercised, captured, and closed successfully. sdk-smoke.json reports real_sdk_window=true, demo_transport=true, physical_phone=false.
- Kotlin grammar parsing passed for all five native source files. This is NOT a Gradle/Android SDK compilation result.
- Artwork tests include bounded image processing, consent defaults, matching, HTTP host/redirect/byte/time boundaries, fake-BLE chunk transfer, stale-track rejection, command priority, placeholder rendering and non-interactive cover hit testing. Online HTTP tests are mocks, not live MusicBrainz/CAA verification.
- Refer to TEST_RESULTS.md for the exact final test count and environment details.

Not tested: real Bluetooth radios, iPhone AMS availability, Android native compilation/installation, actual music-app compatibility, microphone capture, Vosk/OpenAI recognition, optical gaze accuracy, battery life, or phone background/power-management behavior. Do not mark these complete based on a mock or screenshot.

## Start by reproducing, not rewriting

1. Read README.md and TEST_RESULTS.md.
2. Obtain permission for Raven's proprietary SDK. Install the pinned reference revision specified in README.md beside the project.
3. Activate a clean Python 3.11/3.12 venv, install the SDK and this project with test dependencies.
4. Run python main.py; confirm DEMO is visible.
5. Run the core tests, RMC_TEST_SDK=1 python -m pytest -q, and python -m tools.sdk_smoke.
6. Build android/ with JDK 17, SDK 35, Gradle 8.11.1, AGP 8.9.2, Kotlin 2.1.20. Fix any SDK/API type errors; grammar checking is not enough.
7. Install on an Android 12+ phone supporting BLE advertising. Use README's permission/pairing steps. Test Spotify and YouTube Music separately.
8. Test the iPhone AMS adapter with an actual iPhone and supported OS BLE stack.
9. Provision private configuration on the glasses, enable a real voice backend, and run the physical acceptance matrix.

## The highest-priority next engineering work

1. Native Android build and real-phone GATT validation, especially encrypted pairing, authenticated reads, MTU fragmentation, CCCD subscription, reconnect, and permission revocation.
2. iPhone AMS publishing/bonding on the intended computer OS and RavenOS; optional characteristic support; Service Changed handling; command capability notifications.
3. Real Spotify/YouTube Music test matrix, including ads/skip limits, no active session, paused/locked phone, app switches, and fixed-volume routes.
4. End-to-end voice using the SDK microphone plus a compatible offline model or explicitly consented cloud service. The default typed dialog is not a shipping glasses voice solution.
5. Long-running disconnect/battery/readability testing. Do not claim a measured latency or runtime until you measure it.

## Important implementation constraints

- Preserve the SDK's native QWidget.render; an early smoke test caught an accidental override. The code now uses build_page, and a regression test protects it.
- Do not rebuild the page every timer tick; that resets dwell interaction. Update persistent labels and button states.
- Keep BLE I/O off Qt's main thread. BleTransport owns one worker and a bounded, expiring queue.
- Keep reported playback state separate from command-forwarding acknowledgments.
- Check the active player and advertised capabilities before dispatching. Android commands also bind to an expected player code.
- Do not continuously record. Use bounded, deliberate voice input; do not log transcripts or private keys.
- Do not read notification bodies. Notification listener access is used only to obtain allowed media-session controllers.
- Do not introduce insecure HTTP, a public control endpoint, raw shell commands, accessibility screen scraping, or opaque third-party music wrappers as shortcuts.
- Bluetooth alone is not an authorization policy. Preserve the Android encrypted GATT + per-connection HMAC proof + sequence checks + secret rotation.
- The iPhone path follows Apple's AMS protocol, not the Android custom protocol.

## Configuration and secrets

The default private config is ~/.config/raven-muse-control/config.json, outside the repository. RMC_CONFIG can select a different private path. tools/configure.py collects the Android secret using a hidden prompt and never prints it. The Android app protects that secret with AndroidKeyStore and marks its screen secure.

Use RMC_APP_ID and RMC_APP_KEY for private SDK deployment credentials, and OPENAI_API_KEY only if cloud voice is explicitly enabled. Never add real phone addresses, keys, account credentials, microphone clips, or private configs to a refreshed PDF/ZIP or this file. The example config must remain empty for those values.

## Handoff and recovery

All original app source is in the ZIP. The PDF provides context, source listings, the same ZIP as an attachment, and a text fallback. Recover using tools/recover_pdf.py and verify SOURCE_MANIFEST.json. Do not copy PDF line numbers or continuation prefixes into source files. Do not replace missing source with guesses; restore the archive.

The intended deliverable is a validated, capability-aware music remote with an excellent SDK demo and real-phone adapters, not a claim that every phone/app combination has already passed testing.
