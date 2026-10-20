package cn.gowin.control.ble

import cn.gowin.control.protocol.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class AckReadTest {
    private class Radio(private val reject:Int?=null,private var drop:Int=0):BleTransport {
        private val incoming=Reassembler()
        private val stream=MutableSharedFlow<Notification>(extraBufferCapacity=64)
        override val notifications=stream.asSharedFlow()
        override val connected=MutableStateFlow(true).asStateFlow()
        val requests=mutableListOf<Message>()
        override suspend fun connect(address:String) {}
        override suspend fun subscribe(uuid:UUID) {}
        override suspend fun read(uuid:UUID)=hexBytes("01140002a8d59dfad4ea4e7d6800000000010101")
        override suspend fun write(value:ByteArray) {
            val raw=incoming.accept(value,0) ?: return
            val m=Message.decode(raw);requests+=m
            if(m.opcode==Op.ACK_READ && drop-->0)return
            val error=if(m.opcode==Op.ACK_READ)reject else null
            val payload=when {
                error!=null -> Writer().u16(0).u16(0).u32(1).build()
                m.opcode==Op.HELLO -> hexBytes("a8d59dfad4ea4e7d680000000100000000000000")
                m.opcode==Op.ACK -> m.payload.copyOfRange(0,8)
                else -> m.payload.copyOfRange(0,12)
            }
            fragment(Message(m.opcode,error?:0,m.requestId,m.nonce,payload).encode(),1).forEach {
                stream.emit(Notification(GattIds.response,it))
            }
            if(error==null && m.opcode in listOf(Op.READ,Op.ACK_READ)) {
                fragment(Message(Op.DATA,0,m.requestId,m.nonce,byteArrayOf(1,2,3,4)).encode(),2).forEach {
                    stream.emit(Notification(GattIds.transfer,it))
                }
            }
        }
        override fun close() {}
    }
    @Test fun combinedTimeoutRetriesIdenticalIdAndPayload()=runTest {
        val radio=Radio(drop=1);val session=ProtocolSession(radio,backgroundScope);session.handshake()
        val reply=session.readBlock(7,256,256,0xaabbccddL)
        assertEquals(Op.ACK_READ,reply.message.opcode);assertNotNull(reply.data)
        val sent=radio.requests.filter{it.opcode==Op.ACK_READ};assertEquals(2,sent.size)
        assertArrayEquals(sent[0].encode(),sent[1].encode())
        assertArrayEquals(Writer().u32(7).u32(256).u16(256).u16(0).u32(0xaabbccddL).build(),sent[0].payload)
        assertEquals(3000,testScheduler.currentTime);session.close()
    }
    @Test fun oldFirmwareFallsBackOncePerConnection()=runTest {
        val radio=Radio(reject=0x80);val session=ProtocolSession(radio,backgroundScope);session.handshake()
        assertEquals(Op.READ,session.readBlock(7,256,256,23).message.opcode)
        assertEquals(Op.READ,session.readBlock(7,512,128,24).message.opcode)
        assertEquals(listOf(Op.HELLO,Op.ACK_READ,Op.ACK,Op.READ,Op.ACK,Op.READ),radio.requests.map{it.opcode})
        assertArrayEquals(Writer().u32(7).u32(256).u32(23).build(),radio.requests[2].payload)
        assertArrayEquals(Writer().u32(7).u32(512).u32(24).build(),radio.requests[4].payload)
        assertEquals(0,testScheduler.currentTime);session.close()
    }
    @Test fun crcConflictNeverFallsBackAndFirstReadNeedsNoAck()=runTest {
        val radio=Radio(reject=0x8d);val session=ProtocolSession(radio,backgroundScope);session.handshake()
        assertEquals(Op.READ,session.readBlock(7,0,256).message.opcode)
        try {session.readBlock(7,256,256,23);fail("Expected conflict")}catch(e:DeviceError){assertEquals(0x8d,e.code)}
        assertEquals(listOf(Op.HELLO,Op.READ,Op.ACK_READ),radio.requests.map{it.opcode})
        session.close()
    }
}
