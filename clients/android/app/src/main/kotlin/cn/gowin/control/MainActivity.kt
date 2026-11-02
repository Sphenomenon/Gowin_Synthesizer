package cn.gowin.control

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.content.*
import android.content.pm.PackageManager
import android.media.MediaPlayer
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.lifecycle.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import cn.gowin.control.data.*
import kotlinx.coroutines.*
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {
    private var player:MediaPlayer?=null
    override fun onCreate(savedInstanceState:Bundle?){
        super.onCreate(savedInstanceState)
        setContent {
            val model:ControlViewModel=viewModel(factory=object:ViewModelProvider.Factory{
                override fun <T:ViewModel> create(modelClass:Class<T>):T {
                    @Suppress("UNCHECKED_CAST") return ControlViewModel((application as ControlApplication).workstation, (application as ControlApplication).musicPlayback, (application as ControlApplication).midiKeyboard) as T
                }
            })
            MaterialTheme(colorScheme=darkColorScheme(primary=Color(0xFF77DFBE),secondary=Color(0xFFA5B9F1),background=Color(0xFF10141D),surface=Color(0xFF191F2B))) {
                ControlRoot(model,::connectReal,::stopConnection,::play,::share){player?.pause()}
            }
        }
    }
    private fun connectReal(address:String){
        try{ContextCompat.startForegroundService(this,Intent(this,ConnectionService::class.java).setAction("connect").putExtra("address",address))}
        catch(e:Exception){(application as ControlApplication).workstation.error(e.message)}
    }
    private fun stopConnection(){stopService(Intent(this,ConnectionService::class.java));(application as ControlApplication).workstation.disconnect()}
    private fun play(file:File){
        (application as ControlApplication).musicPlayback.pause()
        player?.release();player=null
        try{player=MediaPlayer().apply{setDataSource(file.absolutePath);prepare();start();setOnCompletionListener{it.release();if(player===it)player=null}}}
        catch(e:Exception){player?.release();player=null;(application as ControlApplication).workstation.error("试听失败：${e.message}")}
    }
    private fun share(entry:SavedRecording){
        val uri=FileProvider.getUriForFile(this,"$packageName.files",entry.file)
        startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply{type="audio/wav";putExtra(Intent.EXTRA_STREAM,uri);clipData=ClipData.newRawUri("WAV",uri);addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)},"分享录音"))
    }
    override fun onStop(){(application as ControlApplication).midiKeyboard.releaseControls();player?.pause();(application as ControlApplication).musicPlayback.pause();super.onStop()}
    override fun onDestroy(){player?.release();super.onDestroy()}
}

