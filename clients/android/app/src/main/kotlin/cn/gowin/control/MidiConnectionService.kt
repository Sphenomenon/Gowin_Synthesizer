package cn.gowin.control

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

class MidiConnectionService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val keyboard get() = (application as ControlApplication).midiKeyboard

    override fun onCreate() {
        super.onCreate()
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("midi_connection", "25K MIDI 连接", NotificationManager.IMPORTANCE_LOW))
        try {
            ServiceCompat.startForeground(this, 2, notification(keyboard.state.value.connection),
                if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE else 0)
        } catch (error: Exception) {
            keyboard.reportError("无法保持 MIDI 后台连接：${error.message}；请保持应用前台。")
            stopSelf()
            return
        }
        scope.launch {
            keyboard.state.map { it.active to it.connection }.distinctUntilChanged().collect { (active, text) ->
                if (active) manager.notify(2, notification(text))
                else {
                    ServiceCompat.stopForeground(this@MidiConnectionService, ServiceCompat.STOP_FOREGROUND_REMOVE)
                    stopSelf()
                }
            }
        }
    }

    private fun notification(text: String): Notification {
        val open = PendingIntent.getActivity(this, 3,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val disconnect = PendingIntent.getService(this, 4,
            Intent(this, MidiConnectionService::class.java).setAction("disconnect"), PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, "midi_connection")
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle("Gowin Control · 25K MIDI")
            .setContentText(text).setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true)
            .addAction(0, "断开MIDI", disconnect).build()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "disconnect") keyboard.disconnect()
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
