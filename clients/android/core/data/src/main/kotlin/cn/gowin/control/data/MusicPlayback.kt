package cn.gowin.control.data

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceCallback
import android.media.AudioDeviceInfo
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.AudioRouting
import android.media.MediaPlayer
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.provider.OpenableColumns
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Actual local/A2DP media routing, independent of both BLE business and MIDI. */
data class MusicPlaybackState(
    val name: String? = null,
    val preparing: Boolean = false,
    val ready: Boolean = false,
    val playing: Boolean = false,
    val positionMs: Int = 0,
    val durationMs: Int = 0,
    val outputs: List<MusicOutput> = emptyList(),
    val selectedOutputId: Int? = null,
    val routeConfirmed: Boolean = false,
    val a2dpAvailable: Boolean = false,
    val routedToA2dp: Boolean = false,
    val output: String = "尚未播放",
    val error: String? = null,
)

class MusicPlayback(context: Context) {
    private val context = context.applicationContext
    private val audio = context.getSystemService(AudioManager::class.java)
    private val handler = Handler(Looper.getMainLooper())
    private val mutableState = MutableStateFlow(MusicPlaybackState())
    val state: StateFlow<MusicPlaybackState> = mutableState.asStateFlow()
    private var player: MediaPlayer? = null
    private var routeDeadlineMs = 0L
    private var routeEstablished = false
    private val attributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build()
    private val focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
        .setAudioAttributes(attributes)
        .setOnAudioFocusChangeListener({ change -> if (change < 0) pause() }, handler)
        .build()

    private val tick = object : Runnable {
        override fun run() {
            val current = player ?: return
            if (mutableState.value.ready) {
                refreshRoute(current)
                if (mutableState.value.playing) {
                    if (!mutableState.value.routeConfirmed && (routeEstablished || android.os.SystemClock.elapsedRealtime() >= routeDeadlineMs)) {
                        pause()
                        mutableState.value = mutableState.value.copy(error = "实际音频输出与选择的设备不一致，已暂停。请确认系统媒体输出后重试。")
                        return
                    }
                    runCatching { current.currentPosition }.onSuccess {
                        mutableState.value = mutableState.value.copy(positionMs = it)
                    }
                }
            }
            handler.postDelayed(this, 250)
        }
    }
    private val routing = AudioRouting.OnRoutingChangedListener { current ->
        val active = player ?: return@OnRoutingChangedListener
        if (current !== active) return@OnRoutingChangedListener
        refreshRoute(active)
        // A real route change from A2DP to the handset stops playback rather
        // than continuing on a different physical output without notice.
        if (mutableState.value.playing && !mutableState.value.routeConfirmed &&
            (routeEstablished || android.os.SystemClock.elapsedRealtime() >= routeDeadlineMs)) {
            pause()
            mutableState.value = mutableState.value.copy(error = "所选音频输出已断开或改变，播放已暂停。")
        }
    }
    private val devices = object : AudioDeviceCallback() {
        override fun onAudioDevicesAdded(addedDevices: Array<out AudioDeviceInfo>) = refreshDevices()
        override fun onAudioDevicesRemoved(removedDevices: Array<out AudioDeviceInfo>) = refreshDevices()
    }

    init {
        audio.registerAudioDeviceCallback(devices, handler)
        refreshDevices()
    }

    private fun refreshDevices() {
        val outputs = audio.getDevices(AudioManager.GET_DEVICES_OUTPUTS)
            .filter { it.type in setOf(AudioDeviceInfo.TYPE_BUILTIN_SPEAKER, AudioDeviceInfo.TYPE_WIRED_HEADPHONES,
                AudioDeviceInfo.TYPE_WIRED_HEADSET, AudioDeviceInfo.TYPE_USB_HEADSET, AudioDeviceInfo.TYPE_USB_DEVICE,
                AudioDeviceInfo.TYPE_BLUETOOTH_A2DP) }
            .map { MusicOutput(it.id, if (it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER) "手机扬声器" else it.productName.toString(),
                it.type == AudioDeviceInfo.TYPE_BLUETOOTH_A2DP) }
        val state = mutableState.value
        mutableState.value = state.copy(outputs = outputs, a2dpAvailable = outputs.any { it.a2dp },
            routeConfirmed = state.routeConfirmed && outputs.any { it.id == state.selectedOutputId })
        if (state.selectedOutputId != null && outputs.none { it.id == state.selectedOutputId } && state.playing) {
            pause()
            mutableState.value = mutableState.value.copy(routeConfirmed = false, error = "所选音频输出已断开，播放已暂停。请重新选择输出。")
        }
    }

    fun selectOutput(id: Int) {
        refreshDevices()
        if (mutableState.value.outputs.none { it.id == id }) return
        pause()
        mutableState.value = mutableState.value.copy(selectedOutputId = id, routeConfirmed = false, error = null)
        player?.let { applyPreferredDevice(it) }
    }

