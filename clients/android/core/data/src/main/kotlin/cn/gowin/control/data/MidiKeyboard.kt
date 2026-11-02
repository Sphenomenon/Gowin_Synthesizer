package cn.gowin.control.data

import android.content.Context
import android.os.SystemClock
import cn.gowin.control.ble.AndroidMidiTransport
import cn.gowin.control.ble.MidiTransport
import cn.gowin.control.protocol.BleMidi
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.*

data class MidiKeyboardState(
    val connecting: Boolean = false,
    val ready: Boolean = false,
    val name: String = "未连接25K MIDI",
    val channel: Int = 0,
    val velocity: Int = 100,
    val heldNotes: Set<Int> = emptySet(),
    val sentEvents: Long = 0,
    val error: String? = null,
    val connectionProgress: String? = null,
    val disconnecting: Boolean = false,
) {
    val active: Boolean get() = connecting || ready || disconnecting
    val connection: String get() = when {
        disconnecting -> "MIDI 正在停音并断开"
        connecting -> connectionProgress ?: "MIDI 连接及清理旧音符中…"
        ready -> "MIDI 已连接 · $name"
        else -> "MIDI 未连接 · $name"
    }
}

/** Ordered, bounded MIDI send queue. A new connection never replays old notes. */
class MidiKeyboard(
    private val transport: MidiTransport,
    private val scope: CoroutineScope,
    private val clockMillis: () -> Long = SystemClock::elapsedRealtime,
) {
    constructor(context: Context, scope: CoroutineScope) : this(AndroidMidiTransport(context.applicationContext), scope)
    private val mutableState = MutableStateFlow(MidiKeyboardState())
    val state = mutableState.asStateFlow()
    val devices = transport.devices
    private data class Event(val epoch: Long, val message: ByteArray?, val disconnect: Boolean = false)
    private val queue = Channel<Event>(64)
    private var epoch = 0L
    private var connecting: Job? = null
    private var scanTimeout: Job? = null

    init {
        scope.launch {
            transport.connectionProgress.collect { progress ->
                mutableState.value = mutableState.value.copy(connectionProgress = progress)
            }
        }
        scope.launch {
            transport.connected.collect { connected ->
                if (!connected && mutableState.value.ready) {
                    epoch++
                    mutableState.value = mutableState.value.copy(ready = false, heldNotes = emptySet(), error = "MIDI 已断开；旧按键已清除，重连先发送 PANIC。")
                }
            }
        }
        scope.launch {
            for (event in queue) {
                if (event.epoch != epoch) continue
                try {
                    event.message?.let { transport.send(BleMidi.packet(it, clockMillis())) }
                    if (event.epoch == epoch && event.message != null)
                        mutableState.value = mutableState.value.copy(sentEvents = mutableState.value.sentEvents + 1)
                    if (event.disconnect && event.epoch == epoch) closeNow(null)
                } catch (error: CancellationException) { throw error }
                catch (error: Exception) { if (event.epoch == epoch) closeNow("MIDI 发送失败：${error.message}；请重连并确认设备已停音。") }
            }
        }
    }
    fun scan() {
        try {
            transport.startScan { reportError(it) }
            scanTimeout?.cancel()
            scanTimeout = scope.launch { delay(10_000); transport.stopScan() }
        } catch (error: Exception) { reportError("无法扫描 MIDI 设备：${error.message}") }
    }
    fun stopScan() { scanTimeout?.cancel(); transport.stopScan() }
    fun releaseControls() { panic(); stopScan() }
    fun connect(address: String, name: String) {
        connecting?.cancel()
        closeNow(null)
        stopScan()
        val generation = epoch
        mutableState.value = mutableState.value.copy(connecting = true, name = name, sentEvents = 0)
        connecting = scope.launch {
            try {
                transport.connect(address)
                // GW25K clears its input queue on disconnect; clear any remote
                // synth/controller state too before accepting a fresh key press.
                BleMidi.panic().forEach { transport.send(BleMidi.packet(it, clockMillis())) }
                if (generation == epoch) mutableState.value = mutableState.value.copy(connecting = false, ready = true, error = null)
            } catch (error: CancellationException) { throw error }
            catch (error: Exception) { if (generation == epoch) closeNow("MIDI 连接失败：${error.message}") }
        }
    }
    fun setVelocity(value: Int) { mutableState.value = mutableState.value.copy(velocity = value.coerceIn(1, 127)) }
    fun setChannel(value: Int) {
        val channel = value.coerceIn(0, 15)
        if (channel == mutableState.value.channel) return
        panic()
        mutableState.value = mutableState.value.copy(channel = channel)
    }
    fun noteOn(note: Int) {
        require(note in 0..127)
        val state = mutableState.value
        if (!state.ready || note in state.heldNotes) return
        mutableState.value = state.copy(heldNotes = state.heldNotes + note)
        enqueue(BleMidi.noteOn(state.channel, note, state.velocity))
    }
    fun noteOff(note: Int) {
        val state = mutableState.value
        if (note !in state.heldNotes) return
        mutableState.value = state.copy(heldNotes = state.heldNotes - note)
        if (state.ready) enqueue(BleMidi.noteOff(state.channel, note))
    }
    fun panic() {
        mutableState.value = mutableState.value.copy(heldNotes = emptySet())
        if (!mutableState.value.ready) return
        // Drop unsent key presses before the all-channel cleanup fence.
        epoch++
        while (queue.tryReceive().isSuccess) { /* replace pending presses with panic */ }
        BleMidi.panic().forEach { enqueue(it) }
    }
    fun disconnect() {
        if (mutableState.value.disconnecting) return
        if (mutableState.value.connecting) { connecting?.cancel(); closeNow(null); return }
        if (!mutableState.value.ready) { closeNow(null); return }
        panic()
        mutableState.value = mutableState.value.copy(ready = false, disconnecting = true)
        if (!queue.trySend(Event(epoch, null, disconnect = true)).isSuccess) closeNow("MIDI 队列已满，连接已关闭；请确认设备已停音。")
    }
    fun reportError(message: String) { mutableState.value = mutableState.value.copy(error = message) }
    private fun enqueue(message: ByteArray) {
        if (!queue.trySend(Event(epoch, message)).isSuccess) closeNow("MIDI 队列已满，连接已关闭；请重连并确认设备已停音。")
    }
    private fun closeNow(error: String?) {
        epoch++
        transport.close()
        while (queue.tryReceive().isSuccess) { /* discard retired session */ }
        mutableState.value = mutableState.value.copy(connecting = false, ready = false, disconnecting = false, heldNotes = emptySet(), error = error)
    }
}
