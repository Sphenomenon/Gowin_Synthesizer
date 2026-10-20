package cn.gowin.control.ble

import cn.gowin.control.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.net.Socket
import java.util.UUID

/** Opt-in radio test: Python only bridges GATT bytes; this is the APK's session/codec. */
class RealBoardSessionTest {
    @Test fun handshakeStatusAndReconnectOverRadio() = runBlocking {
        val port=System.getenv("GW25K_BLE_BRIDGE_PORT")?.toIntOrNull()
        assumeTrue("Run through GW25K tools/app_session_check.py for radio testing",port!=null)
        val scope=CoroutineScope(SupervisorJob()+Dispatchers.Default)
        var firstBoot=0uL
        try {
            repeat(2) { connection ->
                val bridge=RadioBridge(port!!)
                bridge.connect("GW25K-PROTO")
                val session=ProtocolSession(bridge,scope)
                try {
                    val cap=session.handshake()
                    assertTrue(cap.protocolTestOnly || cap.flags==0x68L)
                    if(connection==0)firstBoot=cap.boot else assertEquals(firstBoot,cap.boot)
                    var last=0L
                    repeat(3) {
                        val status=Snapshot.decode(session.request(Op.STATUS).message.payload)
                        assertEquals(if(cap.has(3))4L else 0L,status.valid);assertEquals(8L,status.flags)
                        assertTrue(status.id>last);last=status.id
                    }
                    try {session.request(0x7f);fail("unsupported accepted")}
                    catch(e:DeviceError){assertEquals(0x80,e.code)}
                    Snapshot.decode(session.request(Op.STATUS).message.payload)
                } finally {session.close();bridge.close()}
            }
        } finally { scope.cancel() }
    }
    private class RadioBridge(port:Int): BleTransport {
        private val socket=Socket("127.0.0.1",port)
        private val reader=socket.getInputStream().bufferedReader()
        private val writer=socket.getOutputStream().bufferedWriter()
        private val live=MutableStateFlow(false)
        override val connected=live.asStateFlow()
        private val incoming=MutableSharedFlow<Notification>(extraBufferCapacity=256)
        override val notifications=incoming.asSharedFlow()
        @Volatile private var result:CompletableDeferred<ByteArray>?=null
        private val thread=Thread {
            try {
                while(true) {
                    val line=reader.readLine() ?: break
                    val p=line.split(' ')
                    when(p[0]) {
                        "N" -> check(incoming.tryEmit(Notification(UUID.fromString(p[1]),hexBytes(p.getOrElse(2){""}))))
                        "R" -> result?.complete(hexBytes(p.getOrElse(1){""}))
                        "E" -> result?.completeExceptionally(IllegalStateException(line))
                    }
                }
            } catch(e:Exception) { result?.completeExceptionally(e) }
            finally {live.value=false;result?.completeExceptionally(IllegalStateException("bridge closed"))}
        }.apply {isDaemon=true;start()}
        private suspend fun rpc(value:String):ByteArray {
            val reply=CompletableDeferred<ByteArray>();result=reply
            writer.write(value+"\n");writer.flush()
            return withTimeout(25000){reply.await()}
        }
        override suspend fun connect(address:String) {rpc("CONNECT");live.value=true}
        override suspend fun read(uuid:UUID)=rpc("READ $uuid")
        override suspend fun subscribe(uuid:UUID) {rpc("SUBSCRIBE $uuid")}
        override suspend fun write(value:ByteArray) {rpc("WRITE ${value.hex()}")}
        override fun close() {live.value=false;socket.close()}
    }
}
