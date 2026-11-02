package cn.gowin.control

import android.app.Application
import android.content.Intent
import androidx.core.content.ContextCompat
import cn.gowin.control.data.Workstation
import cn.gowin.control.data.MusicPlayback
import cn.gowin.control.data.MidiKeyboard
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

class ControlApplication : Application() {
    val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate)
    val musicPlayback by lazy { MusicPlayback(this) }
    val midiKeyboard by lazy {
        MidiKeyboard(this, scope).also { keyboard ->
            scope.launch {
                keyboard.state.map { it.active }.distinctUntilChanged().filter { it }.collect {
                    try {
                        ContextCompat.startForegroundService(this@ControlApplication, Intent(this@ControlApplication, MidiConnectionService::class.java))
                    } catch (error: Exception) {
                        keyboard.reportError("无法启动 MIDI 后台连接服务：${error.message}；请保持应用前台。")
                    }
                }
            }
        }
    }
    val workstation by lazy { Workstation(this,scope) }
}
