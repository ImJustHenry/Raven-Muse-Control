package app.ravenmuse.control

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import android.os.*
import android.provider.Settings
import android.view.View
import android.view.WindowManager
import android.widget.*
import org.json.JSONObject
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel

class MainActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var status: TextView
    private lateinit var now: TextView
    private lateinit var media: MediaAccess
    private val refresh = object : Runnable {
        override fun run() {
            status.text = BridgeService.status
            now.text = runCatching {
                val state = JSONObject(String(media.snapshot(0, "")))
                val name = state.optString("player")
                if (name.isEmpty()) state.optString("message")
                else "$name\n${state.optString("title")}\n${state.optString("artist")}" 
            }.getOrDefault("Grant media access to see the active player")
            handler.postDelayed(this, 1500)
        }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        media=MediaAccess(this)
        // Protect the pairing-secret dialog from ordinary screenshots/screen recording.
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 54, 36, 36)
            setBackgroundColor(Color.rgb(12, 17, 23))
        }
        fun label(text: String, size: Float = 17f): TextView = TextView(this).apply {
            this.text = text; textSize = size; setTextColor(Color.WHITE)
            setPadding(0, 10, 0, 22); column.addView(this)
        }
        fun action(text: String, callback: () -> Unit) {
            column.addView(Button(this).apply {
                this.text = text; isAllCaps = false; textSize = 17f
                setOnClickListener { callback() }
            }, LinearLayout.LayoutParams(-1, 148).apply { bottomMargin = 14 })
        }
        label("RAVEN\nMUSE CONTROL", 30f)
        label("Your phone plays. Your glasses control.")
        status = label("Stopped", 20f)
        now = label("", 18f)
        action("1. Grant Nearby devices") {
            val permissions = mutableListOf(Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.BLUETOOTH_ADVERTISE)
            if (Build.VERSION.SDK_INT >= 33) permissions += Manifest.permission.POST_NOTIFICATIONS
            requestPermissions(permissions.toTypedArray(), 10)
        }
        action("2. Grant notification / media access") {
            AlertDialog.Builder(this).setTitle("Media session access")
                .setMessage("Android uses notification-listener access to expose media sessions. Muse reads only Spotify/YouTube Music playback state; it does not inspect message notifications.")
                .setPositiveButton("Open settings") { _, _ -> startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }
                .setNegativeButton("Cancel", null).show()
        }
        action("3. Show controller pairing secret") { showSecret() }
        val names = arrayOf("Automatic active player", "Spotify", "YouTube Music")
        val values = arrayOf("auto", "com.spotify.music", "com.google.android.apps.youtube.music")
        val prefs = getSharedPreferences("muse", MODE_PRIVATE)
        label("Control target")
        val spinner = Spinner(this).apply {
            adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, names)
            setSelection(values.indexOf(prefs.getString("preferred", "auto")).coerceAtLeast(0))
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                    prefs.edit().putString("preferred", values[position]).apply()
                }
                override fun onNothingSelected(parent: AdapterView<*>?) { }
            }
        }
        column.addView(spinner)
        action("Start Bluetooth control") {
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED ||
                checkSelfPermission(Manifest.permission.BLUETOOTH_ADVERTISE) != PackageManager.PERMISSION_GRANTED ||
                !media.permission()) {
                Toast.makeText(this, "Complete permission steps first", Toast.LENGTH_LONG).show()
            } else {
                runCatching { startForegroundService(Intent(this, BridgeService::class.java)) }
                    .onFailure { Toast.makeText(this, "Unable to start. Check Bluetooth and permissions.", Toast.LENGTH_LONG).show() }
            }
        }
        action("Stop Bluetooth control") { stopService(Intent(this, BridgeService::class.java)); BridgeService.status = "Stopped" }
        action("Revoke controller / rotate secret") {
            AlertDialog.Builder(this).setMessage("Disconnect the controller and invalidate its stored secret?")
                .setPositiveButton("Revoke") { _, _ ->
                    stopService(Intent(this, BridgeService::class.java)); Vault.rotate(this)
                    BridgeService.status = "Secret rotated; pair again before restarting"
                }.setNegativeButton("Cancel", null).show()
        }
        label("No music downloads. No account passwords. No internet permission in this companion.\nStart a song in Spotify or YouTube Music, then use Muse.", 14f)
        setContentView(ScrollView(this).apply { addView(column) })
    }
    private fun showSecret() {
        runCatching {
            val text = Vault.secret(this).joinToString("") { "%02x".format(it.toInt() and 255) }
            val qr = ImageView(this).apply {
                setImageBitmap(qrBitmap("RMC1:$text", 720))
                setPadding(24, 24, 24, 24)
                setBackgroundColor(Color.WHITE)
                contentDescription = "Controller pairing QR code"
            }
            val note = TextView(this).apply {
                this.text = "Scan with python tools/scan_secret.py on your own computer or glasses. " +
                    "Never photograph it into Claude, a PDF, chat or a repository.\n\nText fallback:\n$text"
                setPadding(36, 24, 36, 12); setTextIsSelectable(true)
            }
            val body = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                addView(qr, LinearLayout.LayoutParams(-1, -2)); addView(note)
            }
            AlertDialog.Builder(this).setTitle("Private controller secret")
                .setView(ScrollView(this).apply { addView(body) })
                .setPositiveButton("Copy") { _, _ ->
                    getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("Muse private key", text))
                }.setNegativeButton("Close", null).show()
        }.onFailure { Toast.makeText(this, "Keystore unavailable; reset/reinstall the companion and pair again", Toast.LENGTH_LONG).show() }
    }
    /** Black-on-white QR with quiet zone; drawn locally, never saved or shared. */
    private fun qrBitmap(payload: String, size: Int): Bitmap {
        val matrix = QRCodeWriter().encode(payload, BarcodeFormat.QR_CODE, size, size,
            mapOf(EncodeHintType.MARGIN to 4, EncodeHintType.ERROR_CORRECTION to ErrorCorrectionLevel.M))
        val pixels = IntArray(matrix.width * matrix.height) { i ->
            if (matrix.get(i % matrix.width, i / matrix.width)) Color.BLACK else Color.WHITE
        }
        return Bitmap.createBitmap(pixels, matrix.width, matrix.height, Bitmap.Config.ARGB_8888)
    }
    override fun onResume() { super.onResume(); handler.post(refresh) }
    override fun onPause() { handler.removeCallbacks(refresh); super.onPause() }
    override fun onDestroy() { handler.removeCallbacksAndMessages(null); media.close(); super.onDestroy() }
}