class ControlViewModel(val repo:Workstation,val music:MusicPlayback,val midi:MidiKeyboard?=null):ViewModel(){
    val state=repo.state
    val devices=repo.scanner.devices
    fun action(block:suspend ()->Unit){
        viewModelScope.launch {
            repo.setBusy(true)
            try{block()}catch(e:CancellationException){throw e}catch(e:Exception){repo.error(e.message ?: "操作失败")}
            finally{repo.setBusy(false)}
        }
    }
    fun demo(){action{repo.connect(true)}}
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ControlRoot(vm:ControlViewModel,connect:(String)->Unit,disconnect:()->Unit,play:(File)->Unit,share:(SavedRecording)->Unit,pausePlayback:()->Unit){
    val s by vm.state.collectAsStateWithLifecycle()
    val devices by vm.devices.collectAsStateWithLifecycle()
    val midiState = vm.midi?.state?.collectAsStateWithLifecycle()?.value
    val context=androidx.compose.ui.platform.LocalContext.current
    val scope=rememberCoroutineScope()
    var tab by rememberSaveable{mutableIntStateOf(0)}
    var showDevices by rememberSaveable{mutableStateOf(false)}
    var pendingExport by remember{mutableStateOf<SavedRecording?>(null)}
    val export=rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("audio/wav")){uri->
        val entry=pendingExport;pendingExport=null
        if(uri!=null&&entry!=null) scope.launch {
            try{withContext(Dispatchers.IO){context.contentResolver.openOutputStream(uri,"w")?.use{out->entry.file.inputStream().use{it.copyTo(out)}} ?: error("无法打开导出文件")}}
            catch(e:Exception){vm.repo.error("导出失败：${e.message}")}
        }
    }
    val bluetoothPermissions=remember{
        if(Build.VERSION.SDK_INT>=31)arrayOf(Manifest.permission.BLUETOOTH_SCAN,Manifest.permission.BLUETOOTH_CONNECT)
        else arrayOf(Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION)
    }
    val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()){result->
        if(bluetoothPermissions.all{result[it]==true||ContextCompat.checkSelfPermission(context,it)==PackageManager.PERMISSION_GRANTED})vm.repo.scan()
        else vm.repo.error("需要附近设备权限才能查找工作站；可在系统设置中授权，或使用模拟模式")
    }
    val enableBluetooth=rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()){}
    val notifyPermission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()){}
    val scan={
        if(bluetoothPermissions.all{ContextCompat.checkSelfPermission(context,it)==PackageManager.PERMISSION_GRANTED})vm.repo.scan()
        else permission.launch(bluetoothPermissions)
    }
    var clock by remember{mutableLongStateOf(SystemClock.elapsedRealtime())}
    LaunchedEffect(Unit){while(true){delay(1000);clock=SystemClock.elapsedRealtime()}}
    Scaffold(topBar={TopAppBar(title={Column{Text("GOWIN",fontWeight=FontWeight.Bold);Text("SYNTHESIZER CONTROL",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.primary)}},actions={
        TextButton(onClick={showDevices=true}){Text(if(s.ready)s.name else "连接工作站")}
    })},bottomBar={NavigationBar{
        listOf("控制","录音","作品","音乐").forEachIndexed{i,title->NavigationBarItem(selected=tab==i,onClick={if(tab==2&&i!=2)pausePlayback();tab=i},icon={Text(listOf("◉","●","♫","▷")[i])},label={Text(title)})}
    }}){padding->
        Column(Modifier.padding(padding).fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal=20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)){
            Card(Modifier.fillMaxWidth()){
                Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(6.dp)){
                    Text(if(s.demo)"模拟工作站 · 不代表实板结果"else "工作站业务连接",color=MaterialTheme.colorScheme.primary,style=MaterialTheme.typography.labelLarge)
                    Text(s.connection,style=MaterialTheme.typography.titleMedium)
                    if(s.updatedAt>0)Text(if(clock-s.updatedAt>3000)"状态已陈旧，请刷新或重连"else "状态已同步",style=MaterialTheme.typography.bodySmall)
                    if(!s.ready) Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){
                        Button(enabled=!s.busy,onClick={showDevices=true}){Text("查找工作站")}
                        OutlinedButton(enabled=!s.busy,onClick={vm.demo()}){Text("体验模拟设备")}
                    }
                    midiState?.let { midi ->
                        HorizontalDivider()
                        Text("25K MIDI · 独立连接", color=MaterialTheme.colorScheme.primary, style=MaterialTheme.typography.labelLarge)
                        Text(midi.connection, style=MaterialTheme.typography.bodyMedium)
                        Text("切页或切到后台仅停音，不主动断开 MIDI。", style=MaterialTheme.typography.bodySmall)
                        midi.error?.let { Text(it, color=MaterialTheme.colorScheme.error, style=MaterialTheme.typography.bodySmall) }
                    }
                }
            }
            s.error?.let{message->Card(colors=CardDefaults.cardColors(containerColor=MaterialTheme.colorScheme.errorContainer)){
                Column(Modifier.padding(14.dp)){Text(message);TextButton(onClick={vm.repo.error(null)}){Text("关闭提示")}}
            }}
            if(s.busy)LinearProgressIndicator(Modifier.fillMaxWidth())
            when(tab){
                0->Controls(s,vm){tab=3}
                1->Recording(s,vm){
                    if(Build.VERSION.SDK_INT>=33&&!s.demo&&ContextCompat.checkSelfPermission(context,Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)notifyPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                    vm.repo.download()
                }
                2->Library(s,vm,play,share){pendingExport=it;export.launch(it.name+".wav")}
                3->Music(vm.music,vm.midi,pausePlayback)
            }
            Spacer(Modifier.height(16.dp))
        }
    }
    if(showDevices)AlertDialog(onDismissRequest={showDevices=false;vm.repo.stopScan()},title={Text("连接工作站")},text={
        Column(Modifier.heightIn(max=400.dp).verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(10.dp)){
            Text("扫描提供 GOWIN 业务服务的设备，包括 GW25K-PROTO。")
            Row{TextButton(onClick=scan){Text("扫描 10 秒")};TextButton(onClick={runCatching{enableBluetooth.launch(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))}.onFailure{vm.repo.error(it.message)}}){Text("开启蓝牙")}}
            devices.forEach{d->OutlinedButton(modifier=Modifier.fillMaxWidth(),onClick={vm.repo.stopScan();showDevices=false;connect(d.address)}){
                Column{Text(d.name);Text("${d.address} · ${d.rssi} dBm",style=MaterialTheme.typography.labelSmall)}
            }}
            if(devices.isEmpty())Text("尚未发现设备",style=MaterialTheme.typography.bodySmall)
            TextButton(onClick={context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:${context.packageName}")))}){Text("打开应用权限设置")}
            if(s.ready)TextButton(onClick={disconnect();showDevices=false}){Text("断开当前设备")}
        }
    },confirmButton={TextButton(onClick={showDevices=false;vm.repo.stopScan()}){Text("关闭")}})
}

