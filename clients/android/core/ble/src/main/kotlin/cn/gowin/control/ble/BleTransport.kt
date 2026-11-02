package cn.gowin.control.ble

import java.util.UUID
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow

data class Notification(val characteristic: UUID, val value: ByteArray)
data class FoundDevice(val address: String, val name: String, val rssi: Int)
interface BleTransport {
    val connectionProgress: Flow<String?> get() = emptyFlow()
    val notifications: SharedFlow<Notification>
    val connected: StateFlow<Boolean>
    suspend fun connect(address: String)
    suspend fun <Result> establish(address: String, handshake: suspend () -> Result): Result {
        connect(address)
        return handshake()
    }
    suspend fun read(uuid: UUID): ByteArray
    suspend fun subscribe(uuid: UUID)
    suspend fun write(value: ByteArray)
    fun priority(high: Boolean) {}
    fun useAcknowledgedWrites() {}
    fun close()
}
