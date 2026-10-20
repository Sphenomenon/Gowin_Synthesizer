@file:Suppress("MissingPermission", "DEPRECATION")
package cn.gowin.control.ble

import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import cn.gowin.control.protocol.GattIds
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.io.IOException
import java.util.UUID

class AndroidBleTransport(private val context: Context) : BleTransport {
    private val manager = context.getSystemService(BluetoothManager::class.java)
    private var gatt: BluetoothGatt? = null
    private var epoch = 0L
    private var commandWriteType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
    private val mutex = Mutex()
    private data class Pending(val kind: String, val uuid: UUID?, val result: CompletableDeferred<ByteArray>)
    private var pending: Pending? = null
    private val _notifications = MutableSharedFlow<Notification>(extraBufferCapacity = 256)
    override val notifications = _notifications.asSharedFlow()
    private val _connected = MutableStateFlow(false)
    override val connected = _connected.asStateFlow()
    private val _devices = MutableStateFlow<List<FoundDevice>>(emptyList())
    val devices = _devices.asStateFlow()
    private var scanner: BluetoothLeScanner? = null
    private var scanCallback: ScanCallback? = null

    fun startScan(onError: (String) -> Unit) {
        stopScan(); _devices.value = emptyList()
        val adapter = manager?.adapter
        if (adapter?.isEnabled != true) { onError("请先开启蓝牙"); return }
        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val d = FoundDevice(result.device.address, result.scanRecord?.deviceName ?: "GW138K 工作站", result.rssi)
                _devices.update { (it.filterNot { x -> x.address == d.address } + d).sortedByDescending { x -> x.rssi } }
            }
            override fun onScanFailed(errorCode: Int) { onError("蓝牙扫描失败 ($errorCode)，请稍后重试") }
        }
        scanner = adapter.bluetoothLeScanner; scanCallback = callback
        scanner?.startScan(listOf(ScanFilter.Builder().setServiceUuid(ParcelUuid(GattIds.service)).build()),
            ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), callback)
    }
    fun stopScan() {
        val cb = scanCallback; scanCallback = null
        if (cb != null) runCatching { scanner?.stopScan(cb) }
        scanner = null
    }
    private fun characteristic(uuid: UUID): BluetoothGattCharacteristic =
        gatt?.getService(GattIds.service)?.getCharacteristic(uuid) ?: throw IOException("设备缺少业务特征 $uuid")

    private class RejectedOperation(message:String):IOException(message)
    private suspend fun operation(kind: String, uuid: UUID? = null, timeout: Long = 5000, optional:Boolean=false, start: () -> Boolean): ByteArray = mutex.withLock {
        withContext(Dispatchers.Main.immediate) {
            val p = Pending(kind, uuid, CompletableDeferred())
            check(pending == null)
            pending = p
            try {
                if (!start()) throw RejectedOperation("系统未接受 GATT $kind")
                withTimeout(timeout) { p.result.await() }
            } catch (e: Exception) {
                if(optional && e is RejectedOperation && connected.value) byteArrayOf()
                else { close(); throw e }
            }
            finally { if (pending === p) pending = null }
        }
    }
    private fun finish(kind: String, uuid: UUID?, status: Int, bytes: ByteArray = byteArrayOf()) {
        val p = pending ?: return
        if (p.kind != kind || p.uuid != uuid) return
        if (status == BluetoothGatt.GATT_SUCCESS) p.result.complete(bytes)
        else p.result.completeExceptionally(RejectedOperation("GATT $kind 失败 ($status)"))
    }
    override suspend fun connect(address: String) {
        withContext(Dispatchers.Main.immediate) { stopScan(); close() }
        val generation = epoch
        val callback = object : BluetoothGattCallback() {
            private fun current(g: BluetoothGatt) = generation == epoch && g === gatt
            override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
                if (!current(g)) return
                if (status == BluetoothGatt.GATT_SUCCESS && newState == BluetoothProfile.STATE_CONNECTED) {
                    _connected.value = true; finish("connect", null, status)
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED || status != 0) close()
            }
            override fun onMtuChanged(g:BluetoothGatt,mtu:Int,status:Int) { if(current(g))finish("mtu",null,status) }
            override fun onServicesDiscovered(g: BluetoothGatt, status: Int) { if (current(g)) finish("discover",null,status) }
            override fun onCharacteristicRead(g: BluetoothGatt, c: BluetoothGattCharacteristic, value: ByteArray, status: Int) {
                if (current(g)) finish("read",c.uuid,status,value.copyOf())
            }
            override fun onCharacteristicRead(g: BluetoothGatt, c: BluetoothGattCharacteristic, status: Int) {
                if (Build.VERSION.SDK_INT < 33 && current(g)) finish("read",c.uuid,status,c.value?.copyOf() ?: byteArrayOf())
            }
            override fun onDescriptorWrite(g: BluetoothGatt, d: BluetoothGattDescriptor, status: Int) {
                if (current(g)) finish("subscribe",d.characteristic.uuid,status)
            }
            override fun onCharacteristicWrite(g: BluetoothGatt, c: BluetoothGattCharacteristic, status: Int) {
                if (current(g)) finish("write",c.uuid,status)
            }
            private fun notify(g: BluetoothGatt, c: BluetoothGattCharacteristic, bytes: ByteArray) {
                if (current(g) && !_notifications.tryEmit(Notification(c.uuid,bytes.copyOf()))) close()
            }
            override fun onCharacteristicChanged(g: BluetoothGatt,c: BluetoothGattCharacteristic,value: ByteArray) { notify(g,c,value) }
            override fun onCharacteristicChanged(g: BluetoothGatt,c: BluetoothGattCharacteristic) {
                if (Build.VERSION.SDK_INT < 33) notify(g,c,c.value ?: byteArrayOf())
            }
        }
        operation("connect",timeout=15000) {
            val adapter = manager?.adapter ?: throw IOException("手机不支持蓝牙")
            if (!adapter.isEnabled) throw IOException("蓝牙未开启")
            gatt = adapter.getRemoteDevice(address).connectGatt(context,false,callback,BluetoothDevice.TRANSPORT_LE,
                BluetoothDevice.PHY_LE_1M_MASK,Handler(Looper.getMainLooper()))
            gatt != null
        }
        operation("discover") { gatt?.discoverServices() == true }
        // A rejected request leaves ATT23 usable. A timeout closes the uncertain
        // GATT operation rather than racing service/characteristic requests.
        operation("mtu",optional=true) { gatt?.requestMtu(247)==true }
        withContext(Dispatchers.Main.immediate) {
            if (gatt?.getService(GattIds.service) == null) { close(); throw IOException("设备尚未提供 GW138K 业务服务") }
            // The declaration advertises this optional transport independently
            // of v1 logical capabilities. Old firmware continues using requests.
            commandWriteType=if(characteristic(GattIds.command).properties and BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE!=0)
                BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE else BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        }
    }
    override suspend fun read(uuid: UUID): ByteArray = operation("read",uuid) {
        val c=characteristic(uuid)
        if (c.properties and BluetoothGattCharacteristic.PROPERTY_READ == 0) throw IOException("特征不可读取")
        gatt?.readCharacteristic(c) == true
    }
    override suspend fun subscribe(uuid: UUID) {
        operation("subscribe",uuid) {
            val c=characteristic(uuid)
            if (c.properties and BluetoothGattCharacteristic.PROPERTY_NOTIFY == 0) throw IOException("设备不支持通知")
            val d=c.getDescriptor(GattIds.cccd) ?: throw IOException("设备缺少 CCCD")
            if (gatt?.setCharacteristicNotification(c,true) != true) throw IOException("无法启用通知")
            if (Build.VERSION.SDK_INT >= 33) gatt?.writeDescriptor(d,BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE) == BluetoothStatusCodes.SUCCESS
            else { d.value=BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE; gatt?.writeDescriptor(d)==true }
        }
    }
    override suspend fun write(value: ByteArray) {
        require(value.size <= 20)
        operation("write",GattIds.command) {
            val c=characteristic(GattIds.command)
            if (c.properties and BluetoothGattCharacteristic.PROPERTY_WRITE == 0) throw IOException("业务命令不可写入")
            if(Build.VERSION.SDK_INT >= 33) gatt?.writeCharacteristic(c,value,commandWriteType)==BluetoothStatusCodes.SUCCESS
            else { c.writeType=commandWriteType; c.value=value; gatt?.writeCharacteristic(c)==true }
        }
    }
    override fun useAcknowledgedWrites() { commandWriteType=BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT }
    override fun priority(high: Boolean) { runCatching { gatt?.requestConnectionPriority(if(high) BluetoothGatt.CONNECTION_PRIORITY_HIGH else BluetoothGatt.CONNECTION_PRIORITY_BALANCED) } }
    override fun close() {
        epoch++; _connected.value=false
        commandWriteType=BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        val old=gatt; gatt=null
        pending?.result?.completeExceptionally(IOException("蓝牙连接已断开"))
        runCatching { old?.disconnect() }; runCatching { old?.close() }
    }
}
