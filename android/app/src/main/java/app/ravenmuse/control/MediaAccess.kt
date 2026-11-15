package app.ravenmuse.control

import android.app.NotificationManager
import android.content.ComponentName
import android.content.Context
import android.media.AudioManager
import android.media.MediaMetadata
import android.media.VolumeProvider
import android.media.session.MediaController
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import android.os.SystemClock
import android.service.notification.NotificationListenerService
import android.view.KeyEvent
import org.json.JSONArray
import org.json.JSONObject

// Deliberately does not inspect notification bodies, messages, senders, or attachments.
class MuseNotificationListener : NotificationListenerService()

class MediaAccess(private val context: Context) {
    private val artwork = ArtworkStore()
    fun close() = artwork.close()
    private fun trackId(c: MediaController, meta: MediaMetadata?): String {
        val identity = JSONArray().put(c.packageName).put(c.sessionToken.hashCode())
            .put(meta?.getString(MediaMetadata.METADATA_KEY_MEDIA_ID) ?: "")
            .put(meta?.getString(MediaMetadata.METADATA_KEY_TITLE) ?: "")
            .put(meta?.getString(MediaMetadata.METADATA_KEY_ARTIST) ?: "")
            .put(meta?.getString(MediaMetadata.METADATA_KEY_ALBUM) ?: "")
            .put(meta?.getLong(MediaMetadata.METADATA_KEY_DURATION) ?: 0)
        return ArtworkStore.hex(ArtworkStore.digest(identity.toString().toByteArray(Charsets.UTF_8)).copyOfRange(0, 8))
    }
    fun artworkChunk(token: ByteArray, offset: Int): ByteArray? {
        val c = controller() ?: return null
        return artwork.chunk(trackId(c, c.metadata), token, offset)
    }
    companion object {
        val players = mapOf("com.spotify.music" to "Spotify",
            "com.google.android.apps.youtube.music" to "YouTube Music")
        val operations = mapOf(1 to "play", 2 to "pause", 3 to "toggle", 4 to "next",
            5 to "previous", 6 to "volume_up", 7 to "volume_down", 8 to "forward", 9 to "back")
    }
    fun permission(): Boolean = context.getSystemService(NotificationManager::class.java)
        .isNotificationListenerAccessGranted(ComponentName(context, MuseNotificationListener::class.java))

