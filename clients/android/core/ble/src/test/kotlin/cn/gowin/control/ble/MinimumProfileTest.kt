package cn.gowin.control.ble

import cn.gowin.control.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

/** Payloads captured from the 25K radio, not the full workstation simulator. */
@OptIn(ExperimentalCoroutinesApi::class)
class MinimumProfileTest {
    @Test fun minimalBoardAcceptsOnlyResponseSubscriptionAndStatus() = runTest {
        val subscriptions=mutableListOf<UUID>()
        val notifications=MutableSharedFlow<Notification>(extraBufferCapacity=32)
        val connected=MutableStateFlow(true)
        val cap=hexBytes("01140002a8d59dfad4ea4e7d0000000000000100")
        val incoming=Reassembler()
        val transport=object: BleTransport {
            override val notifications=notifications.asSharedFlow()
            override val connected=connected.asStateFlow()
            override suspend fun connect(address:String) {}
            override suspend fun read(uuid:UUID):ByteArray { assertEquals(GattIds.capability,uuid);return cap }
            override suspend fun subscribe(uuid:UUID) { subscriptions+=uuid }
            override suspend fun write(value:ByteArray) {
                val raw=incoming.accept(value,0) ?: return
                val m=Message.decode(raw)
                val payload=when(m.opcode) {
                    Op.HELLO -> hexBytes("a8d59dfad4ea4e7d0000000001000000f6080000")
                    Op.STATUS -> hexBytes("020000008a0b00000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000")
                    else -> error("unsupported command during minimal initialization")
                }
                fragment(Message(m.opcode,0,m.requestId,m.nonce,payload).encode(),1).forEach {
                    notifications.emit(Notification(GattIds.response,it))
                }
            }
            override fun close() { connected.value=false }
        }
        val session=ProtocolSession(transport,backgroundScope)
        val capability=session.handshake()
        assertTrue(capability.protocolTestOnly)
        assertEquals(listOf(GattIds.response),subscriptions)
        val status=Snapshot.decode(session.request(Op.STATUS).message.payload)
        assertEquals(0L,status.valid);assertEquals(2L,status.id);assertEquals(8L,status.flags)
        session.close()
    }

    @Test fun missingFastWriteResponsesFallBackWithoutChangingRequestIdentity() = runTest {
        val notifications=MutableSharedFlow<Notification>(extraBufferCapacity=32)
        val requests=mutableListOf<ByteArray>()
        val incoming=Reassembler()
        var acknowledged=false
        var fallbacks=0
        val cap=hexBytes("01140002a8d59dfad4ea4e7d0000000000000100")
        val transport=object:BleTransport {
            override val notifications=notifications.asSharedFlow()
            override val connected=MutableStateFlow(true).asStateFlow()
            override suspend fun connect(address:String) {}
            override suspend fun read(uuid:UUID)=cap
            override suspend fun subscribe(uuid:UUID) {}
            override suspend fun write(value:ByteArray) {
                val raw=incoming.accept(value,testScheduler.currentTime) ?: return
                requests+=raw
                if(!acknowledged)return
                val m=Message.decode(raw)
                val payload=hexBytes("a8d59dfad4ea4e7d0000000001000000f6080000")
                fragment(Message(m.opcode,0,m.requestId,m.nonce,payload).encode(),1).forEach {
                    notifications.emit(Notification(GattIds.response,it))
                }
            }
            override fun useAcknowledgedWrites() { acknowledged=true;fallbacks++ }
            override fun close() {}
        }
        val session=ProtocolSession(transport,backgroundScope)
        assertTrue(session.handshake().protocolTestOnly)
        assertEquals(1,fallbacks);assertEquals(3,requests.size)
        requests.forEach {assertArrayEquals(requests.first(),it)}
        assertEquals(6000,testScheduler.currentTime)
        session.close()
    }
}
