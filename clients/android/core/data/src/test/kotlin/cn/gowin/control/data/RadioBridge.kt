package cn.gowin.control.data
import cn.gowin.control.ble.*
import cn.gowin.control.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import java.net.Socket
import java.util.UUID
class RadioBridge(port:Int): BleTransport {
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
                        "N" -> {
                            val uuid=UUID.fromString(p[1]);val value=hexBytes(p.getOrElse(2){""})
                            // Test-only: lose the complete logical Response after
                            // the controller has already executed the command.
                            if(uuid==GattIds.response && dropNextResponse) {
                                if(value[4].toInt() and 2 != 0)dropNextResponse=false
                            } else if(uuid==GattIds.transfer && dropNextTransfer) {
                                val last=if((value[0].toInt() and 255)==0xb1)(value[4].toInt() and 2)!=0 else (value[3].toInt() and 128)!=0
                                if(last){dropNextTransfer=false;droppedTransfers++}
                            } else check(incoming.tryEmit(Notification(uuid,value)))
                        }
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
            return withTimeout(if(value=="CONNECT")60000 else 25000){reply.await()}
        }
        override suspend fun connect(address:String) {rpc("CONNECT");live.value=true}
        override suspend fun read(uuid:UUID)=rpc("READ $uuid")
        override suspend fun subscribe(uuid:UUID) {rpc("SUBSCRIBE $uuid")}
        @Volatile var dropNextResponse=false
        @Volatile var dropNextTransfer=false
        @Volatile var droppedTransfers=0
        var dropNextWrite=false
        override suspend fun write(value:ByteArray) {
            if(dropNextWrite) {dropNextWrite=false;return}
            rpc("WRITE ${value.hex()}")
        }
        override fun close() {live.value=false;socket.close()}
    }
