package cn.gowin.control.ble

import cn.gowin.control.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.io.IOException
import java.security.SecureRandom
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

data class Reply(val message: Message, val data: Message? = null)
class ProtocolSession(val transport: BleTransport, scope: CoroutineScope) {
    private data class Pending(val opcode: Int, val payload:ByteArray, val response: CompletableDeferred<Message>, val data: CompletableDeferred<Message>?)
    private val pending=ConcurrentHashMap<Long,Pending>()
    private val commandMutex=Mutex()
    private val assemblers=mutableMapOf<UUID,Reassembler>()
    private val _events=MutableSharedFlow<Message>(extraBufferCapacity=64)
    val events=_events.asSharedFlow()
    var nonce: ULong = 0uL; private set
    var recordingFormats: RecordingFormats = RecordingFormats.LEGACY; private set
    private var recordingBoot=0uL
    private var nextId=1L
    private data class DirectObject(val boot:ULong,val recording:Long,val opened:TransferOpen)
    private var directObject:DirectObject?=null
    private var secondOpenAvailable=true
    private var secondTransfer=false
    private var losslessOpenAvailable=true
    private var losslessTransfer=false
    private var extendedOpenAvailable=true
    private var extendedTransfer=false
    private var longOpenAvailable=true
    private var longTransfer=false
    private var directOpenAvailable=true
    private var bulkOpenAvailable=true
    private var bulkValueLimit:Int?=null
    private var compactOpenAvailable=true
    private var compactTransfer=false
    private var wideOpenAvailable=true
    private var ackReadAvailable=true
    private var token=1
    private val receiveJob=scope.launch(start=CoroutineStart.UNDISPATCHED) {
        transport.notifications.collect { n ->
            try {
                val raw=assemblers.getOrPut(n.characteristic){Reassembler(allowCompact=n.characteristic==GattIds.transfer && compactTransfer,bulkValueLimit=if(n.characteristic==GattIds.transfer)bulkValueLimit else null,longData=n.characteristic==GattIds.transfer && longTransfer,extendedData=n.characteristic==GattIds.transfer && extendedTransfer)}.accept(n.value,System.nanoTime()/1_000_000) ?: return@collect
                val m=Message.decode(raw,if(n.characteristic==GattIds.transfer && extendedTransfer)8160 else if(n.characteristic==GattIds.transfer && longTransfer)1020 else 512)
                if(m.nonce!=nonce) return@collect
                if(m.status==0 && m.opcode in setOf(Op.STATUS,Op.STATUS_EVENT,0xe2,0xe3) &&
                    n.characteristic in setOf(GattIds.response,GattIds.status)) {
                    if(Snapshot.decode(m.payload).flags and 8L==0L) {
                        recordingFormats=RecordingFormats.LEGACY;recordingBoot=0uL
                    }
                }
                if(m.requestId==0L) {
                    if(n.characteristic in setOf(GattIds.response,GattIds.status) && m.opcode in 0xe0..0xe3) _events.emit(m)
                } else {
                    val p=pending[m.requestId] ?: return@collect
                    if(n.characteristic==GattIds.response && m.opcode==p.opcode) {
                        if(m.status==0 && m.opcode in setOf(Op.OPEN,Op.OPEN_WIDE,Op.OPEN_COMPACT,Op.OPEN_BULK,Op.OPEN_DIRECT,Op.OPEN_LONG,Op.OPEN_EXTENDED,Op.OPEN_LOSSLESS,Op.OPEN_SECOND)) {
                            // Profile and assembler change on the receive coroutine,
                            // before publishing OPEN success to the caller.
                            val opened=TransferOpen.decode(m)
                            bulkValueLimit=if(m.opcode in setOf(Op.OPEN_BULK,Op.OPEN_DIRECT,Op.OPEN_LONG,Op.OPEN_EXTENDED,Op.OPEN_LOSSLESS,Op.OPEN_SECOND))opened.valueLimit else null
                            directObject=if(m.opcode in setOf(Op.OPEN_DIRECT,Op.OPEN_LONG,Op.OPEN_EXTENDED,Op.OPEN_LOSSLESS,Op.OPEN_SECOND)) {
                                checkWire(p.payload.size==16,"下载打开请求长度错误")
                                val request=Reader(p.payload)
                                val boot=request.u64();val recording=request.u32();val offset=request.u32();request.end()
                                checkWire(boot!=0uL && recording!=0L && opened.offset==offset && offset<=opened.bytes && offset%4==0L && opened.bytes%4==0L,"下载打开元数据与请求不匹配")
                                DirectObject(boot,recording,opened)
                            } else null
                            secondTransfer=m.opcode==Op.OPEN_SECOND
                            losslessTransfer=m.opcode in setOf(Op.OPEN_LOSSLESS,Op.OPEN_SECOND)
                            extendedTransfer=m.opcode in setOf(Op.OPEN_EXTENDED,Op.OPEN_LOSSLESS,Op.OPEN_SECOND)
                            longTransfer=m.opcode==Op.OPEN_LONG
                            compactTransfer=m.opcode==Op.OPEN_COMPACT
                            assemblers.remove(GattIds.transfer)
                        }
                        p.response.complete(m)
                    }
                    if(n.characteristic==GattIds.transfer && m.opcode==Op.DATA) {
                        var validated=m
                        val direct=directObject
                        if(direct!=null && p.data!=null && p.opcode in setOf(Op.READ,Op.ACK_READ,Op.READ_LOSSLESS,Op.ACK_READ_LOSSLESS,Op.READ_SECOND,Op.ACK_READ_SECOND)) {
                            checkWire(m.status==0 && p.payload.size==(if(p.opcode in setOf(Op.READ,Op.READ_LOSSLESS,Op.READ_SECOND))12 else 16),"读取数据状态错误")
                            val coded=p.opcode in setOf(Op.READ_LOSSLESS,Op.ACK_READ_LOSSLESS,Op.READ_SECOND,Op.ACK_READ_SECOND)
                            val second=p.opcode in setOf(Op.READ_SECOND,Op.ACK_READ_SECOND)
                            checkWire(!second || secondTransfer,"未协商二阶无损下载")
                            checkWire(!coded || losslessTransfer,"未协商无损下载")
                            val block=PcmBlock.decode(m.payload,direct.opened.maxChunk,allowLossless=coded && losslessTransfer,allowSecond=second && secondTransfer)
                            val request=Reader(p.payload)
                            val tid=request.u32();val offset=request.u32();val length=request.u16();request.zero(2)
                            checkWire(block.transfer==tid && tid==direct.opened.transfer && block.offset==offset && block.data.size==length &&
                                block.boot==direct.boot && block.recording==direct.recording && offset+length<=direct.opened.bytes,"读取数据与请求不匹配")
                            if(coded) validated=m.copy(payload=Writer().u32(block.transfer).u64(block.boot).u32(block.recording)
                                .u32(block.offset).u16(block.data.size).u16(0).u32(block.crc).bytes(block.data).build())
                            // DATA is the explicit positive receipt only after OPEN_DIRECT.
                            // Logical and PCM CRCs, identity and range all passed above.
                            p.response.complete(Message(p.opcode,0,m.requestId,m.nonce,
                                Writer().u32(tid).u32(offset).u16(length).u16(0).build()))
                        }
                        p.data?.complete(validated)
                    }
                }
            } catch (_: ProtocolException) { /* Drop corrupt frames. The same request is retried without re-execution. */ }
        }
    }
    private val connectionJob=scope.launch {
        transport.connected.collect { live -> if(!live) {
            recordingFormats=RecordingFormats.LEGACY;recordingBoot=0uL
            pending.values.forEach {
                it.response.completeExceptionally(IOException("蓝牙连接已断开")); it.data?.completeExceptionally(IOException("蓝牙连接已断开"))
            }
        } }
    }
    suspend fun handshake(): Capability {
        recordingFormats=RecordingFormats.LEGACY
        recordingBoot=0uL
        val cap=Capability.decode(transport.read(GattIds.capability))
        transport.subscribe(GattIds.response)
        if(cap.has(2)) transport.subscribe(GattIds.status)
        if(cap.has(5)) transport.subscribe(GattIds.transfer)
        do { nonce=SecureRandom().nextLong().toULong() } while(nonce==0uL)
        val hello=request(Op.HELLO,Writer().u16(1).u16(0).build()).message
        checkWire(hello.payload.size==20,"HELLO 响应长度错误")
        val r=Reader(hello.payload)
        checkWire(r.u64()==cap.boot && r.u32()==cap.flags,"设备身份在握手时改变")
        r.u32();r.u32();r.end()
        recordingBoot=cap.boot
        return cap
    }
    /** Only explicit UNSUPPORTED permits legacy fallback; corruption/timeouts fail the connection. */
    suspend fun negotiateRecordingFormats(): RecordingFormats {
        checkWire(recordingBoot!=0uL && transport.connected.value, "录音格式协商需要有效会话")
        val boot=recordingBoot;val sessionNonce=nonce
        val grant=try {
            RecordingFormats.decodeResponse(request(Op.RECORDING_FORMATS,RecordingFormats.requestPayload()).message,boot)
        } catch(e: DeviceError) {
            if(e.code!=0x80)throw e
            RecordingFormats.LEGACY
        }
        checkWire(transport.connected.value && recordingBoot==boot && nonce==sessionNonce, "录音格式协商会话已失效")
        recordingFormats=grant
        return grant
    }
    suspend fun request(opcode: Int,payload: ByteArray=byteArrayOf(),data: Boolean=false): Reply = commandMutex.withLock {
        checkWire(nonce!=0uL,"会话未建立")
        checkWire(nextId<0xffffffffL,"请求编号耗尽，请重新连接")
        val id=nextId++
        val request=Message(opcode,0,id,nonce,payload)
        val p=Pending(opcode,payload.copyOf(),CompletableDeferred(),if(data) CompletableDeferred() else null)
        pending[id]=p
        try {
            repeat(4) { attempt ->
                checkWire(transport.connected.value,"蓝牙连接已断开")
                val fragments=fragment(request.encode(),token)
                token=(token+1) and 0xffff
                for(part in fragments) transport.write(part)
                try {
                    val response=try { withTimeout(3000){ p.response.await() }.checked() }
                    catch(e:DeviceError) {
                        if(e.code in setOf(0x85,0x8c)) { recordingFormats=RecordingFormats.LEGACY;recordingBoot=0uL }
                        throw e
                    }
                    val body=if(data) withTimeout(3000){p.data!!.await()}.checked() else null
                    return@withLock Reply(response,body)
                } catch(e: TimeoutCancellationException) {
                    // Retry the identical logical request first; persistent
                    // transport/cache incompatibility falls back to ATT requests.
                    if(attempt==1) transport.useAcknowledgedWrites()
                    if(attempt==3) throw IOException("业务响应超时，请重新连接并恢复",e)
                }
            }
            error("unreachable")
        } finally { pending.remove(id) }
    }
    /** OPEN_DIRECT, OPEN_BULK, OPEN_COMPACT and OPEN_WIDE are opt-in per transfer. Only explicit UNSUPPORTED permits
     * falling back; a lost response retries the same request ID. */
    suspend fun openTransfer(boot:ULong,recording:Long,offset:Long):Reply {
        val payload=Writer().u64(boot).u32(recording).u32(offset).build()
        suspend fun opened(op:Int):Reply {
            val result=request(op,payload)
            return result
        }
        if(secondOpenAvailable) {
            try { return opened(Op.OPEN_SECOND) }
            catch(e:DeviceError) {
                if(e.code!=0x80)throw e
                secondOpenAvailable=false
            }
        }
        if(losslessOpenAvailable) {
            try { return opened(Op.OPEN_LOSSLESS) }
            catch(e:DeviceError) {
                if(e.code!=0x80)throw e
                losslessOpenAvailable=false
            }
        }
        if(extendedOpenAvailable) {
            try { return opened(Op.OPEN_EXTENDED) }
            catch(e:DeviceError) {
                if(e.code!=0x80)throw e
                extendedOpenAvailable=false
            }
        }
        if(longOpenAvailable) {
            try { return opened(Op.OPEN_LONG) }
            catch(e:DeviceError) {
                if(e.code!=0x80)throw e
                longOpenAvailable=false
            }
        }
        if(directOpenAvailable) {
            try { return opened(Op.OPEN_DIRECT) }
            catch(e:DeviceError) {
                if(e.code!=0x80)throw e
                directOpenAvailable=false
            }
        }
        if(bulkOpenAvailable) {
            try { return opened(Op.OPEN_BULK) }
            catch(e:DeviceError) {
                if(e.code!=0x80)throw e
                bulkOpenAvailable=false
            }
        }
        if(compactOpenAvailable) {
            try { return opened(Op.OPEN_COMPACT) }
            catch(e:DeviceError) {
                if(e.code!=0x80)throw e
                compactOpenAvailable=false
            }
        }
        if(wideOpenAvailable) {
            try { return opened(Op.OPEN_WIDE) }
            catch(e:DeviceError) {
                if(e.code!=0x80)throw e
                wideOpenAvailable=false
            }
        }
        return opened(Op.OPEN)
    }
    /** Call only after the preceding block and checkpoint are durable. An old
     * firmware's UNSUPPORTED response guarantees no ACK was committed. */
    suspend fun readBlock(transfer:Long,offset:Long,length:Int,previousCrc:Long?=null):Reply {
        if(secondTransfer) {
            val payload=Writer().u32(transfer).u32(offset).u16(length).u16(0)
            if(previousCrc!=null)payload.u32(previousCrc)
            return request(if(previousCrc!=null)Op.ACK_READ_SECOND else Op.READ_SECOND,payload.build(),data=true)
        }
        if(losslessTransfer) {
            val payload=Writer().u32(transfer).u32(offset).u16(length).u16(0)
            if(previousCrc!=null)payload.u32(previousCrc)
            return request(if(previousCrc!=null)Op.ACK_READ_LOSSLESS else Op.READ_LOSSLESS,payload.build(),data=true)
        }
        if(previousCrc!=null && ackReadAvailable) {
            try {
                return request(Op.ACK_READ,Writer().u32(transfer).u32(offset).u16(length).u16(0).u32(previousCrc).build(),data=true)
            } catch(e:DeviceError) {
                if(e.code!=0x80)throw e
                ackReadAvailable=false
            }
        }
        if(previousCrc!=null) acknowledgeBlock(transfer,offset,previousCrc)
        return request(Op.READ,Writer().u32(transfer).u32(offset).u16(length).u16(0).build(),data=true)
    }
    suspend fun acknowledgeBlock(transfer:Long,offset:Long,crc:Long) {
        val payload=request(Op.ACK,Writer().u32(transfer).u32(offset).u32(crc).build()).message.payload
        val r=Reader(payload)
        checkWire(payload.size==8 && r.u32()==transfer && r.u32()==offset,"ACK 响应不匹配")
    }
    fun close() { recordingFormats=RecordingFormats.LEGACY;recordingBoot=0uL;receiveJob.cancel(); connectionJob.cancel(); pending.values.forEach { it.response.cancel(); it.data?.cancel() }; pending.clear() }
}
