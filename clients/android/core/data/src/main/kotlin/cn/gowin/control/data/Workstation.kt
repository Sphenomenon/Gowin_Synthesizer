package cn.gowin.control.data

import android.content.Context
import android.os.SystemClock
import cn.gowin.control.ble.*
import cn.gowin.control.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.io.File
import java.io.IOException
import java.io.RandomAccessFile
import java.util.zip.CRC32

data class DownloadState(val phase: String="未下载",val received: Long=0,val durable: Long=0,val confirmed: Long=0,val total: Long=0,val speed: Double=0.0,val active: Boolean=false) {
    val fraction get()=if(phase=="下载完成")1f else if(total>0)(confirmed.toDouble()/total).toFloat().coerceIn(0f,1f)else 0f
}
data class WorkstationState(
    val connection: String="未连接",val ready: Boolean=false,val demo: Boolean=false,val name: String="GW138K",
    val capability: Capability?=null,val snapshot: Snapshot=Snapshot(),val record: RecordingInfo?=null,
    val parameters: Map<Int,Long> = emptyMap(),val updatedAt: Long=0,val error: String?=null,
    val busy: Boolean=false,val download: DownloadState=DownloadState(),val library: List<SavedRecording> = emptyList()
) {
    val builtInAudioTest get() = !demo && name=="GW25K-PROTO" && capability?.flags==0x68L
}