@Composable private fun Section(title:String,content:@Composable ColumnScope.()->Unit){
    Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){Text(title,style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.SemiBold);content()} }
}
@Composable private fun Choices(title:String,options:List<String>,selected:Int,enabled:Boolean,onSelect:(Int)->Unit){
    Text(title,style=MaterialTheme.typography.labelLarge)
    options.chunked(3).forEachIndexed{row,list->Row(horizontalArrangement=Arrangement.spacedBy(6.dp)){
        list.forEachIndexed{index,text->val value=row*3+index;FilterChip(selected=selected==value,onClick={onSelect(value)},enabled=enabled,label={Text(text)})}
    }}
}
@Composable private fun ParamSlider(title:String,id:Int,s:WorkstationState,vm:ControlViewModel){
    val actual=s.parameters[id]?.toFloat() ?: if(id==1)s.snapshot.volume.toFloat()else 0f
    var value by remember(id){mutableFloatStateOf(actual)}
    LaunchedEffect(actual){value=actual}
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(title);Text(value.toInt().toString())}
    Slider(value=value,onValueChange={value=it},valueRange=0f..127f,enabled=s.ready&&!s.busy&&s.capability?.has(1)==true&&id in s.parameters,
        onValueChangeFinished={vm.action{vm.repo.setParameter(id,value.toLong())}})
}
@Composable internal fun Controls(s:WorkstationState,vm:ControlViewModel,openMusic:()->Unit){
    val capability=s.capability
    if(capability?.protocolTestOnly==true || s.builtInAudioTest) {
        Section(if(s.builtInAudioTest)"25K 内置音频测试"else"25K 最小协议联调") {
            Text("已完成 Capability → Response 订阅 → HELLO → GET_STATUS")
            Text(if(s.builtInAudioTest)"切换到录音页，可录制 FPGA 内置的 1 秒双声道提示音，下载后在作品页播放。音源为内置测试信号。"else"此固件仅验证命令收发，声音控制、录音和下载尚未接入。")
            Text("boot_id：${capability!!.boot.toString(16).padStart(16,'0')}")
            Text("快照 ${s.snapshot.id} · 设备时间 ${s.snapshot.time} ms")
            Text("有效组 0x${s.snapshot.valid.toString(16)} · 控制窗口${if(s.snapshot.flags and 8L!=0L)"开启"else"关闭"}")
            OutlinedButton(enabled=s.ready&&!s.busy,onClick={vm.action{vm.repo.refreshStatus()}}){Text("发送 GET_STATUS")}
        }
        return
    }
    if(!s.demo && capability!=null && !capability.has(0) && !capability.has(1)) {
        Section("设备业务") {
            Text("当前设备未开放手机参数控制。")
            Text("参数请在工作站或25K面板上调整。")
            Text("设备录音：${if(capability.has(3)||capability.has(4))"已开放"else"未开放"}")
            Text("录音下载：${if(capability.has(5))"已开放"else"未开放"}")
            if(capability.has(3)||capability.has(4)||capability.has(5)) {
                Text("在录音页操作设备录音和下载；录音状态以设备读取结果为准。")
            }
            Text("音乐页可选择手机音频，通过系统蓝牙媒体连接播放到工作站。")
            Button(onClick=openMusic){Text("前往音乐")}
            OutlinedButton(enabled=s.ready&&!s.busy,onClick={vm.action{vm.repo.refresh()}}){Text("刷新状态")}
        }
        return
    }
    val enabled=s.ready&&!s.busy&&s.capability?.has(1)==true&&s.snapshot.valid(0)
    Section("声音"){
        Choices("合成模式",listOf("A · 单分音","B · 4 分音","C · 32 分音"),s.snapshot.mode,enabled&&2 in s.parameters){vm.action{vm.repo.setParameter(2,it.toLong())}}
        if(s.snapshot.flags and 1!=0L)Text("请求模式 ${s.snapshot.requestedMode}，等待当前声部结束",color=MaterialTheme.colorScheme.secondary)
        Choices("内置音色",listOf("笛","弦","铜管","马林巴","钢琴"),s.snapshot.profile,enabled&&3 in s.parameters){vm.action{vm.repo.setParameter(3,it.toLong())}}
        ParamSlider("主音量",1,s,vm)
        Choices("输出路由",listOf("立体声","仅左","仅右","静音"),s.snapshot.route,enabled&&4 in s.parameters){vm.action{vm.repo.setParameter(4,it.toLong())}}
    }
    Section("表达"){ParamSlider("颤音深度",5,s,vm);ParamSlider("滑音",6,s,vm)}
    var chain by remember(s.snapshot.effects){mutableStateOf(s.snapshot.effects)}
    var effectEnabled by remember(s.snapshot.effectsEnabled){mutableStateOf(s.snapshot.effectsEnabled)}
    Section("效果链"){
        Row(verticalAlignment=Alignment.CenterVertically){Text("效果总开关",Modifier.weight(1f));Switch(checked=effectEnabled,onCheckedChange={effectEnabled=it},enabled=enabled)}
        Row(horizontalArrangement=Arrangement.spacedBy(6.dp)){listOf("延迟","合唱","混响").forEachIndexed{id,name->FilterChip(selected=id in chain,enabled=enabled,onClick={chain=if(id in chain)chain-id else chain+id},label={Text(name)})}}
        chain.forEachIndexed{index,id->Row(verticalAlignment=Alignment.CenterVertically){
            Text("${index+1}. ${listOf("延迟","合唱","混响")[id]}",Modifier.weight(1f))
            TextButton(enabled=enabled&&index>0,onClick={chain=chain.toMutableList().apply{val a=this[index-1];this[index-1]=this[index];this[index]=a}}){Text("上移")}
            TextButton(enabled=enabled&&index<chain.lastIndex,onClick={chain=chain.toMutableList().apply{val a=this[index+1];this[index+1]=this[index];this[index]=a}}){Text("下移")}
        }}
        Button(enabled=enabled,onClick={vm.action{vm.repo.setEffects(effectEnabled,chain)}}){Text("应用效果顺序")}
    }
    Section("实时状态"){
        Text("活动声部：${if(s.snapshot.valid(1))s.snapshot.voices.toString()else "暂无数据"}")
        if(s.snapshot.valid(3)){
            Text("左声道");LinearProgressIndicator(progress={s.snapshot.leftPeak/65535f},modifier=Modifier.fillMaxWidth())
            Text("右声道");LinearProgressIndicator(progress={s.snapshot.rightPeak/65535f},modifier=Modifier.fillMaxWidth())
        }else Text("电平：暂无数据")
        if(s.snapshot.valid(4))Text("截止期 ${s.snapshot.deadline} · 欠载 ${s.snapshot.underrun}\n丢音 ${s.snapshot.noteDrop} · 录音丢帧 ${s.snapshot.recordDrop}")
        if(s.snapshot.flags and 2!=0L)Text("检测到削波",color=MaterialTheme.colorScheme.error)
        OutlinedButton(enabled=s.ready&&!s.busy,onClick={vm.action{vm.repo.refresh()}}){Text("刷新状态")}
    }
}
@Composable private fun Recording(s:WorkstationState,vm:ControlViewModel,download:()->Unit){
    val capability=s.capability
    if(capability!=null && !capability.has(3) && !capability.has(4)) {
        Section("设备录音") { Text("当前设备未提供录音能力。25K 最小测试请在控制页发送 GET_STATUS。") }
        return
    }
    val rec=s.record
    var seconds by rememberSaveable{mutableStateOf("0")}
    var clear by remember{mutableStateOf(false)}
    var cancel by remember{mutableStateOf(false)}
    Section(if(s.builtInAudioTest)"内置测试音频录音槽"else"设备录音槽"){
        Text("48 kHz · 双声道 · PCM16",color=MaterialTheme.colorScheme.secondary)
        Text("状态：${listOf("空闲","正在启动","正在录音","正在封存","可下载","错误").getOrElse(rec?.state ?: -1){"等待读取"}}")
        Text("${duration(rec?.frames ?: 0,rec?.sampleRate ?: 48000)} / 容量 ${duration(rec?.capacity ?: 0,rec?.sampleRate ?: 48000)}")
        if(rec?.incomplete==true)Text("录音曾中断（原因 ${rec.reason}），下载的是已封存片段",color=MaterialTheme.colorScheme.error)
        OutlinedTextField(seconds,{seconds=it.filter(Char::isDigit).take(5)},label={Text("最大时长（秒，0 为容量上限）")},singleLine=true,enabled=rec?.state==0&&!s.busy)
        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){
            Button(enabled=s.ready&&!s.busy&&rec?.state==0,onClick={vm.action{vm.repo.startRecording(seconds.toIntOrNull() ?: 0)}}){Text("开始录音")}
            OutlinedButton(enabled=s.ready&&!s.busy&&rec?.state==2,onClick={vm.action{vm.repo.stopRecording()}}){Text("停止")}
        }
        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){
            OutlinedButton(enabled=s.ready&&!s.busy,onClick={vm.action{vm.repo.refreshRecord()}}){Text("读取录音信息")}
            TextButton(enabled=s.ready&&!s.busy&&rec?.state in listOf(4,5)&&!s.download.active,onClick={clear=true}){Text("清除设备录音")}
        }
        if(s.builtInAudioTest)Text("FPGA 内置左右不同频率的提示音，容量 1 秒；0 表示录满。支持提前停止。",style=MaterialTheme.typography.bodySmall)
        if(s.demo)Text("模拟录音容量 10 秒，生成左右不同频率的测试 WAV。",style=MaterialTheme.typography.bodySmall)
    }
    Section("下载到手机"){
        Text(s.download.phase)
        LinearProgressIndicator(progress={s.download.fraction},modifier=Modifier.fillMaxWidth())
        Text("${(s.download.fraction*100).toInt()}% · ${s.download.confirmed/1024} / ${s.download.total/1024} KiB")
        if(s.download.speed>0)Text("${"%.1f".format(s.download.speed/1024)} KiB/s · 预计剩余 ${((s.download.total-s.download.confirmed)/s.download.speed).toLong()} 秒")
        Text("接收 ${s.download.received} · 已保存 ${s.download.durable} · 已确认 ${s.download.confirmed}",style=MaterialTheme.typography.labelSmall)
        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){
            Button(enabled=s.ready&&rec?.ready==true&&!s.download.active&&s.capability?.has(5)==true,onClick=download){Text("下载 / 继续")}
            OutlinedButton(enabled=s.download.active,onClick={vm.repo.pauseDownload()}){Text("暂停")}
            TextButton(enabled=s.download.total>0,onClick={cancel=true}){Text("取消")}
        }
        Text("校验通过后生成 WAV。原音质下载耗时由设备链路决定，切换页面不影响活跃任务。",style=MaterialTheme.typography.bodySmall)
    }
    if(clear)AlertDialog(onDismissRequest={clear=false},title={Text("清除设备录音？")},text={Text("设备上的录音将被删除，手机已下载作品保留。")},confirmButton={TextButton(onClick={clear=false;vm.action{vm.repo.clearRecording()}}){Text("确认清除")}},dismissButton={TextButton(onClick={clear=false}){Text("返回")}})
    if(cancel)AlertDialog(onDismissRequest={cancel=false},title={Text("取消下载")},text={Text("可保留进度以后继续，或删除手机上的临时文件。设备录音不会清除。")},confirmButton={TextButton(onClick={cancel=false;vm.repo.discardPartial()}){Text("删除临时文件")}},dismissButton={TextButton(onClick={cancel=false;vm.repo.pauseDownload()}){Text("保留进度")}})
}
@Composable private fun Library(s:WorkstationState,vm:ControlViewModel,play:(File)->Unit,share:(SavedRecording)->Unit,export:(SavedRecording)->Unit){
    var rename by remember{mutableStateOf<SavedRecording?>(null)}
    var name by remember{mutableStateOf("")}
    var remove by remember{mutableStateOf<SavedRecording?>(null)}
    if(s.library.isEmpty())Section("本地作品"){Text("尚无录音。连接工作站或体验模拟设备后，录音并下载即可在此试听和导出。")}
    s.library.forEach{entry->Section(entry.name){
        Text("${duration(entry.bytes/4,entry.sampleRate)} · ${entry.bytes/1024} KiB · WAV")
        Text(SimpleDateFormat("yyyy-MM-dd HH:mm",Locale.getDefault()).format(Date(entry.savedAt))+" 保存",style=MaterialTheme.typography.bodySmall)
        if(entry.source=="builtin")Text("FPGA 内置测试音频",color=MaterialTheme.colorScheme.secondary)
        if(entry.demo)Text("模拟测试音频",color=MaterialTheme.colorScheme.secondary)
        if(entry.incomplete)Text("录音曾中断",color=MaterialTheme.colorScheme.error)
        Row{TextButton(onClick={play(entry.file)}){Text("试听")};TextButton(onClick={export(entry)}){Text("导出")};TextButton(onClick={share(entry)}){Text("分享")}}
        Row{TextButton(onClick={rename=entry;name=entry.name}){Text("重命名")};TextButton(onClick={remove=entry}){Text("删除")}}
    }}
    if(rename!=null)AlertDialog(onDismissRequest={rename=null},title={Text("重命名作品")},text={OutlinedTextField(name,{name=it.take(80)},singleLine=true)},confirmButton={TextButton(enabled=name.isNotBlank(),onClick={val e=rename!!;rename=null;vm.action{vm.repo.rename(e,name)}}){Text("保存")}},dismissButton={TextButton(onClick={rename=null}){Text("取消")}})
    if(remove!=null)AlertDialog(onDismissRequest={remove=null},title={Text("删除本地作品？")},text={Text("仅删除手机上的文件，不影响设备录音。")},confirmButton={TextButton(onClick={val e=remove!!;remove=null;vm.action{vm.repo.delete(e)}}){Text("删除")}},dismissButton={TextButton(onClick={remove=null}){Text("取消")}})
}
private fun duration(frames:Long,sampleRate:Long):String{val seconds=frames/sampleRate;return "%02d:%02d".format(seconds/60,seconds%60)}


