# Release 1.7.0 — music remote only

- Removed Reach/SOS, the lyrics/identify/saved hub and the iOS speech proof; the app is now a music remote only.
- Flat HUD: compact now-playing card that opens one page of Prev / Play-Pause / Next / Vol − / Vol + / Hide, vertically centred on the right edge. SDK Home button hidden.
- Follows the Raven SDK design guide (theme font roles, minimal text, large targets, fade-in).
- Simulator starts in the 60 fps Raw view; the Background (room) view still works.
- Android companion: Reach screens, SMS/location permissions and GATT characteristics removed; built and tested against Spotify on a Galaxy S25 Ultra.
- 210 passed / 1 skipped. See TEST_RESULTS.md.

# Release 1.6.0 — hackathon lyric/recognition MVP

- Continues the supplied v1.4 source, preserving Android QR/BlueZ additions and all original tests.
- Adds original local LRC catalog, timed current/next-line view, Follow/Browse, lyric offset and missing/uncertain states.
- Adds a real, limited three-recording local acoustic matcher; deliberate microphone consent/capture/cancel; explicit file-fixture lane.
- Adds private persistent Saved to Muse bookmarks and provider-search QR codes. No account likes or universal recognition are claimed.
- Includes three original spoken-word demo WAVs, LRC files, generator, external test-stimulus page, and full actual SDK MVP smoke.
- Fixes the inherited voice AsyncRunner callback contract and cover-ready smoke timing; keeps original phone/Android code unchanged.
- Current verification: 228 passed / 1 Linux-appropriate skip; both actual SDK smokes pass; five Kotlin files pass syntax checks. No new native build or real hardware validation is claimed.
- The separate v1.5 tilt/lighting/timer/recap/ad proposal remains unimplemented.

# Historical release 1.3.0 — compact cover art

Based on the delivered Raven-Muse-Control 1.2.0 source ZIP, not a rewrite.

## Added
- 64px artwork/placeholder in the existing compact card, with one parent gaze target.
- Original local demo cover fixtures.
- Optional Android f105 thumbnail extension, background compression, strict chunk validation, final-state recheck and bounded caches.
- iPhone album metadata subscription and an independent opt-in MusicBrainz/Cover Art Archive lookup; default OFF.
- Online-match provenance indicator, strict matching and bounded HTTPS access.
- Artwork setup/protocol/privacy/rights documentation and 67 new tests.

## Preserved
- 256 x 112 compact and 432 x 320 expanded footprints.
- Six 128 x 104 controls, 16px gaps, dwell ring, re-arm guard and idle collapse.
- Phone-owned playback/accounts/output, existing command allowlist and no separate player/library.
- Android authentication and media command framing; old companion compatibility.
- No always-listening microphone; separate cloud voice consent.

## Verification
- 135 Python tests passed with the actual Raven SDK enabled.
- Full actual SDK SimulatorRunApp launch, demo artwork, interaction, captures and clean exit passed.
- All five Kotlin source files passed grammar checks only.
- Android native build, real phone/radio/Prism operation, live artwork-provider calls and commercial rights review remain unverified.

See TEST_RESULTS.md and ARTWORK.md for exact boundaries. The PDF and ZIP contain the same complete source, plus attachment and text-only recovery paths.
