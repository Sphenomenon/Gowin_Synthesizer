package cn.gowin.control

import android.app.Application
import cn.gowin.control.data.Workstation
import kotlinx.coroutines.*

class ControlApplication : Application() {
    val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate)
    val workstation by lazy { Workstation(this,scope) }
}
