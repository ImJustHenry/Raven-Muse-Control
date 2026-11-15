# Cover artwork — v1.3

## What changed

- A **64 x 64** non-interactive cover appears on the left of the existing **256 x 112** compact card. Title and artist remain on the right; status and progress remain visible. Long text is elided only in the UI. Full title remains available in the expanded Info page and desktop tooltip.
- The entire card is still **one gaze target**. The artwork has transparent mouse/gaze hit handling; selecting it opens controls without sending playback. All expanded control sizes and re-arm safeguards are retained.
- Original geometric DEMO covers change with the simulated track. These are not images of real albums and never imply live phone connectivity.
- Missing, malformed, oversized or unavailable covers show a musical-note placeholder. Playback never depends on an image succeeding.
- Artwork is not an independent music library or streaming feature. No audio, lyrics, Spotify/Google credentials or music catalog UI were added.

## Support matrix — implementation versus validation

| Source | Implemented behavior | Important limitation |
|---|---|---|
| Demo | Original local cover fixtures; no network | Validated in actual SDK widgets/simulator, not a real music session |
| Android | Companion reads exposed ART, ALBUM_ART, then DISPLAY_ICON bitmaps, compresses to JPEG and serves authorized BLE chunks | Native build and real Spotify/YouTube Music bitmap availability still need testing |
| iPhone AMS | Subscribes to album as well as artist/title/duration | Apple's published AMS has no image or artwork URL field |
| Optional iPhone lookup | MusicBrainz exact metadata matching, then CAA front-250 image | OFF by default; requires internet on computer/glasses and explicit consent; mocked tests only |

Android v1.3 deliberately does **not** fetch `content://` or HTTP artwork URIs. If the media session provides only a URI, the card keeps the placeholder. DISPLAY_ICON can be a generic media thumbnail rather than album art; the companion passes through what the player exposes. This is not a guarantee of exact cover availability in either music app.

## Default setup

No configuration change is needed for the demo or Android artwork path. Existing private configs default to artwork enabled, online lookup disabled. Update both the Python app and Android companion to v1.3 for real Android image transfer. Older companions still support playback, with a placeholder.

1. Follow README.md to install the separately authorized Raven SDK and app dependencies.
2. Run `python main.py` in default demo mode. A DEMO cover should appear in the compact card.
3. Use Next/Previous to change simulated covers. Press L and select `missing_artwork` to verify the fallback.
4. Before claiming Android support, build/install the native app and complete the phone checklist below.

The Pillow dependency is now explicit in pyproject.toml and requirements.txt. Use the supported RavenOS runtime; do not replace its Qt installation.

## Optional iPhone online lookup

The simplest setup is `python tools/configure.py`: choose iPhone, enter your BLE identifier, and explicitly answer YES to the separate artwork consent prompt. Playback does not require opting in.

The private JSON keys are:

```json
{
  "artwork_enabled": true,
  "artwork_lookup": "off",
  "online_artwork_consent": false,
  "artwork_contact": ""
}
```

To opt in, change `artwork_lookup` to `musicbrainz`, set `online_artwork_consent` to true, and supply your own public contact URL/email in `artwork_contact`. All three are required for the online path. The app's mode must be `iphone`. The contact identifies the application to MusicBrainz; it is transmitted in the User-Agent and is not a secret. Do not use a private credential as the contact.

Disable online lookup by setting `artwork_lookup` back to `off` or consent to false, then restarting. `artwork_enabled: false` disables all image loading/transfers while retaining the card's musical-note placeholder. It does not stop playback or AMS metadata.

### Data leaving the device

Only after opt-in:
- Song title, artist and album are sent in an HTTPS search query to MusicBrainz. No audio is sent.
- A selected release identifier is sent to Cover Art Archive; image delivery may redirect to Internet Archive infrastructure.
- Those services receive normal connection information such as IP address and the configured contact User-Agent.
- Requests use fixed allowed HTTPS domains, bounded redirects, response-size limits and timeouts. Local/network-private arbitrary URLs and HTTP downgrade requests are rejected.
- Artwork caches live only in process memory. This app writes no cover files or listening-history database, and does not log track queries or image bytes. Service operators have their own logging/retention policies.

### Matching is not identification

