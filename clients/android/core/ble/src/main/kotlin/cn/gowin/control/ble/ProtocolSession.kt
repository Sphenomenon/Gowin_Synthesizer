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
    private data class Pending(val opcode: Int, val response: CompletableDeferred<Message>, val data: CompletableDeferred<Message>?)
    private val pending=ConcurrentHashMap<Long,Pending>()
    private val commandMutex=Mutex()
    private val assemblers=mutableMapOf<UUID,Reassembler>()
    private val _events=MutableSharedFlow<Message>(extraBufferCapacity=64)
    val events=_events.asSharedFlow()
    var nonce: ULong = 0uL; private set
    private var nextId=1L
    private var token=1
    private val receiveJob=scope.launch(start=CoroutineStart.UNDISPATCHED) {
        transport.notifications.collect { n ->
            try {
                val raw=assemblers.getOrPut(n.characteristic){Reassembler()}.accept(n.value,System.nanoTime()/1_000_000) ?: return@collect
                val m=Message.decode(raw)
                if(m.nonce!=nonce) return@collect
                if(m.requestId==0L) {
                    if(n.characteristic in setOf(GattIds.response,GattIds.status) && m.opcode in 0xe0..0xe3) _events.emit(m)
                } else {
                    val p=pending[m.requestId] ?: return@collect
                    if(n.characteristic==GattIds.response && m.opcode==p.opcode) p.response.complete(m)
                    if(n.characteristic==GattIds.transfer && m.opcode==Op.DATA) p.data?.complete(m)
                }
            } catch (_: ProtocolException) { /* Drop corrupt frames. The same request is retried without re-execution. */ }
        }
    }
    private val connectionJob=scope.launch {
        transport.connected.collect { live -> if(!live) pending.values.forEach {
            it.response.completeExceptionally(IOException("蓝牙连接已断开")); it.data?.completeExceptionally(IOException("蓝牙连接已断开"))
        } }
    }
    suspend fun handshake(): Capability {
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
        return cap
    }
    suspend fun request(opcode: Int,payload: ByteArray=byteArrayOf(),data: Boolean=false): Reply = commandMutex.withLock {
        checkWire(nonce!=0uL,"会话未建立")
        checkWire(nextId<0xffffffffL,"请求编号耗尽，请重新连接")
        val id=nextId++
        val request=Message(opcode,0,id,nonce,payload)
        val p=Pending(opcode,CompletableDeferred(),if(data) CompletableDeferred() else null)
        pending[id]=p
        try {
            repeat(4) { attempt ->
                checkWire(transport.connected.value,"蓝牙连接已断开")
                val fragments=fragment(request.encode(),token)
                token=(token+1) and 0xffff
                for(part in fragments) transport.write(part)
                try {
                    val response=withTimeout(3000){ p.response.await() }.checked()
                    val body=if(data) withTimeout(3000){p.data!!.await()}.checked() else null
                    return@withLock Reply(response,body)
                } catch(e: TimeoutCancellationException) { if(attempt==3) throw IOException("业务响应超时，请重新连接并恢复",e) }
            }
            error("unreachable")
        } finally { pending.remove(id) }
    }
    fun close() { receiveJob.cancel(); connectionJob.cancel(); pending.values.forEach { it.response.cancel(); it.data?.cancel() }; pending.clear() }
}
