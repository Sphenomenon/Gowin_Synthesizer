package cn.gowin.control.ble

import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withTimeoutOrNull

open class GattFailure(
    val operation: String,
    val status: Int? = null,
    val detail: String? = null,
    cause: Throwable? = null,
) : IOException(buildString {
    append("蓝牙${gattOperationName(operation)}失败")
    status?.let { append("（GATT $it）") }
    detail?.let { append("：$it") }
    if (status == 5 || status == 15) append("；认证或加密未通过")
}, cause)

internal fun gattOperationName(operation: String): String = when (operation) {
    "connect" -> "连接"
    "connection" -> "连接维持"
    "discover" -> "服务发现"
    "mtu" -> "MTU协商"
    "read" -> "读取"
    "subscribe" -> "通知订阅"
    "write" -> "写入"
    else -> operation
}

internal enum class BondState { NONE, BONDING, BONDED }

internal data class BondObservation(
    val initiallyBonded: Boolean,
    val state: BondState,
    val removed: Boolean = false,
    val keyMissing: Boolean = false,
) {
    val canRetry: Boolean get() = initiallyBonded && removed && state == BondState.NONE

    fun changed(newState: BondState, previousState: BondState = state): BondObservation = copy(
        initiallyBonded = initiallyBonded || previousState == BondState.BONDED,
        state = newState,
        removed = removed || ((initiallyBonded || previousState == BondState.BONDED) && newState == BondState.NONE),
    )
}

internal suspend fun <Result> connectWithBondRecovery(
    observations: StateFlow<BondObservation>,
    reset: () -> Unit,
    progress: (String) -> Unit = {},
    waitMillis: Long = 3000,
    retryDelayMillis: Long = 350,
    attempt: suspend () -> Result,
): Result {
    val original = try {
        return attempt()
    } catch (error: CancellationException) {
        throw error
    } catch (error: GattFailure) {
        error
    }
    val observed = observations.value
    val authenticationError = original.status == 5 || original.status == 15
    val eligible = observed.removed || observed.keyMissing ||
        (observed.initiallyBonded && (authenticationError || original.status == 133))
    if (!eligible) throw original

    reset()
    progress("连接失败，等待系统确认旧配对状态…")
    val cleared = withTimeoutOrNull(waitMillis) { observations.first { it.canRetry } }
    if (cleared == null) {
        val latest = observations.value
        if (latest.keyMissing || (authenticationError && latest.initiallyBonded)) {
            val reason = if (latest.keyMissing) "设备未能提供旧配对密钥" else "旧配对可能已失效"
            throw IOException("${original.message}；$reason。请在系统蓝牙设置中仅取消此设备的旧配对，再返回对应连接页重试。", original)
        }
        throw original
    }
    progress("系统已清除旧配对，正在自动重连（仅一次）…")
    delay(retryDelayMillis)
    if (observations.value.state != BondState.NONE)
        throw IOException("配对状态已改变，已停止自动重连；请等待系统配对完成后重试。", original)
    return try {
        attempt()
    } catch (error: CancellationException) {
        throw error
    } catch (error: Exception) {
        throw IOException("旧配对清除后自动重连仍失败：${error.message}；已停止重试。", error).apply {
            addSuppressed(original)
        }
    }
}