    private fun applyPreferredDevice(current: MediaPlayer): Boolean {
        val id = mutableState.value.selectedOutputId ?: return false
        val device = audio.getDevices(AudioManager.GET_DEVICES_OUTPUTS).firstOrNull { it.id == id } ?: return false
        return current.setPreferredDevice(device)
    }

    private fun refreshRoute(current: MediaPlayer) {
        val device = current.routedDevice
        val isA2dp = device?.type == AudioDeviceInfo.TYPE_BLUETOOTH_A2DP
        val output = when {
            isA2dp -> "蓝牙媒体 · ${device?.productName}"
            device?.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER -> "手机扬声器"
            device != null -> device.productName.toString()
            else -> "尚未取得实际输出路由"
        }
        mutableState.value = mutableState.value.copy(routedToA2dp = isA2dp, output = output,
            routeConfirmed = MusicRoute.accepts(mutableState.value.selectedOutputId, device?.id, mutableState.value.outputs.map { it.id }.toSet()))
        if (mutableState.value.routeConfirmed) routeEstablished = true
    }

    fun select(uri: Uri) {
        releasePlayer()
        val name = runCatching {
            context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) cursor.getString(0) else null
            }
        }.getOrNull() ?: uri.lastPathSegment ?: "音频文件"
        mutableState.value = mutableState.value.copy(name = name, preparing = true, ready = false, playing = false,
            positionMs = 0, durationMs = 0, routeConfirmed = false, routedToA2dp = false, output = "尚未播放", error = null)
        val current = MediaPlayer()
        player = current
        try {
            current.setAudioAttributes(attributes)
            current.addOnRoutingChangedListener(routing, handler)
            current.setOnPreparedListener {
                if (player !== it) return@setOnPreparedListener
                mutableState.value = mutableState.value.copy(preparing = false, ready = true, durationMs = it.duration.coerceAtLeast(0))
                handler.post(tick)
            }
            current.setOnCompletionListener {
                if (player === it) {
                    audio.abandonAudioFocusRequest(focus)
                    mutableState.value = mutableState.value.copy(playing = false, positionMs = mutableState.value.durationMs)
                }
            }
            current.setOnErrorListener { failed, what, extra ->
                if (player === failed) {
                    releasePlayer()
                    mutableState.value = mutableState.value.copy(preparing = false, ready = false, playing = false,
                        error = "无法播放此音频文件（$what / $extra），请选择手机支持的音频格式。")
                }
                true
            }
            current.setDataSource(context, uri)
            current.prepareAsync()
        } catch (error: Exception) {
            releasePlayer()
            mutableState.value = mutableState.value.copy(preparing = false, ready = false,
                error = "无法打开音频：${error.message ?: "文件不可读取"}")
        }
    }

    fun play() {
        refreshDevices()
        if (!mutableState.value.ready) return
        if (mutableState.value.outputs.none { it.id == mutableState.value.selectedOutputId }) {
            mutableState.value = mutableState.value.copy(error = "请先明确选择手机本地输出或已连接的蓝牙媒体设备。")
            return
        }
        val current = player ?: return
        try {
            if (!applyPreferredDevice(current)) {
                mutableState.value = mutableState.value.copy(error = "系统未接受所选输出，请在系统媒体输出中选择后重试。")
                return
            }
            if (audio.requestAudioFocus(focus) != AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
                mutableState.value = mutableState.value.copy(error = "系统暂未允许音乐播放，请结束其他通话或音频任务后重试。")
                return
            }
            if (mutableState.value.positionMs >= mutableState.value.durationMs) current.seekTo(0)
            routeEstablished = false
            routeDeadlineMs = android.os.SystemClock.elapsedRealtime() + 2000
            current.start()
            mutableState.value = mutableState.value.copy(playing = true, error = null)
            refreshRoute(current)
            handler.removeCallbacks(tick)
            handler.post(tick)
        } catch (error: Exception) {
            audio.abandonAudioFocusRequest(focus)
            mutableState.value = mutableState.value.copy(playing = false, error = "播放失败：${error.message}")
        }
    }

    fun pause() {
        audio.abandonAudioFocusRequest(focus)
        val current = player ?: return
        if (mutableState.value.ready) runCatching {
            if (current.isPlaying) current.pause()
            mutableState.value = mutableState.value.copy(playing = false, positionMs = current.currentPosition)
        }.onFailure { mutableState.value = mutableState.value.copy(playing = false) }
    }

    fun seek(positionMs: Int) {
        if (!mutableState.value.ready) return
        val position = positionMs.coerceIn(0, mutableState.value.durationMs)
        runCatching { player?.seekTo(position.toLong(), MediaPlayer.SEEK_CLOSEST) }
            .onSuccess { mutableState.value = mutableState.value.copy(positionMs = position) }
    }

    fun reportError(message: String) { mutableState.value = mutableState.value.copy(error = message) }

    fun close() {
        releasePlayer()
        audio.unregisterAudioDeviceCallback(devices)
    }

    private fun releasePlayer() {
        audio.abandonAudioFocusRequest(focus)
        handler.removeCallbacks(tick)
        val old = player
        player = null
        old?.removeOnRoutingChangedListener(routing)
        old?.release()
    }
}
