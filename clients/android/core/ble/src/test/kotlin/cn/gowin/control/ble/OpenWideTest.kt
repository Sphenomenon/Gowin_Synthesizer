package cn.gowin.control.ble

import cn.gowin.control.protocol.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class OpenWideTest {
    private class Radio(private val reject:Int?=null,private var drop:Int=0):BleTransport {
        private val assembler=Reassembler()
        private val incoming=MutableSharedFlow<Notification>(extraBufferCapacity=64)
        override val notifications=incoming.asSharedFlow()
        override val connected=MutableStateFlow(true).asStateFlow()
        val requests=mutableListOf<Message>()
        override suspend fun connect(address:String) {}
        override suspend fun subscribe(uuid:UUID) {}
        override suspend fun read(uuid:UUID)=hexBytes("01140002a8d59dfad4ea4e7d6800000000010101")
        override suspend fun write(value:ByteArray) {
            val raw=assembler.accept(value,0)?:return
            val m=Message.decode(raw);requests+=m
            if(m.opcode==Op.OPEN_WIDE && drop-->0)return
            val error=if(m.opcode in setOf(Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED,Op.OPEN_LONG,Op.OPEN_DIRECT,Op.OPEN_BULK,Op.OPEN_COMPACT))0x80 else if(m.opcode==Op.OPEN_WIDE)reject else null
            val payload=when {
                error!=null -> Writer().u16(0).u16(0).u32(1).build()
                m.opcode==Op.HELLO -> hexBytes("a8d59dfad4ea4e7d680000000100000000000000")
                else -> Writer().u32(7).u32(192000).u32(23).u32(460).u16(if(m.opcode==Op.OPEN_WIDE)460 else 256).u8(1).u8(0).build()
            }
            fragment(Message(m.opcode,error?:0,m.requestId,m.nonce,payload).encode(),1).forEach {
                incoming.emit(Notification(GattIds.response,it))
            }
        }
        override fun close() {}
    }
    @Test fun timeoutRetriesSameOpenWithoutAllocatingNewId()=runTest {
        val radio=Radio(drop=1);val s=ProtocolSession(radio,backgroundScope);s.handshake()
        assertEquals(Op.OPEN_WIDE,s.openTransfer(1uL,2,460).message.opcode)
        val opens=radio.requests.filter{it.opcode==Op.OPEN_WIDE};assertEquals(2,opens.size)
        assertArrayEquals(opens[0].encode(),opens[1].encode())
        assertArrayEquals(Writer().u64(1uL).u32(2).u32(460).build(),opens[0].payload)
        assertEquals(3000,testScheduler.currentTime);s.close()
    }
    @Test fun unsupportedDisablesProbeForConnectionOnly()=runTest {
        val radio=Radio(reject=0x80);val s=ProtocolSession(radio,backgroundScope);s.handshake()
        assertEquals(Op.OPEN,s.openTransfer(1uL,2,0).message.opcode)
        assertEquals(Op.OPEN,s.openTransfer(1uL,2,256).message.opcode)
        assertEquals(listOf(Op.HELLO,Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED,Op.OPEN_LONG,Op.OPEN_DIRECT,Op.OPEN_BULK,Op.OPEN_COMPACT,Op.OPEN_WIDE,Op.OPEN,Op.OPEN),radio.requests.map{it.opcode});s.close()
        val next=Radio();val another=ProtocolSession(next,backgroundScope);another.handshake()
        assertEquals(Op.OPEN_WIDE,another.openTransfer(1uL,2,0).message.opcode);another.close()
    }
    @Test fun busyNeverFallsBackToAnotherOpen()=runTest {
        val radio=Radio(reject=0x82);val s=ProtocolSession(radio,backgroundScope);s.handshake()
        try {s.openTransfer(1uL,2,0);fail("Expected BUSY")}catch(e:DeviceError){assertEquals(0x82,e.code)}
        assertEquals(listOf(Op.HELLO,Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED,Op.OPEN_LONG,Op.OPEN_DIRECT,Op.OPEN_BULK,Op.OPEN_COMPACT,Op.OPEN_WIDE),radio.requests.map{it.opcode});s.close()
    }
    @Test fun largeBlockRequiresExplicitBoundAndKeepsLogicalAndPcmCrc() {
        val pcm=ByteArray(460){(it*13).toByte()}
        val payload=Writer().u32(7).u64(1uL).u32(2).u32(460).u16(460).u16(0).u32(crc32(pcm)).bytes(pcm).build()
        val raw=Message(Op.DATA,0,9,1uL,payload).encode();assertEquals(508,raw.size)
        val fragments=fragment(raw,1);assertEquals(37,fragments.size)
        val assembler=Reassembler();var received:ByteArray?=null
        fragments.forEachIndexed{i,f->received=assembler.accept(f,i.toLong())}
        val decoded=Message.decode(received!!)
        assertThrows(ProtocolException::class.java){PcmBlock.decode(decoded.payload)}
        assertArrayEquals(pcm,PcmBlock.decode(decoded.payload,460).data)
        assertThrows(ProtocolException::class.java){PcmBlock.decode(decoded.payload,456)}
        val corrupt=decoded.payload.copyOf().apply{this[lastIndex]=(this[lastIndex].toInt() xor 1).toByte()}
        assertThrows(ProtocolException::class.java){PcmBlock.decode(corrupt,460)}
        assertThrows(ProtocolException::class.java){PcmBlock.decode(decoded.payload,8116)}
    }
}