@Composable internal fun Music(music:MusicPlayback,midi:MidiKeyboard?,pauseLibrary:()->Unit){
    val state by music.state.collectAsStateWithLifecycle()
    val context=androidx.compose.ui.platform.LocalContext.current
    val choose=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()){uri->
        if(uri!=null){
            runCatching{context.contentResolver.takePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION)}
            pauseLibrary();music.select(uri)
        }
    }
    val pair={
        runCatching{context.startActivity(Intent(Settings.ACTION_BLUETOOTH_SETTINGS))}
            .onFailure{music.reportError("无法打开系统蓝牙设置：${it.message}")}
        Unit
    }
    Section("手机音频播放"){
        Text("先选择实际输出。手机本地播放可用扬声器或耳机；发送至138K时，在系统连接其蓝牙媒体音频，再选择对应设备。")

        OutlinedButton(onClick=pair){Text("连接蓝牙媒体音频")}
        Text(if(state.a2dpAvailable)"已检测到蓝牙媒体设备"else "蓝牙媒体未连接",color=if(state.a2dpAvailable)MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.secondary)
        state.outputs.forEach { output ->
            FilterChip(selected=state.selectedOutputId==output.id,onClick={music.selectOutput(output.id)},
                label={Text((if(output.a2dp) "蓝牙媒体 · " else "本地 · ")+output.name)})
        }
        Text("实际输出：${state.output}",style=MaterialTheme.typography.bodySmall)
        Text(if(state.routeConfirmed) "已确认实际路由与选择一致" else "实际路由尚未确认",style=MaterialTheme.typography.bodySmall)
        Button(onClick={choose.launch(arrayOf("audio/*"))}){Text(if(state.name==null)"选择音频文件"else "更换音频文件")}
        state.name?.let{Text(it,style=MaterialTheme.typography.titleSmall)}
        if(state.preparing)LinearProgressIndicator(Modifier.fillMaxWidth())
        if(state.ready){
            var position by remember(state.name){mutableFloatStateOf(state.positionMs.toFloat())}
            var dragging by remember{mutableStateOf(false)}
            LaunchedEffect(state.positionMs){if(!dragging)position=state.positionMs.toFloat()}
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                Text(playbackTime(position.toInt()));Text(playbackTime(state.durationMs))
            }
            Slider(value=position.coerceIn(0f,state.durationMs.coerceAtLeast(1).toFloat()),
                valueRange=0f..state.durationMs.coerceAtLeast(1).toFloat(),
                onValueChange={dragging=true;position=it},onValueChangeFinished={music.seek(position.toInt());dragging=false})
            Button(enabled=state.playing||state.outputs.any{it.id==state.selectedOutputId},onClick={pauseLibrary();if(state.playing)music.pause()else music.play()}){
                Text(if(state.playing)"暂停"else "播放所选音频")
            }
        }
        state.error?.let{Text(it,color=MaterialTheme.colorScheme.error)}
        Text("选择设备只是向系统提出路由请求；播放后根据实际路由确认，输出丢失或不符会暂停。BLE MIDI／业务连接不代表蓝牙媒体已连接。进入后台暂停。",style=MaterialTheme.typography.bodySmall)
    }
    if(midi!=null) MidiKeyboardPanel(midi)
}

private fun playbackTime(milliseconds:Int):String{
    val seconds=milliseconds.coerceAtLeast(0)/1000
    return "${seconds/60}:${(seconds%60).toString().padStart(2,'0')}"
}
