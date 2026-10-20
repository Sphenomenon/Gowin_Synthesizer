package cn.gowin.control

import android.app.*
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

/** Started by a visible user action; owns the live real-device session across navigation/lock screen. */
@OptIn(kotlinx.coroutines.FlowPreview::class)
class ConnectionService : Service() {
    private val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate)
    private val repo get()=(application as ControlApplication).workstation
    private var connectJob: Job?=null
    override fun onCreate() {
        super.onCreate()
        getSystemService(NotificationManager::class.java).createNotificationChannel(NotificationChannel("connection","设备连接与下载",NotificationManager.IMPORTANCE_LOW))
        scope.launch {
            repo.state.sample(1000).collect { s ->
                val text=if(s.download.active)"${s.download.phase} · ${(s.download.fraction*100).toInt()}%"else s.connection
                getSystemService(NotificationManager::class.java).notify(1,notification(text))
            }
        }
    }
    private fun notification(text:String): Notification {
        val open=PendingIntent.getActivity(this,0,Intent(this,MainActivity::class.java),PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val pause=PendingIntent.getService(this,1,Intent(this,ConnectionService::class.java).setAction("pause"),PendingIntent.FLAG_IMMUTABLE)
        val stop=PendingIntent.getService(this,2,Intent(this,ConnectionService::class.java).setAction("disconnect"),PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this,"connection").setSmallIcon(android.R.drawable.stat_sys_data_bluetooth).setContentTitle("Gowin Control")
            .setContentText(text).setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true)
            .addAction(0,"暂停下载",pause).addAction(0,"断开",stop).build()
    }
    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int {
        when(intent?.action) {
            "pause" -> repo.pauseDownload()
            "disconnect" -> {repo.disconnect();stopSelf()}
            "connect" -> {
                try {
                    ServiceCompat.startForeground(this,1,notification("正在连接设备"),if(Build.VERSION.SDK_INT>=29)ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE else 0)
                    connectJob?.cancel()
                    connectJob=scope.launch {
                        try{repo.connect(false,intent.getStringExtra("address") ?: error("缺少设备地址"))}
                        catch(e:CancellationException){throw e}
                        catch(_:Exception){stopSelf()}
                    }
                }catch(e:Exception){repo.error(e.message ?: "无法启动设备连接服务");stopSelf()}
            }
        }
        return START_NOT_STICKY
    }
    override fun onDestroy(){connectJob?.cancel();scope.cancel();if(!repo.state.value.demo)repo.disconnect();super.onDestroy()}
    override fun onBind(intent:Intent?):IBinder?=null
}