    private fun controller(): MediaController? {
        if (!permission()) return null
        val manager = context.getSystemService(MediaSessionManager::class.java)
        val allowed = manager.getActiveSessions(ComponentName(context, MuseNotificationListener::class.java))
            .filter { players.containsKey(it.packageName) }
        val preference = context.getSharedPreferences("muse", Context.MODE_PRIVATE)
            .getString("preferred", "auto")
        if (preference != "auto") return allowed.firstOrNull { it.packageName == preference }
        val playing = allowed.filter { it.playbackState?.state == PlaybackState.STATE_PLAYING }
        if (playing.size > 1) return null // ambiguous: choose a target explicitly on the phone
        return playing.firstOrNull() ?: allowed.firstOrNull()
    }
    private fun capabilities(c: MediaController): List<String> {
        val s = c.playbackState ?: return emptyList()
        val bits = s.actions
        val result = mutableListOf<String>()
        val map = mapOf("play" to PlaybackState.ACTION_PLAY, "pause" to PlaybackState.ACTION_PAUSE,
            "toggle" to PlaybackState.ACTION_PLAY_PAUSE, "next" to PlaybackState.ACTION_SKIP_TO_NEXT,
            "previous" to PlaybackState.ACTION_SKIP_TO_PREVIOUS)
        for ((name, bit) in map) if (bits and bit != 0L) result += name
        if (bits and PlaybackState.ACTION_SEEK_TO != 0L && s.position >= 0) result += listOf("forward", "back")
        if (c.playbackInfo.volumeControl != VolumeProvider.VOLUME_CONTROL_FIXED) {
            result += listOf("volume_up", "volume_down")
        }
        return result
    }
    private fun position(c: MediaController): Long? {
        val s = c.playbackState ?: return null
        if (s.position < 0) return null
        val extra = if (s.state == PlaybackState.STATE_PLAYING && s.lastPositionUpdateTime > 0)
            ((SystemClock.elapsedRealtime() - s.lastPositionUpdateTime).coerceAtLeast(0) * s.playbackSpeed).toLong() else 0L
        val value = (s.position + extra).coerceAtLeast(0)
        val duration = c.metadata?.getLong(MediaMetadata.METADATA_KEY_DURATION) ?: 0
        return if (duration > 0) value.coerceAtMost(duration) else value
    }
    private fun clip(value: String, bytes: Int): String {
        var end = value.length
        while (end > 0 && value.substring(0, end).toByteArray(Charsets.UTF_8).size > bytes) end--
        if (end > 0 && value[end - 1].isHighSurrogate()) end--
        return value.substring(0, end)
    }
    fun snapshot(revision: Int, message: String): ByteArray {
        val c = try { controller() } catch (_: SecurityException) { null }
        val result = JSONObject().put("v", 1).put("rev", revision)
        if (c == null) {
            artwork.clear()
            return result.put("player", "").put("title", "").put("artist", "")
                .put("caps", JSONArray()).put("playing", JSONObject.NULL)
                .put("message", if (permission()) "Open Spotify or YouTube Music; select target" else "Grant notification/media access")
                .toString().toByteArray(Charsets.UTF_8)
        }
        val meta = c.metadata
        val tid = trackId(c, meta)
        // Prefer actual media/album artwork. Only already-exposed bitmaps are
        // accepted; content:// or HTTP URIs are not dereferenced in this release.
        val bitmap = meta?.getBitmap(MediaMetadata.METADATA_KEY_ART)
            ?: meta?.getBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART)
            ?: meta?.getBitmap(MediaMetadata.METADATA_KEY_DISPLAY_ICON)
        result.put("tid", tid).put("art", artwork.select(tid, bitmap))
        val title = meta?.getString(MediaMetadata.METADATA_KEY_TITLE) ?: ""
        val artist = meta?.getString(MediaMetadata.METADATA_KEY_ARTIST) ?: ""
        val duration = meta?.getLong(MediaMetadata.METADATA_KEY_DURATION) ?: 0
        val playback = c.playbackState
        val playing = when (playback?.state) {
            PlaybackState.STATE_PLAYING -> true
            PlaybackState.STATE_PAUSED, PlaybackState.STATE_STOPPED -> false
            else -> null
        }
        val pi = c.playbackInfo
        result.put("player", players[c.packageName]).put("title", clip(title, 80))
            .put("artist", clip(artist, 48)).put("playing", playing ?: JSONObject.NULL)
            .put("position", position(c)?.div(1000.0) ?: JSONObject.NULL)
            .put("duration", if (duration > 0) duration / 1000.0 else JSONObject.NULL)
            .put("rate", playback?.playbackSpeed?.takeIf { it.isFinite() } ?: 0f)
            .put("volume", if (pi.maxVolume > 0) pi.currentVolume.toDouble() / pi.maxVolume else JSONObject.NULL)
            .put("caps", JSONArray(capabilities(c))).put("message", clip(message, 48))
            .put("truncated", clip(title, 80) != title || clip(artist, 48) != artist)
        var raw = result.toString().toByteArray(Charsets.UTF_8)
        var budget = 24
        while (raw.size > 500 && budget >= 0) {
            result.put("title", clip(title, budget)).put("artist", clip(artist, budget / 2))
                .put("message", "Connected").put("truncated", true)
            raw = result.toString().toByteArray(Charsets.UTF_8)
            budget -= 4
        }
        check(raw.size <= 512) { "GATT state payload too large" }
        return raw
    }
    fun execute(opCode: Int, expectedPlayer: Int): String {
        val c = controller() ?: return "No active supported session"
        val code = if (c.packageName == "com.spotify.music") 1 else 2
        if (code != expectedPlayer) return "Player changed; select again"
        val op = operations[opCode] ?: return "Unknown operation"
        if (op !in capabilities(c)) return "Action unavailable in this app"
        val controls = c.transportControls
        when (op) {
            "play" -> controls.play()
            "pause" -> controls.pause()
            "toggle" -> {
                c.dispatchMediaButtonEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE))
                c.dispatchMediaButtonEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE))
            }
            "next" -> controls.skipToNext()
            "previous" -> controls.skipToPrevious()
            "volume_up" -> c.adjustVolume(AudioManager.ADJUST_RAISE, 0)
            "volume_down" -> c.adjustVolume(AudioManager.ADJUST_LOWER, 0)
            "forward", "back" -> {
                var target = ((position(c) ?: 0) + if (op == "forward") 10000 else -10000).coerceAtLeast(0)
                val duration = c.metadata?.getLong(MediaMetadata.METADATA_KEY_DURATION) ?: 0
                if (duration > 0) target = target.coerceAtMost(duration)
                controls.seekTo(target)
            }
        }
        return "Forwarded $op; await actual app state"
    }
}