The lookup waits for a quiet 0.8-second metadata interval because AMS attributes arrive separately. It requires non-empty title, artist and album and skips metadata marked truncated. A MusicBrainz recording must match normalized title and complete credited artist exactly; at least one associated release must match the album exactly. If both durations are available they must be within 3 seconds. Multiple distinct matching recordings are rejected. No fuzzy-remix or first-result fallback is used.

Even an exact text match cannot prove that a release edition is identical to the phone's. If one recording has multiple releases with that album name, the implementation selects a deterministic release ID. A CAA front cover can therefore differ from the phone thumbnail. The artwork has an **amber dot** for this metadata-matched source, and Info labels it **Online match (not phone art)**. Its tooltip includes the provider and release ID. Missing/ambiguous matches remain placeholders.

No album metadata means no online cover. User-uploaded YouTube content, remixes, unavailable releases, network errors, provider changes and CAA missing covers are expected fallback cases. No live lookup request was executed in the generation sandbox.

### Provider terms and image rights

- MusicBrainz documents its public API as free for non-commercial use; commercial use requires reviewing its current commercial plans/contact process. It requires a meaningful User-Agent and at most one call per second per client application. This implementation serializes calls with at least 1.1 seconds between MusicBrainz request starts.
- Availability from Cover Art Archive does not establish ownership, a blanket image license, or permission to redistribute album art. Review rights and provider terms before public/commercial distribution. This source bundle ships only original synthetic demo art, not downloaded covers.
- No legal clearance, provider service-level guarantee or commercial license is asserted by this handoff. The optional integration is source code for a prototype, not a certification of compliant commercial operation.

## Android image transfer protocol

The original version-1 control/authentication protocol is preserved. The new extension is optional.

| Item | Definition |
|---|---|
| Service | 7c27f100-6baa-4ad0-8e3b-31f62b88ac50 |
| Artwork characteristic | 7c27f105-6baa-4ad0-8e3b-31f62b88ac50 |
| Permissions | Encrypted read/write AND existing per-connection application HMAC authorization |
| STATE additions | `tid`: 16-hex-character full track/session identity; `art`: 16-hex-character thumbnail token or empty |
| Image | 64 x 64 JPEG; hard maximum 16,384 encoded bytes |
| Chunk payload | Up to 480 bytes; response including header is at most 497 bytes |
| Write request | 13 bytes; fits a default 20-byte ATT write payload |
| Read | Frozen response supports OS-managed long characteristic reads at negotiated MTU |

Request layout, little endian:

```text
byte 0       extension version = 1
bytes 1-8    expected 8-byte artwork token
bytes 9-12   unsigned image offset
```

Response layout, little endian:

```text
byte 0       extension version = 1
bytes 1-8    artwork token
bytes 9-12   offset of this payload
bytes 13-16  total encoded JPEG length
bytes 17+    up to 480 JPEG bytes
```

The token is the first 8 bytes of SHA-256 over ASCII `tid` followed by the JPEG bytes. It binds the transfer to the full track identity and permits an integrity check before decoding. This truncated digest is not a replacement for authentication or an audited cryptographic transport design. GATT encryption and the existing HMAC controller proof remain required.

The phone recomputes the current track identity before serving a chunk request. It rejects an outdated token, wrong track, negative/out-of-range offset, unauthorized access, prepared write or wrong request size. The response is frozen until the next request, so a long ATT read cannot splice two chunks together. The Python assembler rejects inconsistent totals, out-of-order/duplicate offsets, version/token mismatches, overflow and more than 16 KiB. Before publishing a completed image, Python rereads STATE and requires the same tid/art pair.

There is one BLE worker. It attempts at most one artwork chunk per loop and skips artwork while a playback command is queued. Artwork reads/writes have one-second operation timeouts. Failures drop the partial image and introduce a 10-second artwork retry delay; they do not intentionally disable playback or disconnect the bridge. Radio/backend errors can still affect the underlying connection. No latency claim is made.

STATE remains at most 512 bytes; image data is never inserted into JSON. Extra fields can reduce the available title/artist string budget; the existing `truncated` flag marks this honestly. A tid hash uses the full metadata so two clipped visible titles do not share a transfer identity.

## Resource limits and thread ownership

