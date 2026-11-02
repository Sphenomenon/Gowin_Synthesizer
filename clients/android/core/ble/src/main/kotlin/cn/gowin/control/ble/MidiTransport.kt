package cn.gowin.control.ble

import kotlinx.coroutines.flow.StateFlow

interface MidiTransport {
    val connectionProgress: kotlinx.coroutines.flow.Flow<String?> get() = kotlinx.coroutines.flow.emptyFlow()
    val connected: StateFlow<Boolean>
    val devices: StateFlow<List<FoundDevice>>
    fun startScan(onError: (String) -> Unit)
    fun stopScan()
    suspend fun connect(address: String)
    suspend fun send(packet: ByteArray)
    fun close()
}
