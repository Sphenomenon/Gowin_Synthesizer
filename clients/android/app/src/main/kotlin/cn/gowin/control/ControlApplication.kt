package cn.gowin.control

import android.app.Application
import cn.gowin.control.data.Workstation
import cn.gowin.control.data.MusicPlayback
import cn.gowin.control.data.MidiKeyboard
import kotlinx.coroutines.*

class ControlApplication : Application() {
    val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate)
    val musicPlayback by lazy { MusicPlayback(this) }
    val midiKeyboard by lazy { MidiKeyboard(this, scope) }
    val workstation by lazy { Workstation(this,scope) }
}