| Work | Owner / limit |
|---|---|
| Android bitmap compression | Single background executor; latest pending image replaces older pending work |
| Android inputs | Existing session bitmap only; reject more than 4,194,304 pixels; never recycle the player's bitmap |
| BLE I/O | Existing serialized worker, never Qt main thread |
| Python normalization/lookup | One daemon artwork worker, one replaceable pending job |
| Online response | Maximum 1 MiB; decoded image maximum 4,194,304 pixels; JPEG/PNG/WebP only; no animation |
| Python image output | 64 x 64, metadata-free JPEG <=16 KiB, letterboxed rather than cropping |
| Caches | Memory-only, at most 48 entries each in the Android client and UI artwork manager |
| Negative online results | Cached 60 seconds; positive results 30 minutes |
| UI | Persistent CoverView, QImage painting only; no network or full-resolution image decode in paintEvent |

A metadata change immediately clears the previous displayed image on the next normal UI refresh (150 ms timer, or an explicit refresh). Pending results are tied to a state key; an old job may finish but cannot publish into a different track. Progress/volume/revision-only changes do not trigger downloads. Closing the app prevents result publication and clears caches; an already-running bounded HTTP request may finish on its daemon worker.

## Files changed or added

- `muse/artwork.py`: image validation, assembler, cache, worker and stale-result guard.
- `muse/artwork_lookup.py`: opt-in provider lookup, conservative matching and HTTP boundaries.
- `muse/cover_view.py`: non-interactive cover and fallback painting.
- `muse/demo_art.py`: original local demo covers.
- `muse/model.py`, `demo.py`, `ui.py`, `gaze_target.py`: data fields, art lifecycle, compact arrangement and status-icon placement.
- `muse/android.py`: compatible optional f105 transfer; `muse/iphone.py`: album subscription only, no AMS image fabrication.
- Android `ArtworkStore.kt`, `MediaAccess.kt`, `BridgeService.kt`: bounded background compression, state descriptor, authorized frozen chunks.
- `main.py`, config, setup tool, dependency/version files, tests and smoke test.
- Existing test assertions for compact text width were updated because the cover reserves 64 pixels. Expanded gaze-target and interaction assertions were retained.

## Acceptance checklist — all hardware items remain HOLD

1. Build Android with the documented toolchain; install v1.3 and verify versionCode 2 upgrade behavior.
2. For Spotify and YouTube Music separately, log whether ART/ALBUM_ART/DISPLAY_ICON exposes a bitmap. Verify real title/cover correspondence.
3. Test BLE MTU 23 and a larger negotiated MTU. Confirm complete 497-byte characteristic reads on the actual BlueZ/CoreBluetooth/Windows backend.
4. Skip rapidly during image transfer; verify no previous cover appears with the next title. Test long/Unicode titles that truncate identically.
5. Pause/next while images load; measure control responsiveness rather than relying on the fake-BLE tests.
6. Revoke media/Bluetooth access, stop the bridge, rotate the secret and reconnect; no unauthorized artwork read should succeed.
7. Test missing artwork and URI-only sessions; placeholder is expected, not a defect to hide with fabricated data.
8. Verify iPhone album attribute delivery, with lookup OFF first. Playback must work independently of cover lookup.
9. After explicit consent and terms review, test real MusicBrainz/CAA requests from the development computer, then RavenOS. Test offline/404/503 and title/artist/album ambiguity. Confirm the amber matched-art marker.
10. Test brightness/cover recognizability and title elision on the actual optical display. Confirm the cover remains a single parent-card hit region and does not interfere with re-arming.
11. Measure memory/battery/reconnection behavior over a realistic listening session.

## Primary references inspected for this change

- Android MediaMetadata bitmap keys: https://developer.android.com/reference/android/media/MediaMetadata
- Apple AMS documented attributes: https://developer.apple.com/library/archive/documentation/CoreBluetooth/Reference/AppleMediaService_Reference/Appendix/Appendix.html
- MusicBrainz API identification, rate limits and non-commercial/commercial distinction: https://musicbrainz.org/doc/MusicBrainz_API
- MusicBrainz search fields and Lucene escaping: https://musicbrainz.org/doc/MusicBrainz_API/Search
- Cover Art Archive thumbnail/redirect interface: https://musicbrainz.org/doc/Cover_Art_Archive/API
- Raven framework pinned for simulator checks: https://github.com/RavenResonance/raven-framework/tree/b0efac742ed0ec6c9e76e1c52868ebd39afd531f

Documentation research supports the implementation approach. It is not proof that live services, phone apps or Raven hardware have passed acceptance testing.
