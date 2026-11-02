@file:Suppress("MissingPermission", "DEPRECATION")
package cn.gowin.control.ble

import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import cn.gowin.control.protocol.BleMidi
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.io.IOException
import java.util.UUID

/** Dedicated standard BLE MIDI link; never shares the workstation business GATT session. */
class AndroidMidiTransport(private val context: Context) : MidiTransport {
    private val manager = context.getSystemService(BluetoothManager::class.java)
    private val recovery = AndroidConnectionRecovery(context)
    override val connectionProgress = recovery.progress
    private var gatt: BluetoothGatt? = null
    private var epoch = 0L
    private val mutex = Mutex()
    private data class Pending(val kind: String, val uuid: UUID?, val result: CompletableDeferred<ByteArray>)
    private var pending: Pending? = null
    private val _connected = MutableStateFlow(false)
    override val connected = _connected.asStateFlow()
    private val _devices = MutableStateFlow<List<FoundDevice>>(emptyList())
    override val devices = _devices.asStateFlow()
    private var scanner: BluetoothLeScanner? = null
    private var scanCallback: ScanCallback? = null

    override fun startScan(onError: (String) -> Unit) {
        stopScan(); _devices.value = emptyList()
        val adapter = manager?.adapter
        if (adapter?.isEnabled != true) { onError("请先开启蓝牙"); return }
        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val d = FoundDevice(result.device.address, result.scanRecord?.deviceName ?: "BLE MIDI 设备", result.rssi)
                _devices.update { (it.filterNot { x -> x.address == d.address } + d).sortedByDescending { x -> x.rssi } }
            }
            override fun onScanFailed(errorCode: Int) { onError("蓝牙扫描失败 ($errorCode)，请稍后重试") }
        }
        scanner = adapter.bluetoothLeScanner; scanCallback = callback
        scanner?.startScan(listOf(ScanFilter.Builder().setServiceUuid(ParcelUuid(BleMidi.service)).build()),
            ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), callback)
    }
    override fun stopScan() {
        val cb = scanCallback; scanCallback = null
        if (cb != null) runCatching { scanner?.stopScan(cb) }
        scanner = null
    }
    private fun characteristic(uuid: UUID): BluetoothGattCharacteristic =
        gatt?.getService(BleMidi.service)?.getCharacteristic(uuid) ?: throw IOException("设备缺少 MIDI 特征 $uuid")

    private class RejectedOperation(kind: String): GattFailure(kind, detail = "系统未接受请求")
    private suspend fun operation(kind: String, uuid: UUID? = null, timeout: Long = 5000, optional:Boolean=false, start: () -> Boolean): ByteArray = mutex.withLock {
        withContext(Dispatchers.Main.immediate) {
            recovery.progress(kind)
            val p = Pending(kind, uuid, CompletableDeferred())
            check(pending == null)
            pending = p
            try {
                if (!start()) throw RejectedOperation(kind)
                withTimeout(timeout) { p.result.await() }
            } catch (error: TimeoutCancellationException) {
                currentCoroutineContext().ensureActive()
                val failure = GattFailure(kind, detail = "操作超时", cause = error)
                closeGatt(failure)
                throw failure
            } catch (e: Exception) {
                if(optional && e is RejectedOperation && connected.value) byteArrayOf()
                else { closeGatt(); throw e }
            }
            finally { if (pending === p) pending = null }
        }
    }
    private fun finish(kind: String, uuid: UUID?, status: Int, bytes: ByteArray = byteArrayOf()) {
        val p = pending ?: return
        if (p.kind != kind || p.uuid != uuid) return
        if (status == BluetoothGatt.GATT_SUCCESS) p.result.complete(bytes)
        else p.result.completeExceptionally(GattFailure(kind, status))
    }
    override suspend fun connect(address: String) {
        recovery.run(address, { closeGatt() }) { connectOnce(address) }
    }
    private suspend fun connectOnce(address: String) {
        withContext(Dispatchers.Main.immediate) { stopScan(); closeGatt() }
        val generation = epoch
        val callback = object : BluetoothGattCallback() {
            private fun current(g: BluetoothGatt) = generation == epoch && g === gatt
            override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
                if (!current(g)) return
                if (status == BluetoothGatt.GATT_SUCCESS && newState == BluetoothProfile.STATE_CONNECTED) {
                    _connected.value = true; finish("connect", null, status)
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED || status != 0)
                    closeGatt(GattFailure(pending?.kind ?: "connection", status, "连接已断开"))
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

        }
        operation("connect",timeout=15000) {
            val adapter = manager?.adapter ?: throw IOException("手机不支持蓝牙")
            if (!adapter.isEnabled) throw IOException("蓝牙未开启")
            gatt = adapter.getRemoteDevice(address).connectGatt(context,false,callback,BluetoothDevice.TRANSPORT_LE,
                BluetoothDevice.PHY_LE_1M_MASK,Handler(Looper.getMainLooper()))
            gatt != null
        }
        operation("discover") { gatt?.discoverServices() == true }
        withContext(Dispatchers.Main.immediate) {
            val c = characteristic(BleMidi.characteristic)
            if (c.properties and BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE == 0)
                throw IOException("设备不支持 BLE MIDI 无响应写入")
        }
        subscribe()
    }

    private suspend fun subscribe() {
        val uuid = BleMidi.characteristic
        operation("subscribe",uuid) {
            val c=characteristic(uuid)
            if (c.properties and BluetoothGattCharacteristic.PROPERTY_NOTIFY == 0) throw IOException("设备不支持通知")
            val d=c.getDescriptor(BleMidi.cccd) ?: throw IOException("设备缺少 CCCD")
            if (gatt?.setCharacteristicNotification(c,true) != true) throw IOException("无法启用通知")
            if (Build.VERSION.SDK_INT >= 33) gatt?.writeDescriptor(d,BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE) == BluetoothStatusCodes.SUCCESS
            else { d.value=BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE; gatt?.writeDescriptor(d)==true }
        }
    }
    override suspend fun send(packet: ByteArray) {
        require(packet.size in 3..5)
        val value = packet.copyOf()
        operation("write",BleMidi.characteristic) {
            val c=characteristic(BleMidi.characteristic)
            if (c.properties and BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE == 0) throw IOException("MIDI 特征不可写入")
            if(Build.VERSION.SDK_INT >= 33) gatt?.writeCharacteristic(c,value,BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE)==BluetoothStatusCodes.SUCCESS
            else { c.writeType=BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE; c.value=value; gatt?.writeCharacteristic(c)==true }
        }
    }
    override fun close() {
        recovery.cancel()
        closeGatt()
    }
    private fun closeGatt(error: Exception = IOException("蓝牙连接已断开")) {
        epoch++; _connected.value=false
        val old=gatt; gatt=null
        pending?.result?.completeExceptionally(error)
        runCatching { old?.disconnect() }; runCatching { old?.close() }
    }
}
