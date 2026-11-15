package app.ravenmuse.control

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.util.concurrent.Executors

/** A single background compressor with a replaceable pending job, never a queue
 * of full-size covers. Caller-owned media bitmaps are never recycled or edited.
 * No network, notification-body access, files, or account APIs are used here.
 */
class ArtworkStore {
    companion object {
        const val MAX_BYTES = 16384
        const val CHUNK = 480
        fun hex(bytes: ByteArray) = bytes.joinToString("") { "%02x".format(it.toInt() and 255) }
        fun digest(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes)
    }
    private data class Job(val track: String, val key: String, val bitmap: Bitmap)
    private val executor = Executors.newSingleThreadExecutor { task ->
        Thread(task, "muse-artwork").apply { isDaemon = true }
    }
    private var track = ""
    private var desiredKey = ""
    private var token = ByteArray(0)
    private var image = ByteArray(0)
    private var pending: Job? = null
    private var running = false
    private var closed = false

    @Synchronized fun select(trackId: String, bitmap: Bitmap?): String {
        if (closed || bitmap == null || bitmap.isRecycled || trackId.isEmpty()) {
            clear(); return ""
        }
        if (track != trackId) {
            track = trackId; token = ByteArray(0); image = ByteArray(0)
        }
        val key = "$trackId:${bitmap.generationId}:${bitmap.width}:${bitmap.height}"
        if (key != desiredKey) {
            desiredKey = key
            pending = Job(trackId, key, bitmap)
            if (!running) {
                running = true
                executor.execute { drain() }
            }
        }
        return hex(token)
    }
    private fun drain() {
        while (true) {
            val job = synchronized(this) {
                if (closed || pending == null) { running = false; return }
                val next = pending!!; pending = null; next
            }
            val bytes = try { compress(job.bitmap) } catch (_: Exception) { ByteArray(0) }
            synchronized(this) {
                if (!closed && desiredKey == job.key && track == job.track) {
                    image = bytes
                    token = if (bytes.isEmpty()) ByteArray(0)
                        else digest(job.track.toByteArray(Charsets.US_ASCII) + bytes).copyOfRange(0, 8)
                }
            }
        }
    }
    private fun compress(source: Bitmap): ByteArray {
        require(!source.isRecycled && source.width > 0 && source.height > 0)
        require(source.width.toLong() * source.height <= 4194304L)
        val target = Bitmap.createBitmap(64, 64, Bitmap.Config.ARGB_8888)
        try {
            val canvas = Canvas(target)
            canvas.drawColor(Color.rgb(5, 12, 15))
            val scale = minOf(64f / source.width, 64f / source.height)
            val width = source.width * scale; val height = source.height * scale
            canvas.drawBitmap(source, null,
                RectF((64-width)/2, (64-height)/2, (64+width)/2, (64+height)/2),
                Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG))
            val out = ByteArrayOutputStream()
            check(target.compress(Bitmap.CompressFormat.JPEG, 82, out))
            val bytes = out.toByteArray()
            require(bytes.isNotEmpty() && bytes.size <= MAX_BYTES)
            return bytes
        } finally { target.recycle() }
    }
    @Synchronized fun chunk(trackId: String, expected: ByteArray, offset: Int): ByteArray? {
        if (closed || trackId != track || expected.size != 8 || token.size != 8 ||
            !MessageDigest.isEqual(expected, token) || offset < 0 || offset >= image.size) return null
        val length = minOf(CHUNK, image.size - offset)
        return ByteBuffer.allocate(17 + length).order(ByteOrder.LITTLE_ENDIAN)
            .put(1.toByte()).put(token).putInt(offset).putInt(image.size)
            .put(image, offset, length).array()
    }
    @Synchronized fun clear() {
        track = ""; desiredKey = ""; pending = null
        token = ByteArray(0); image = ByteArray(0)
    }
    @Synchronized fun close() {
        closed = true; clear(); executor.shutdownNow()
    }
}
