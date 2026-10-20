package cn.gowin.control.data

import cn.gowin.control.ble.*
import cn.gowin.control.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import java.util.UUID
import kotlin.math.*

/** A protocol peripheral, not a UI stub: all commands pass through byte framing and CRC. */
class DemoTransport(private val scope: CoroutineScope) : BleTransport {
    private val _notifications=MutableSharedFlow<Notification>(extraBufferCapacity=256)
    override val notifications=_notifications.asSharedFlow()
    private val _connected=MutableStateFlow(false)
    override val connected=_connected.asStateFlow()
    private var incoming=Reassembler()
    private var nonce=0uL
    private var token=1
    private val boot=generateSequence { java.security.SecureRandom().nextLong().toULong() }.first{it!=0uL}
    private var snapshot=Snapshot(valid=31,capacity=480000,flags=8)
    private var pcm=byteArrayOf()
    private var record=RecordingInfo(boot,0,0,1,2,0,48000,0,0,480000,0,0,0,0)
    private val parameters=mutableMapOf(1 to 100L,2 to 2L,3 to 0L,4 to 0L,5 to 0L,6 to 0L,7 to 0L)
    private val replies=linkedMapOf<Long,Pair<ByteArray,Message>>()
    private val tasks=mutableMapOf<Long,ByteArray>()
    private var operation=1L
    private var nextRecord=1L
    private var transfer=0L
    private var cursor=0L
    private var inFlight: PcmBlock?=null
    private var previousAck: Pair<Long,Long>?=null
    private var started=0L
    private var maxFrames=480000L
    private var ticker: Job?=null
    private var statusPeriod=200L
    override suspend fun connect(address: String) {
        nonce=0uL; replies.clear(); incoming.clear(); transfer=0; inFlight=null
        _connected.value=true
        ticker?.cancel()
        ticker=scope.launch {
            while(isActive) {
                delay(statusPeriod)
                updateRecording()
                snapshot=snapshot.copy(id=(snapshot.id+1) and 0xffffffffL,time=(System.nanoTime()/1_000_000) and 0xffffffffL,
                    recordState=record.state,recordId=record.id,frames=record.frames,capacity=record.capacity,
                    voices=if(record.state==2) 3 else 0,leftPeak=if(record.state==2) 28000 else 0,rightPeak=if(record.state==2) 23000 else 0)
                if(nonce!=0uL) emit(GattIds.status,Message(Op.STATUS_EVENT,0,0,nonce,snapshot.encode()))
            }
        }
    }
    override suspend fun read(uuid: UUID): ByteArray {
        require(uuid==GattIds.capability)
        return Writer().u8(1).u8(20).u16(512).u64(boot).u32(0x6f).u16(256).u8(1).u8(1).build()
    }
    override suspend fun subscribe(uuid: UUID) {}
    override suspend fun write(value: ByteArray) {
        val raw=incoming.accept(value,System.nanoTime()/1_000_000) ?: return
        val request=Message.decode(raw)
        val cached=replies[request.requestId]
        if(cached!=null) {
            if(cached.first.contentEquals(raw)) {
                emit(GattIds.response,cached.second)
                if(request.opcode==Op.READ) inFlight?.let { emitBlock(request.requestId,it) }
            } else errorReply(request,0x86)
            return
        }
        try {
            if(request.opcode!=Op.HELLO && (nonce==0uL || request.nonce!=nonce)) throw DeviceError(0x85)
            val response=process(request)
            replies[request.requestId]=raw.copyOf() to response
            if(replies.size>32) replies.remove(replies.keys.first())
            // Deliberately emit Transfer before Response to exercise Android callback ordering.
            if(request.opcode==Op.READ) inFlight?.let { emitBlock(request.requestId,it) }
            emit(GattIds.response,response)
        } catch(e: DeviceError) { errorReply(request,e.code) }
    }
    private suspend fun errorReply(m: Message,code: Int) {
        emit(GattIds.response,Message(m.opcode,code,m.requestId,m.nonce,Writer().u16(0).u16(0).u32(snapshot.revision).build()))
    }
    private fun revision(r: Reader) { if(r.u32()!=snapshot.revision) throw DeviceError(0x84) }
    private fun applied() { snapshot=snapshot.copy(revision=(snapshot.revision+1) and 0xffffffffL) }
    private fun paramPayload(id: Int): ByteArray=Writer().u16(id).u16(0).u32(parameters[id] ?: throw DeviceError(0x80))
        .u32(parameters.getValue(id)).u32(snapshot.revision).u32(0).build()
    private fun task(m: Message): Long {
        val id=operation++
        tasks[id]=Writer().u32(id).u32(m.requestId).u8(m.opcode).u8(2).u8(0).u8(0).u32(snapshot.revision).u32(record.id).build()
        return id
    }
    private fun process(m: Message): Message {
        val r=Reader(m.payload)
        var status=0
        val payload=when(m.opcode) {
            Op.HELLO -> {
                if(r.u16()!=1 || r.u16()!=0 || m.nonce==0uL) throw DeviceError(0x81)
                nonce=m.nonce
                Writer().u64(boot).u32(0x6f).u32(snapshot.revision).u32(snapshot.time).build()
            }
            Op.STATUS -> snapshot.copy(recordState=record.state,recordId=record.id,frames=record.frames).encode()
            Op.SUBSCRIBE -> { r.u16();statusPeriod=r.u16().toLong().coerceAtLeast(100);r.u16();r.zero(2);m.payload }
            Op.GET_PARAM -> paramPayload(r.u16())
            Op.SET_PARAM -> {
                val id=r.u16();r.zero(2);val v=r.u32();revision(r)
                if(id !in parameters) throw DeviceError(0x80)
                val max=when(id){2->2;3->4;4->3;7->1;else->127}
                if(v !in 0..max.toLong()) throw DeviceError(0x81)
                parameters[id]=v;applied()
                snapshot=snapshot.copy(volume=parameters.getValue(1).toInt(),mode=parameters.getValue(2).toInt(),requestedMode=parameters.getValue(2).toInt(),
                    profile=parameters.getValue(3).toInt(),route=parameters.getValue(4).toInt(),effectsEnabled=parameters.getValue(7)==1L)
                paramPayload(id)
            }
            Op.GET_EFFECTS -> effectsPayload()
            Op.SET_EFFECTS -> {
                revision(r);val enabled=r.u8();val count=r.u8();val chain=List(3){r.u8()};r.zero(3)
                if(enabled !in 0..1 || count !in 0..3 || chain.take(count).any{it !in 0..2} || chain.take(count).distinct().size!=count || chain.drop(count).any{it!=255} || count==0 && enabled==1) throw DeviceError(0x81)
                applied();snapshot=snapshot.copy(effects=chain.take(count),effectsEnabled=enabled==1);parameters[7]=enabled.toLong();effectsPayload()
            }
            Op.START -> {
                if(record.state!=0) throw DeviceError(0x83)
                if(r.u8()!=1 || r.u8()!=0) throw DeviceError(0x81)
                r.zero(2);val max=r.u32();if(max>480000)throw DeviceError(0x81)
                maxFrames=if(max==0L)480000 else max
                record=record.copy(id=nextRecord++,state=2,frames=0,bytes=0,crc=0,flags=0,reason=0)
                started=System.nanoTime()/1_000_000;pcm=byteArrayOf();val id=task(m);record=record.copy(operation=id);status=1
                Writer().u32(id).u32(record.id).build()
            }
            Op.STOP -> {
                objectIdentity(r);if(record.state!=2)throw DeviceError(0x83)
                updateRecording();finishRecording(1);val id=task(m);record=record.copy(operation=id);status=1
                Writer().u32(id).u32(record.id).build()
            }
            Op.INFO -> {
                val id=r.u32();if(id!=0L&&id!=record.id)throw DeviceError(0x88)
                updateRecording();record.encode()
            }
            Op.CLEAR -> { objectIdentity(r);if(transfer!=0L||record.state in 1..3)throw DeviceError(0x82)
                val id=record.id;record=record.copy(id=0,state=0,frames=0,bytes=0,crc=0,flags=0,reason=0,operation=0);pcm=byteArrayOf();Writer().u32(id).build() }
            Op.OPERATION -> tasks[r.u32()] ?: throw DeviceError(0x88)
            Op.OPEN -> {
                objectIdentity(r);val offset=r.u32()
                if(!record.ready||transfer!=0L)throw DeviceError(0x83)
                if(offset>pcm.size||offset%4!=0L)throw DeviceError(0x89)
                transfer=operation++;cursor=offset;inFlight=null;previousAck=null
                Writer().u32(transfer).u32(record.bytes).u32(record.crc).u32(offset).u16(256).u8(1).u8(0).build()
            }
            Op.READ -> {
                transferIdentity(r);val offset=r.u32();val n=r.u16();r.zero(2)
                if(inFlight!=null)throw DeviceError(0x82)
                if(offset!=cursor||n !in 4..256||n%4!=0||offset+n>pcm.size)throw DeviceError(0x89)
                val bytes=pcm.copyOfRange(offset.toInt(),offset.toInt()+n)
                inFlight=PcmBlock(transfer,boot,record.id,offset,crc32(bytes),bytes)
                Writer().u32(transfer).u32(offset).u16(n).u16(0).build()
            }
            Op.ACK -> {
                transferIdentity(r);val next=r.u32();val crc=r.u32()
                if(previousAck!=(next to crc)) {
                    val b=inFlight ?: throw DeviceError(0x8d)
                    if(next!=b.offset+b.data.size||crc!=b.crc)throw DeviceError(0x8d)
                    cursor=next;previousAck=next to crc;inFlight=null
                }
                Writer().u32(transfer).u32(cursor).build()
            }
            Op.CLOSE -> { transferIdentity(r);val crc=r.u32();if(cursor!=pcm.size.toLong()||crc!=record.crc)throw DeviceError(0x8d)
                Writer().u32(transfer).build().also{transfer=0;inFlight=null} }
            Op.CANCEL -> { transferIdentity(r);Writer().u32(transfer).build().also{transfer=0;inFlight=null} }
            else -> throw DeviceError(0x80)
        }
        r.end()
        return Message(m.opcode,status,m.requestId,m.nonce,payload)
    }
    private fun effectsPayload()=Writer().u32(snapshot.revision).u8(if(snapshot.effectsEnabled)1 else 0).u8(snapshot.effects.size)
        .bytes(ByteArray(3){snapshot.effects.getOrElse(it){255}.toByte()}).bytes(ByteArray(3)).build()
    private fun objectIdentity(r: Reader) { if(r.u64()!=boot||r.u32()!=record.id)throw DeviceError(0x88) }
    private fun transferIdentity(r: Reader) { if(r.u32()!=transfer||transfer==0L)throw DeviceError(0x8d) }
    private fun updateRecording() {
        if(record.state==2) {
            val frames=((System.nanoTime()/1_000_000-started)*48).coerceAtMost(maxFrames)
            record=record.copy(frames=frames,bytes=frames*4)
            if(frames>=maxFrames)finishRecording(2)
        }
    }
    private fun finishRecording(reason: Int) {
        pcm=ByteArray(record.frames.toInt()*4)
        for(i in 0 until record.frames.toInt()) {
            val left=(sin(i*2*PI*440/48000)*12000).toInt()
            val right=(sin(i*2*PI*660/48000)*10000).toInt()
            pcm[i*4]=left.toByte();pcm[i*4+1]=(left shr 8).toByte();pcm[i*4+2]=right.toByte();pcm[i*4+3]=(right shr 8).toByte()
        }
        record=record.copy(state=4,flags=2,crc=crc32(pcm),reason=reason)
    }
    private suspend fun emitBlock(id: Long,b: PcmBlock) {
        emit(GattIds.transfer,Message(Op.DATA,0,id,nonce,Writer().u32(b.transfer).u64(b.boot).u32(b.recording).u32(b.offset)
            .u16(b.data.size).u16(0).u32(b.crc).bytes(b.data).build()))
    }
    private suspend fun emit(uuid: UUID,m: Message) {
        val currentToken=token++ and 65535
        for(part in fragment(m.encode(),currentToken)) _notifications.emit(Notification(uuid,part))
    }
    override fun close() { _connected.value=false;ticker?.cancel();ticker=null;transfer=0;inFlight=null;nonce=0uL }
}
