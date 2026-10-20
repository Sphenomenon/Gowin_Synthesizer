package cn.gowin.control.ble

import cn.gowin.control.protocol.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class CompactTransferTest {
    private fun compact(raw:ByteArray,token:Int=7)=raw.toList().chunked(16).mapIndexed { i, data ->
        Writer().u8(0xb2).u16(token).u8(i or (if(i==0)64 else 0) or
            (if((i+1)*16>=raw.size)128 else 0)).bytes(data.toByteArray()).build()
    }
    @Test fun allSizesIncludingFullLastFragmentAndTokenWrap() {
        for(size in 1..512) {
            val raw=ByteArray(size){(it*19).toByte()}
            val parts=compact(raw,if(size%2==0)0 else 65535)
            val assembler=Reassembler(allowCompact=true)
            var result:ByteArray?=null
            parts.forEachIndexed { i, part ->
                result=assembler.accept(part,i.toLong())
                if(i<parts.lastIndex)assertNull(assembler.accept(part,i.toLong()))
            }
            assertArrayEquals(raw,result)
            assertThrows(ProtocolException::class.java){Reassembler().accept(parts.first(),0)}
        }
        assertEquals(32,compact(ByteArray(508)).size)
    }
    @Test fun lostConflictingMixedAndTimedOutFragmentsRequireNewFirst() {
        val raw=ByteArray(508){it.toByte()};val p=compact(raw)
        val assembler=Reassembler(allowCompact=true)
        assembler.accept(p[0],0)
        assertThrows(ProtocolException::class.java){assembler.accept(p[2],1)}
        assembler.accept(p[0],2)
        assertThrows(ProtocolException::class.java){assembler.accept(p[0].copyOf().apply{this[4]=99},3)}
        assembler.accept(p[0],4)
        assertThrows(ProtocolException::class.java){assembler.accept(fragment(raw,7)[1],5)}
        assembler.accept(p[0],6)
        assertThrows(ProtocolException::class.java){assembler.accept(p[1],2007)}
        var result:ByteArray?=null
        p.forEachIndexed{i,v->result=assembler.accept(v,2010+i.toLong())}
        assertArrayEquals(raw,result)
    }
    private inner class Radio(private val reject:Int?=null,private var dropOpen:Boolean=false,
                              private var loseData:Boolean=false):BleTransport {
        private val assembly=Reassembler()
        private val incoming=MutableSharedFlow<Notification>(extraBufferCapacity=64)
        override val notifications=incoming.asSharedFlow()
        override val connected=MutableStateFlow(true).asStateFlow()
        val requests=mutableListOf<Message>()
        val pcm=ByteArray(460){(it*13).toByte()}
        override suspend fun connect(address:String) {}
        override suspend fun subscribe(uuid:UUID) {}
        override suspend fun read(uuid:UUID)=hexBytes("01140002a8d59dfad4ea4e7d6800000000010101")
        override suspend fun write(value:ByteArray) {
            val m=Message.decode(assembly.accept(value,0)?:return);requests+=m
            if(m.opcode==Op.OPEN_COMPACT && dropOpen){dropOpen=false;return}
            val error=if(m.opcode in setOf(Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED,Op.OPEN_LONG,Op.OPEN_DIRECT,Op.OPEN_BULK))0x80 else if(m.opcode==Op.OPEN_COMPACT)reject else null
            val payload=when {
                error!=null -> Writer().u16(0).u16(0).u32(1).build()
                m.opcode==Op.HELLO -> hexBytes("a8d59dfad4ea4e7d680000000100000000000000")
                m.opcode==Op.READ -> Writer().u32(7).u32(0).u16(460).u16(0).build()
                else -> Writer().u32(7).u32(192000).u32(23).u32(0).u16(460).u8(1).u8(0).build()
            }
            fragment(Message(m.opcode,error?:0,m.requestId,m.nonce,payload).encode(),1).forEach {
                incoming.emit(Notification(GattIds.response,it))
            }
            if(m.opcode==Op.READ) {
                val block=Writer().u32(7).u64(1uL).u32(2).u32(0).u16(460).u16(0).u32(crc32(pcm)).bytes(pcm).build()
                val parts=compact(Message(Op.DATA,0,m.requestId,m.nonce,block).encode())
                parts.forEachIndexed { i,part ->
                    if(!loseData || i!=1)incoming.emit(Notification(GattIds.transfer,part))
                }
                loseData=false
            }
        }
        override fun close() {}
    }
    @Test fun successfulOptInReceivesCompactDataAndLostFragmentRetriesIdenticalRequest()=runTest {
        val radio=Radio(dropOpen=true,loseData=true);val s=ProtocolSession(radio,backgroundScope);s.handshake()
        assertEquals(Op.OPEN_COMPACT,s.openTransfer(1uL,2,0).message.opcode)
        val reply=s.readBlock(7,0,460)
        assertArrayEquals(radio.pcm,PcmBlock.decode(reply.data!!.payload,460).data)
        for(op in listOf(Op.OPEN_COMPACT,Op.READ)) {
            val repeated=radio.requests.filter{it.opcode==op}
            assertEquals(2,repeated.size);assertArrayEquals(repeated[0].encode(),repeated[1].encode())
        }
        assertEquals(6000,testScheduler.currentTime);s.close()
    }
    @Test fun unsupportedFallsBackOnceButBusyDoesNot()=runTest {
        val old=Radio(reject=0x80);val s=ProtocolSession(old,backgroundScope);s.handshake()
        repeat(2){assertEquals(Op.OPEN_WIDE,s.openTransfer(1uL,2,0).message.opcode)}
        assertEquals(listOf(Op.HELLO,Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED,Op.OPEN_LONG,Op.OPEN_DIRECT,Op.OPEN_BULK,Op.OPEN_COMPACT,Op.OPEN_WIDE,Op.OPEN_WIDE),old.requests.map{it.opcode});s.close()
        val busy=Radio(reject=0x82);val t=ProtocolSession(busy,backgroundScope);t.handshake()
        try{t.openTransfer(1uL,2,0);fail("Expected BUSY")}catch(e:DeviceError){assertEquals(0x82,e.code)}
        assertEquals(listOf(Op.HELLO,Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED,Op.OPEN_LONG,Op.OPEN_DIRECT,Op.OPEN_BULK,Op.OPEN_COMPACT),busy.requests.map{it.opcode});t.close()
    }
}