class Workstation(context: Context,private val scope: CoroutineScope) {
    val scanner=AndroidBleTransport(context.applicationContext)
    private val files=RecordingFiles(context.filesDir)
    private val _state=MutableStateFlow(WorkstationState(library=files.library()))
    val state=_state.asStateFlow()
    private var transport: BleTransport?=null
    private var session: ProtocolSession?=null
    private var events: Job?=null
    private var poll: Job?=null
    private var watcher: Job?=null
    private var scanJob: Job?=null
    private var downloadJob: Job?=null
    private val mutation=Mutex()
    private val connectionLock=Mutex()
    private var demoPeripheral: DemoTransport?=null
    private var lastAddress: String?=null
    private var lastDemo=false
    fun error(message: String?) { _state.update{it.copy(error=message)} }
    fun scan() {
        runCatching{scanner.startScan{error(it)}}.onFailure{error(it.message ?: "无法扫描，请检查权限")}
        scanJob?.cancel();scanJob=scope.launch{delay(10000);scanner.stopScan()}
    }
    fun stopScan() { scanner.stopScan();scanJob?.cancel() }
    suspend fun connect(demo: Boolean,address: String="demo",recovery: Boolean=false)=connectionLock.withLock {
        if(!recovery) { downloadJob?.cancelAndJoin();downloadJob=null }
        closeSession()
        lastAddress=address;lastDemo=demo
        _state.update{it.copy(ready=false,busy=true,connection="连接并发现服务…",demo=demo,name=if(demo)"模拟工作站"else scanner.devices.value.firstOrNull{it.address==address}?.name ?: "GOWIN · $address",error=null,capability=null,parameters=emptyMap(),snapshot=Snapshot(),updatedAt=0,record=null)}
        try {
            val t=if(demo) demoPeripheral ?: DemoTransport(scope).also{demoPeripheral=it} else AndroidBleTransport(appContext)
            transport=t;t.connect(address)
            _state.update{it.copy(connection="订阅通知与协议握手…")}
            val s=ProtocolSession(t,scope);session=s
            val cap=s.handshake();_state.update{it.copy(capability=cap)}
            if(cap.has(3) || cap.has(4) || cap.has(5))s.negotiateRecordingFormats()
            events=scope.launch(start=CoroutineStart.UNDISPATCHED) {
                s.events.collect { m -> if(m.opcode in 0xe1..0xe3) runCatching{acceptSnapshot(Snapshot.decode(m.payload))} }
            }
            refresh()
            val params=mutableMapOf<Int,Long>()
            if(cap.has(0)) for(id in 1..7) {
                try { params[id]=parameterResponse(s.request(Op.GET_PARAM,Writer().u16(id).build()).message.payload).second }
                catch(e:DeviceError){if(e.code!=0x80)throw e}
            }
            _state.update{it.copy(parameters=params)}
            if(cap.has(2)) subscribe(200)
            _state.update{it.copy(ready=true,connection=when {
                _state.value.builtInAudioTest->"已连接 · 内置音频录音测试"
                cap.protocolTestOnly->"已连接 · 最小协议测试"
                cap.has(0)||cap.has(1)->"已连接 · 可控制"
                cap.has(3)||cap.has(4)||cap.has(5)->"已连接 · 录音服务"
                else->"已连接 · 业务服务"
            })}
            watcher=scope.launch {
                t.connected.filter{!it}.first()
                _state.update{it.copy(ready=false,connection=if(cap.protocolTestOnly)"连接已断开，可重新扫描连接"else"连接已断开，设备录音默认继续")}
            }
            poll=scope.launch {
                while(isActive) {
                    delay(1500)
                    if(!t.connected.value) break
                    runCatching {
                        if(_state.value.record?.state in 1..3) refreshRecord()
                        if(SystemClock.elapsedRealtime()-_state.value.updatedAt>3000 && !_state.value.download.active) refreshStatus()
                    }.onFailure { if(it !is CancellationException)error(it.message) }
                }
            }
        } catch(e:Exception) { closeSession();_state.update{it.copy(ready=false,connection="连接失败",error=e.message ?: "连接失败")};throw e }
        finally { _state.update{it.copy(busy=false)} }
    }
    // Retained application context only; never retain an Activity in GATT/service ownership.
    private val appContext=context.applicationContext
    private fun current()=session ?: throw IOException("请先连接设备")
    private suspend fun subscribe(period: Int) {
        current().request(Op.SUBSCRIBE,Writer().u16(15).u16(period).u16(1000).u16(0).build())
    }
    private fun acceptSnapshot(new: Snapshot) {
        _state.update { old ->
            if(old.updatedAt!=0L && new.id!=old.snapshot.id && !isNewerSequence(new.id,old.snapshot.id)) old
            else {
                val previous=old.snapshot
                val merged=new.copy(
                    revision=if(new.valid(0))new.revision else previous.revision,
                    requestedMode=if(new.valid(0))new.requestedMode else previous.requestedMode,
                    mode=if(new.valid(0))new.mode else previous.mode,
                    profile=if(new.valid(0))new.profile else previous.profile,
                    volume=if(new.valid(0))new.volume else previous.volume,
                    route=if(new.valid(0))new.route else previous.route,
                    effects=if(new.valid(0))new.effects else previous.effects,
                    effectsEnabled=if(new.valid(0))new.effectsEnabled else previous.effectsEnabled)
                val params=if(new.valid(0))old.parameters.mapValues{(key,value)->when(key){
                    1->new.volume.toLong();2->new.mode.toLong();3->new.profile.toLong();4->new.route.toLong();7->if(new.effectsEnabled)1L else 0L;else->value
                }}else old.parameters
                old.copy(snapshot=merged,parameters=params,updatedAt=SystemClock.elapsedRealtime())
            }
        }
    }
    suspend fun refreshStatus() { acceptSnapshot(Snapshot.decode(current().request(Op.STATUS).message.payload)) }
    suspend fun refreshRecord() {
        if(_state.value.capability?.has(3)!=true && _state.value.capability?.has(4)!=true)return
        val s=current()
        val rec=RecordingInfo.decode(s.request(Op.INFO,Writer().u32(0).build()).message.payload,s.recordingFormats)
        checkWire(rec.boot==_state.value.capability?.boot,"录音身份不匹配")
        _state.update{it.copy(record=rec)}
    }
    suspend fun refresh() { refreshStatus();refreshRecord() }
    private fun parameterResponse(raw: ByteArray): Pair<Int,Long> {
        checkWire(raw.size==20,"参数响应长度错误")
        val r=Reader(raw);val id=r.u16();r.zero(2);val actual=r.u32();r.u32();val rev=r.u32();r.u32()
        _state.update{it.copy(snapshot=it.snapshot.copy(revision=rev))}
        return id to actual
    }
    suspend fun setParameter(id: Int,value: Long)=mutation.withLock {
        check(_state.value.ready && _state.value.capability?.has(1)==true){"设备尚未开放参数设置"}
        try {
            val response=current().request(Op.SET_PARAM,Writer().u16(id).u16(0).u32(value).u32(_state.value.snapshot.revision).build()).message
            val p=parameterResponse(response.payload);_state.update{it.copy(parameters=it.parameters+p)}
            if(response.status==2) awaitOperation(Reader(response.payload.copyOfRange(16,20)).u32())
            refreshStatus()
        } catch(e:DeviceError){if(e.code==0x84)refreshStatus();throw e}
    }
    suspend fun setEffects(enabled: Boolean,chain: List<Int>)=mutation.withLock {
        check(_state.value.ready && _state.value.capability?.has(1)==true){"设备尚未开放效果设置"}
        check(chain.size<=3 && chain.distinct().size==chain.size)
        try {
            val p=Writer().u32(_state.value.snapshot.revision).u8(if(enabled&&chain.isNotEmpty())1 else 0).u8(chain.size)
                .bytes(ByteArray(3){chain.getOrElse(it){255}.toByte()}).bytes(ByteArray(3)).build()
            current().request(Op.SET_EFFECTS,p);refreshStatus()
        }catch(e:DeviceError){if(e.code==0x84)refreshStatus();throw e}
    }
    private suspend fun awaitOperation(id: Long) {
        checkWire(id!=0L,"后台任务编号无效")
        withTimeout(120000) {
            while(true) {
                delay(250)
                val raw=current().request(Op.OPERATION,Writer().u32(id).build()).message.payload
                checkWire(raw.size==20,"任务响应长度错误")
                val r=Reader(raw);checkWire(r.u32()==id,"任务身份错误");r.u32();r.u8();val phase=r.u8();val result=r.u8();r.zero(1)
                if(phase==2){checkWire(result==0,"后台任务未成功");break}
                if(phase==3)throw DeviceError(result)
            }
        }
    }
    suspend fun startRecording(seconds: Int,format: Int=1)=mutation.withLock {
        val rec=_state.value.record ?: throw IOException("请先读取录音能力")
        current().recordingFormats.validate(rec)
        require(seconds>=0)
        // A sealed object's rate does not identify the current DAC clock.
        // Selection is explicit; the device must reject a clock/format mismatch.
        val frames=seconds*current().recordingFormats.sampleRate(format)
        require(frames==0L||frames<=rec.capacity){"目标时长超过设备容量"}
        val m=current().request(Op.START,Writer().u8(format).u8(0).u16(0).u32(frames).build()).message
        val r=Reader(m.payload);val id=r.u32();r.u32();r.end();awaitOperation(id);refresh()
    }
    suspend fun stopRecording()=mutation.withLock {
        val rec=_state.value.record ?: throw IOException("没有录音")
        val m=current().request(Op.STOP,Writer().u64(rec.boot).u32(rec.id).build()).message
        val r=Reader(m.payload);val id=r.u32();r.u32();r.end();awaitOperation(id);refresh()
    }
    suspend fun clearRecording()=mutation.withLock {
        val rec=_state.value.record ?: throw IOException("没有录音")
        current().request(Op.CLEAR,Writer().u64(rec.boot).u32(rec.id).build());refresh()
    }
    fun download() {
        if(downloadJob?.isActive==true)return
        downloadJob=scope.launch {
            try {
                refreshRecord();val rec=_state.value.record ?: throw IOException("没有录音")
                current().recordingFormats.validate(rec,requireReady=true)
                var attempt=0
                while(true) {
                    try {
                        if(transport?.connected?.value!=true) {
                            if(attempt>=5)throw IOException("重连失败，请手动连接后继续下载")
                            _state.update{it.copy(download=it.download.copy(phase="等待重连并恢复",active=true))}
                            delay(listOf(1000L,2000L,4000L,8000L,15000L)[attempt++])
                            try {connect(lastDemo,lastAddress ?: "demo",recovery=true)}
                            catch(e:CancellationException){throw e}
                            catch(_:Exception){continue}
                            val current=_state.value.record
                            check(current!=null && rec.samePcmObject(current)){"设备端录音身份或格式已改变，无法续传"}
                        }
                        downloadOnce(rec);break
                    }
                    catch(e:CancellationException){throw e}
                    catch(e:Exception) {
                        if(e is DeviceError && e.code in listOf(0x85,0x87)) {
                            closeSession();_state.update{it.copy(ready=false,connection="会话失效，正在重连")}
                        }
                        if(transport?.connected?.value==true || attempt>=5)throw e
                    }
                }
            }catch(e:CancellationException){_state.update{it.copy(download=it.download.copy(phase="已暂停，可继续",active=false))};throw e}
            catch(e:Exception){_state.update{it.copy(error=e.message,download=it.download.copy(phase="下载失败，可重试",active=false))}}
            finally { transport?.priority(false);if(_state.value.ready && _state.value.capability?.has(2)==true)runCatching{subscribe(200)} }
        }
    }
    private suspend fun downloadOnce(info: RecordingInfo) {
        val s=current();val t=transport ?: throw IOException("连接已断开")
        s.recordingFormats.validate(info,requireReady=true)
        val formats=s.recordingFormats
        t.priority(true)
        if(_state.value.capability?.has(2)==true)subscribe(1000)
        var transfer=0L
        try {
            withContext(Dispatchers.IO){check(files.part(info).parentFile!!.usableSpace>info.bytes*2+1048576){"手机存储空间不足"}}
            val cp=withContext(Dispatchers.IO){files.recover(info)}
            _state.update{it.copy(download=DownloadState("正在打开录音",cp.offset,cp.offset,cp.offset,info.bytes,active=true),error=null)}
            val opened=s.openTransfer(info.boot,info.id,cp.offset).message
            val open=TransferOpen.decode(opened);transfer=open.transfer
            val max=open.maxChunk
            checkWire(open.bytes==info.bytes&&open.crc==info.crc&&open.offset==cp.offset,"下载对象或能力改变")
            val checksum=CRC32()
            withContext(Dispatchers.IO) {
                files.part(info).inputStream().use{input->val buf=ByteArray(32768);var remaining=cp.offset;while(remaining>0){val n=input.read(buf,0,minOf(buf.size.toLong(),remaining).toInt());check(n>0);checksum.update(buf,0,n);remaining-=n}}
            }
            var offset=cp.offset
            var previousCrc:Long?=null
            var windowStart=SystemClock.elapsedRealtime();var windowBytes=offset;var speed=0.0
            RandomAccessFile(files.part(info),"rw").use { output ->
                while(offset<info.bytes) {
                    currentCoroutineContext().ensureActive()
                    val n=minOf(max.toLong(),info.bytes-offset).toInt()
                    val reply=s.readBlock(transfer,offset,n,previousCrc)
                    val response=Reader(reply.message.payload)
                    checkWire(reply.message.payload.size==12&&response.u32()==transfer&&response.u32()==offset&&response.u16()==n,"READ 响应不匹配");response.zero(2)
                    val block=PcmBlock.decode(reply.data!!.payload,max)
                    checkWire(block.transfer==transfer&&block.boot==info.boot&&block.recording==info.id&&block.offset==offset&&block.data.size==n,"下载块对象或偏移不匹配")
                    if(previousCrc!=null)_state.update{it.copy(download=it.download.copy(confirmed=offset))}
                    val next=offset+n
                    _state.update{it.copy(download=it.download.copy(phase="下载中",received=next))}
                    withContext(Dispatchers.IO) { output.seek(offset);output.write(block.data);checksum.update(block.data);files.persist(info,output,next,checksum.value) }
                    _state.update{it.copy(download=it.download.copy(durable=next))}
                    previousCrc=block.crc
                    offset=next
                    val now=SystemClock.elapsedRealtime();if(now-windowStart>=1000){val sample=(offset-windowBytes)*1000.0/(now-windowStart);speed=if(speed==0.0)sample else speed*0.8+sample*0.2;windowStart=now;windowBytes=offset}
                    _state.update{it.copy(download=it.download.copy(speed=speed))}
                }
                previousCrc?.let{s.acknowledgeBlock(transfer,offset,it)}
                _state.update{it.copy(download=it.download.copy(confirmed=offset))}
            }
            _state.update{it.copy(download=it.download.copy(phase="校验完整录音"))}
            withContext(Dispatchers.IO){check(RecordingFiles.fileCrc(files.part(info))==info.crc){"完整录音 CRC32 不匹配"}}
            var closeWarning:String?=null
            try {
                val response=s.request(Op.CLOSE,Writer().u32(transfer).u32(info.crc).build()).message.payload
                checkWire(response.size==4 && Reader(response).u32()==transfer,"CLOSE 响应不匹配")
            }catch(e:CancellationException){throw e}
            catch(_:Exception){
                // A lost remote close must not discard a fully verified local recording.
                closeWarning="录音已完整校验并保存；设备传输关闭尚未确认，已断开连接以释放引用"
                t.close()
            }
            transfer=0
            _state.update{it.copy(download=it.download.copy(phase="生成 WAV 文件"))}
            withContext(Dispatchers.IO){files.packageWav(info,_state.value.demo,if(_state.value.builtInAudioTest)"builtin"else if(_state.value.demo)"demo"else"workstation",formats)}
            _state.update{it.copy(download=it.download.copy(phase="下载完成",active=false),library=files.library(),error=closeWarning)}
        } finally {
            if(transfer!=0L && t.connected.value)withContext(NonCancellable){withTimeoutOrNull(3000){runCatching{s.request(Op.CANCEL,Writer().u32(transfer).build())}}}
        }
    }
    fun pauseDownload() { downloadJob?.cancel() }
    fun discardPartial() { val rec=_state.value.record ?: return;scope.launch {downloadJob?.cancelAndJoin();withContext(Dispatchers.IO){files.discard(rec)};_state.update{it.copy(download=DownloadState("已取消并删除临时文件"))}} }
    fun rename(entry: SavedRecording,name:String){files.rename(entry,name);_state.update{it.copy(library=files.library())}}
    fun delete(entry: SavedRecording){files.delete(entry);_state.update{it.copy(library=files.library())}}
    fun disconnect() { downloadJob?.cancel();closeSession();_state.update{it.copy(ready=false,connection="未连接") } }
    private fun closeSession(){events?.cancel();poll?.cancel();watcher?.cancel();session?.close();session=null;transport?.close();transport=null}
    fun setBusy(busy:Boolean){_state.update{it.copy(busy=busy)}}
}
