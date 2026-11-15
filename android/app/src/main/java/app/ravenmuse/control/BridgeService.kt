package app.ravenmuse.control

import android.Manifest
import android.annotation.SuppressLint
import android.app.*
import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.*
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.UUID
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

@SuppressLint("MissingPermission")
class BridgeService : Service() {
    companion object {
        val SERVICE: UUID = UUID.fromString("7c27f100-6baa-4ad0-8e3b-31f62b88ac50")
        val AUTH: UUID = UUID.fromString("7c27f101-6baa-4ad0-8e3b-31f62b88ac50")
        val STATE: UUID = UUID.fromString("7c27f102-6baa-4ad0-8e3b-31f62b88ac50")
        val COMMAND: UUID = UUID.fromString("7c27f103-6baa-4ad0-8e3b-31f62b88ac50")
        val SIGNAL: UUID = UUID.fromString("7c27f104-6baa-4ad0-8e3b-31f62b88ac50")
        val ARTWORK: UUID = UUID.fromString("7c27f105-6baa-4ad0-8e3b-31f62b88ac50")
        val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        @Volatile var status = "Stopped"
    }
    private val handler = Handler(Looper.getMainLooper())
    private var server: BluetoothGattServer? = null
    private var advertiser: BluetoothLeAdvertiser? = null
    private var peer: BluetoothDevice? = null
    private var nonce = ByteArray(16)
    private var firstHalf: ByteArray? = null
    private var authenticated = false
    private var subscribed = false
    private var authFailures = 0
    private var sequence = 0
    private var revision = 0
    private var peerMtu = 23
    private var readCache = ByteArray(0)
    private var artworkReadCache = ByteArray(0)
    private var lastCommand = "Connected"
    private lateinit var media: MediaAccess
    private lateinit var secret: ByteArray
    private val advertiseCallback = object : AdvertiseCallback() {
        override fun onStartSuccess(settingsInEffect: AdvertiseSettings?) { status = "Advertising; pair the controller" }
        override fun onStartFailure(errorCode: Int) { status = "Advertising error $errorCode"; stopSelf() }
    }
    private fun resetPeer() {
        SecureRandom().nextBytes(nonce)
        firstHalf = null; authenticated = false; subscribed = false
        sequence = 0; authFailures = 0; peerMtu = 23; readCache = ByteArray(0)
        artworkReadCache = ByteArray(0)
    }
    private fun valid(device: BluetoothDevice) = device.address == peer?.address
    private fun authorized(device: BluetoothDevice) = valid(device) && authenticated &&
        runCatching { MessageDigest.isEqual(secret,Vault.secret(this)) }.getOrDefault(false)
    private fun respond(device: BluetoothDevice, request: Int, status: Int, offset: Int = 0, value: ByteArray? = null) {
        server?.sendResponse(device, request, status, offset, value)
    }
    private fun notifyRevision() {
        val device = peer ?: return
        if (!authenticated || !subscribed) return
        val characteristic = server?.getService(SERVICE)?.getCharacteristic(SIGNAL) ?: return
        val value = byteArrayOf((revision and 255).toByte())
        if (Build.VERSION.SDK_INT >= 33) {
            server?.notifyCharacteristicChanged(device, characteristic, false, value)
        } else {
            @Suppress("DEPRECATION")
            characteristic.value = value
            @Suppress("DEPRECATION")
            server?.notifyCharacteristicChanged(device, characteristic, false)
        }
    }
    private val pulse = object : Runnable {
        override fun run() {
            revision = if (revision == Int.MAX_VALUE) 1 else revision + 1
            try {
                notifyRevision()
                handler.postDelayed(this, 1000)
            } catch (_: SecurityException) {
                status = "Bluetooth permission changed; restart after granting access"
                stopSelf()
            }
        }
    }
    private val callback = object : BluetoothGattServerCallback() {
        override fun onServiceAdded(statusCode: Int, service: BluetoothGattService) {
            handler.post {
                if (statusCode != BluetoothGatt.GATT_SUCCESS) { status = "Cannot add BLE service"; stopSelf(); return@post }
                val settings = AdvertiseSettings.Builder().setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
                    .setConnectable(true).setTimeout(0).setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_MEDIUM).build()
                val data = AdvertiseData.Builder().addServiceUuid(ParcelUuid(SERVICE)).setIncludeDeviceName(false).build()
                advertiser?.startAdvertising(settings, data, advertiseCallback)
            }
        }
        override fun onConnectionStateChange(device: BluetoothDevice, statusCode: Int, newState: Int) {
            handler.post {
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    if (peer != null && peer?.address != device.address) {
                        server?.cancelConnection(device)
                    } else {
                        peer = device; resetPeer(); status = "Controller connected; authenticating"
                    }
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED && valid(device)) {
                    peer = null; resetPeer(); status = "Advertising; controller disconnected"
                }
            }
        }
        override fun onMtuChanged(device: BluetoothDevice, mtu: Int) {
            handler.post { if (valid(device)) peerMtu = mtu.coerceIn(23, 517) }
        }
        override fun onCharacteristicReadRequest(device: BluetoothDevice, requestId: Int,
            offset: Int, characteristic: BluetoothGattCharacteristic) {
            handler.post {
                if (!valid(device)) { respond(device, requestId, BluetoothGatt.GATT_INSUFFICIENT_AUTHENTICATION); return@post }
                val bytes: ByteArray = when (characteristic.uuid) {
                    AUTH -> nonce
                    STATE -> {
                        if (!authorized(device)) {
                            respond(device, requestId, BluetoothGatt.GATT_INSUFFICIENT_AUTHENTICATION); return@post
                        }
                        if (offset == 0) {
                            readCache = try { media.snapshot(revision, lastCommand) }
                            catch (_: Exception) { "{\"v\":1,\"caps\":[],\"message\":\"Media permission changed\"}".toByteArray() }
                        }
                        readCache
                    }
                    ARTWORK -> {
                        if (!authorized(device)) {
                            respond(device, requestId, BluetoothGatt.GATT_INSUFFICIENT_AUTHENTICATION); return@post
                        }
                        // Frozen per write request so long GATT reads cannot mix chunks.
                        artworkReadCache
                    }
                    else -> { respond(device, requestId, BluetoothGatt.GATT_READ_NOT_PERMITTED); return@post }
                }
                if (offset < 0 || offset > bytes.size) respond(device, requestId, BluetoothGatt.GATT_INVALID_OFFSET)
                else respond(device, requestId, BluetoothGatt.GATT_SUCCESS, offset,
                    bytes.copyOfRange(offset, minOf(bytes.size, offset + peerMtu - 1)))
            }
        }
        override fun onCharacteristicWriteRequest(device: BluetoothDevice, requestId: Int,
            characteristic: BluetoothGattCharacteristic, preparedWrite: Boolean,
            responseNeeded: Boolean, offset: Int, value: ByteArray) {
            handler.post {
                var result = BluetoothGatt.GATT_SUCCESS
                if (!valid(device)) result = BluetoothGatt.GATT_INSUFFICIENT_AUTHENTICATION
                else if (preparedWrite || offset != 0) result = BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED
                else when (characteristic.uuid) {
                    AUTH -> {
                        if (value.size != 17) result = BluetoothGatt.GATT_INVALID_ATTRIBUTE_LENGTH
                        else if (value[0].toInt() == 0) firstHalf = value.copyOfRange(1, 17)
                        else if (value[0].toInt() == 1 && firstHalf != null) {
                            val expected = Mac.getInstance("HmacSHA256").run {
                                init(SecretKeySpec(secret, "HmacSHA256"))
                                doFinal("RMC1".toByteArray(Charsets.US_ASCII) + nonce)
                            }
                            authenticated = MessageDigest.isEqual(expected, firstHalf!! + value.copyOfRange(1, 17))
                            firstHalf = null
                            if (!authenticated) {
                                result = BluetoothGatt.GATT_INSUFFICIENT_AUTHENTICATION
                                authFailures++
                                SecureRandom().nextBytes(nonce)
                            } else status = "Authenticated controller connected"
                        } else result = BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED
                    }
                    COMMAND -> {
                        if (!authorized(device)) result = BluetoothGatt.GATT_INSUFFICIENT_AUTHENTICATION
                        else if (value.size != 7 || value[0].toInt() != 1) result = BluetoothGatt.GATT_INVALID_ATTRIBUTE_LENGTH
                        else {
                            val buffer = ByteBuffer.wrap(value).order(ByteOrder.LITTLE_ENDIAN)
                            buffer.get(); val op = buffer.get().toInt() and 255
                            val seq = buffer.int; val expectedPlayer = buffer.get().toInt() and 255
                            if (seq <= 0 || seq < sequence) result = BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED
                            else if (seq > sequence) {
                                sequence = seq
                                lastCommand = try { media.execute(op, expectedPlayer) }
                                    catch (_: Exception) { "Permission/session changed; retry" }
                                revision = if (revision == Int.MAX_VALUE) 1 else revision + 1
                                notifyRevision()
                            } // equal sequence: idempotent, never execute twice
                        }
                    }
                    ARTWORK -> {
                        artworkReadCache = ByteArray(0)
                        if (!authorized(device)) result = BluetoothGatt.GATT_INSUFFICIENT_AUTHENTICATION
                        else if (value.size != 13 || value[0].toInt() != 1)
                            result = BluetoothGatt.GATT_INVALID_ATTRIBUTE_LENGTH
                        else {
                            val buffer = ByteBuffer.wrap(value).order(ByteOrder.LITTLE_ENDIAN)
                            buffer.get()
                            val token = ByteArray(8); buffer.get(token)
                            val imageOffset = buffer.int
                            val chunk = try { media.artworkChunk(token, imageOffset) } catch (_: Exception) { null }
                            if (chunk == null) result = BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED
                            else artworkReadCache = chunk
                        }
                    }
                    else -> result = BluetoothGatt.GATT_WRITE_NOT_PERMITTED
                }
                if (responseNeeded) respond(device, requestId, result)
                if (authFailures >= 3) server?.cancelConnection(device)
            }
        }
        override fun onDescriptorWriteRequest(device: BluetoothDevice, requestId: Int,
            descriptor: BluetoothGattDescriptor, preparedWrite: Boolean, responseNeeded: Boolean,
            offset: Int, value: ByteArray) {
            handler.post {
                val allowed = authorized(device) && descriptor.uuid == CCCD && !preparedWrite && offset == 0 &&
                    (value.contentEquals(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE) ||
                     value.contentEquals(BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE))
                if (allowed) subscribed = value.contentEquals(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                if (responseNeeded) respond(device, requestId,
                    if (allowed) BluetoothGatt.GATT_SUCCESS else BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED)
            }
        }
        override fun onDescriptorReadRequest(device: BluetoothDevice, requestId: Int,
            offset: Int, descriptor: BluetoothGattDescriptor) {
            handler.post {
                if (!authorized(device) || descriptor.uuid != CCCD || offset != 0) {
                    respond(device, requestId, BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED)
                } else respond(device, requestId, BluetoothGatt.GATT_SUCCESS, 0,
                    if (subscribed) BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE else BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE)
            }
        }
    }
    override fun onCreate() {
        super.onCreate()
        media = MediaAccess(this); secret = Vault.secret(this)
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED ||
            checkSelfPermission(Manifest.permission.BLUETOOTH_ADVERTISE) != PackageManager.PERMISSION_GRANTED || !media.permission()) {
            status = "Grant Nearby devices and media access first"; stopSelf(); return START_NOT_STICKY
        }
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("muse", "Phone music remote", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val notification = Notification.Builder(this, "muse").setContentTitle("Raven-Muse-Control")
            .setContentText("Bluetooth music control enabled. Open to stop.")
            .setSmallIcon(android.R.drawable.ic_media_play).setContentIntent(open).setOngoing(true).build()
        startForeground(42, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        if (server == null) {
            val manager = getSystemService(BluetoothManager::class.java)
            advertiser = manager.adapter?.bluetoothLeAdvertiser
            if (advertiser == null) { status = "Bluetooth off or BLE advertising unavailable"; stopSelf(); return START_NOT_STICKY }
            server = manager.openGattServer(this, callback)
            if (server == null) { status = "Cannot open GATT server"; stopSelf(); return START_NOT_STICKY }
            val service = BluetoothGattService(SERVICE, BluetoothGattService.SERVICE_TYPE_PRIMARY)
            val auth = BluetoothGattCharacteristic(AUTH,
                BluetoothGattCharacteristic.PROPERTY_READ or BluetoothGattCharacteristic.PROPERTY_WRITE,
                BluetoothGattCharacteristic.PERMISSION_READ_ENCRYPTED or BluetoothGattCharacteristic.PERMISSION_WRITE_ENCRYPTED)
            val state = BluetoothGattCharacteristic(STATE, BluetoothGattCharacteristic.PROPERTY_READ,
                BluetoothGattCharacteristic.PERMISSION_READ_ENCRYPTED)
            val command = BluetoothGattCharacteristic(COMMAND, BluetoothGattCharacteristic.PROPERTY_WRITE,
                BluetoothGattCharacteristic.PERMISSION_WRITE_ENCRYPTED)
            val signal = BluetoothGattCharacteristic(SIGNAL, BluetoothGattCharacteristic.PROPERTY_NOTIFY, 0)
            signal.addDescriptor(BluetoothGattDescriptor(CCCD,
                BluetoothGattDescriptor.PERMISSION_READ_ENCRYPTED or BluetoothGattDescriptor.PERMISSION_WRITE_ENCRYPTED))
            val artwork = BluetoothGattCharacteristic(ARTWORK,
                BluetoothGattCharacteristic.PROPERTY_READ or BluetoothGattCharacteristic.PROPERTY_WRITE,
                BluetoothGattCharacteristic.PERMISSION_READ_ENCRYPTED or BluetoothGattCharacteristic.PERMISSION_WRITE_ENCRYPTED)
            service.addCharacteristic(auth); service.addCharacteristic(state)
            service.addCharacteristic(command); service.addCharacteristic(signal)
            service.addCharacteristic(artwork)
            if (server?.addService(service) != true) { status = "Cannot publish GATT service"; stopSelf() }
            handler.post(pulse)
        }
        return START_NOT_STICKY
    }
    override fun onBind(intent: Intent?) = null
    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        media.close()
        artworkReadCache = ByteArray(0)
        runCatching { advertiser?.stopAdvertising(advertiseCallback) }
        runCatching { peer?.let { server?.cancelConnection(it) }; server?.close() }
        server = null; peer = null; authenticated = false
        if (status.startsWith("Advertising") || status.startsWith("Authenticated")) status = "Stopped"
        super.onDestroy()
    }
}
