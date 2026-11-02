@file:Suppress("MissingPermission", "DEPRECATION")
package cn.gowin.control.ble

import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.job
import kotlinx.coroutines.withContext

internal class AndroidConnectionRecovery(private val context: Context) {
    private var owner: Job? = null
    private val mutableProgress = MutableStateFlow<String?>(null)
    val progress = mutableProgress.asStateFlow()

    fun progress(operation: String) { mutableProgress.value = "正在${gattOperationName(operation)}…" }

    suspend fun <Result> run(address: String, reset: () -> Unit, attempt: suspend () -> Result): Result =
        withContext(Dispatchers.Main.immediate) {
            this@AndroidConnectionRecovery.cancel()
            coroutineScope {
                val current = coroutineContext.job
                owner = current
                try {
                    val adapter = context.getSystemService(BluetoothManager::class.java)?.adapter
                        ?: throw java.io.IOException("手机不支持蓝牙")
                    if (!adapter.isEnabled) throw java.io.IOException("蓝牙未开启")
                    AndroidBondMonitor(context, adapter.getRemoteDevice(address)).use { monitor ->
                        connectWithBondRecovery(monitor.observations, reset, { mutableProgress.value = it }, attempt = attempt)
                    }
                } catch (error: Exception) {
                    if (owner === current) reset()
                    throw error
                } finally {
                    if (owner === current) {
                        owner = null
                        mutableProgress.value = null
                    }
                }
            }
        }

    fun cancel() {
        owner?.cancel()
        owner = null
        mutableProgress.value = null
    }
}

internal class AndroidBondMonitor(private val context: Context, private val device: BluetoothDevice) : AutoCloseable {
    private fun state() = when (device.bondState) {
        BluetoothDevice.BOND_BONDED -> BondState.BONDED
        BluetoothDevice.BOND_BONDING -> BondState.BONDING
        else -> BondState.NONE
    }

    private val initial = state()
    private val mutableObservations = MutableStateFlow(BondObservation(initial == BondState.BONDED, initial))
    val observations = mutableObservations.asStateFlow()
    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val remote = if (Build.VERSION.SDK_INT >= 33)
                intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice::class.java)
            else intent.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE)
            if (remote?.address?.equals(device.address, ignoreCase = true) != true) return
            if (intent.action != BluetoothDevice.ACTION_BOND_STATE_CHANGED && intent.action != KEY_MISSING) return
            val previous = mutableObservations.value
            val currentState = runCatching { state() }.getOrNull() ?: return
            val changed = previous.changed(currentState)
            mutableObservations.value = changed.copy(keyMissing = previous.keyMissing || intent.action == KEY_MISSING)
        }
    }

    init {
        val filter = IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED)
        if (Build.VERSION.SDK_INT >= 36) filter.addAction(KEY_MISSING)
        if (Build.VERSION.SDK_INT >= 33) context.registerReceiver(receiver, filter, Context.RECEIVER_EXPORTED)
        else context.registerReceiver(receiver, filter)
        try {
            mutableObservations.value = mutableObservations.value.changed(state())
        } catch (error: Exception) {
            context.unregisterReceiver(receiver)
            throw error
        }
    }

    override fun close() { context.unregisterReceiver(receiver) }

    private companion object {
        const val KEY_MISSING = "android.bluetooth.device.action.KEY_MISSING"
    }
}
