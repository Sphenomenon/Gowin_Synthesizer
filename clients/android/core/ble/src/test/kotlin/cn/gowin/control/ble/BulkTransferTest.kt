package cn.gowin.control.ble

import cn.gowin.control.protocol.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class BulkTransferTest {
    private fun parts(raw:ByteArray,valueLimit:Int,token:Int=7):List<ByteArray> {
        val capacity=valueLimit-4
        return raw.toList().chunked(capacity).mapIndexed { i,data ->
            Writer().u8(0xb3).u16(token).u8(i or (if(i==0)64 else 0) or
                (if((i+1)*capacity>=raw.size)128 else 0)).bytes(data.toByteArray()).build()
        }
    }
    @Test fun everyMessageLengthAtMultipleNegotiatedLimitsKeepsBytesAndDuplicates() {
        for(limit in listOf(20,21,60,182,244))for(size in 1..512) {
            val raw=ByteArray(size){(it*19).toByte()};val fragments=parts(raw,limit,if(size%2==0)0 else 65535)
            val assembly=Reassembler(bulkValueLimit=limit);var result:ByteArray?=null
            fragments.forEachIndexed { i,part ->
                result=assembly.accept(part,i.toLong())
                if(i<fragments.lastIndex)assertNull(assembly.accept(part,i.toLong()))
            }
            assertArrayEquals(raw,result)
            assertThrows(ProtocolException::class.java){Reassembler(allowCompact=true).accept(fragments.first(),0)}
        }
        assertEquals(3,parts(ByteArray(508),182).size)
        assertEquals(3,parts(ByteArray(508),244).size)
        assertEquals(32,parts(ByteArray(508),20).size)
    }
    @Test fun lostCorruptShortMixedAndOversizedFragmentsRequireFreshFirst() {
        val raw=ByteArray(508){it.toByte()};val p=parts(raw,182);val a=Reassembler(bulkValueLimit=182)
        a.accept(p[0],0)
        assertThrows(ProtocolException::class.java){a.accept(p[2],1)}
        a.accept(p[0],2)
        assertThrows(ProtocolException::class.java){a.accept(p[0].copyOf().apply{this[4]=99},3)}
        assertThrows(ProtocolException::class.java){a.accept(p[0].copyOf(181),4)}
        assertThrows(ProtocolException::class.java){a.accept(parts(raw,244)[0],5)}
        a.accept(p[0],6)
        assertThrows(ProtocolException::class.java){a.accept(fragment(raw,7)[1],7)}
        a.accept(p[0],8)
        assertThrows(ProtocolException::class.java){a.accept(p[1],2009)}
        var result:ByteArray?=null;p.forEachIndexed{i,f->result=a.accept(f,2010+i.toLong())}
        assertArrayEquals(raw,result)
        assertThrows(IllegalArgumentException::class.java){Reassembler(bulkValueLimit=19)}
        assertThrows(IllegalArgumentException::class.java){Reassembler(bulkValueLimit=245)}
    }
    private fun openPayload(limit:Int=182)=Writer().u32(7).u32(192000).u32(23).u32(0)
        .u16(460).u8(1).u8(0).u16(limit).u16(0).build()
    @Test fun openMetadataRequiresExplicitOpcodeLengthLimitWindowAndReservedBytes() {
        val good=Message(Op.OPEN_BULK,0,2,1uL,openPayload())
        assertEquals(182,TransferOpen.decode(good).valueLimit)
        assertEquals(460,TransferOpen.decode(good).maxChunk)
        for(payload in listOf(openPayload(19),openPayload(245),openPayload().copyOf(20),
            openPayload().apply{this[22]=1},openPayload().apply{this[18]=2},openPayload().apply{this[0]=0})) {
            assertThrows(ProtocolException::class.java){TransferOpen.decode(good.copy(payload=payload))}
        }
        assertThrows(ProtocolException::class.java){TransferOpen.decode(good.copy(opcode=Op.OPEN_COMPACT))}
    }
    private inner class Radio(private val reject:Int?=null,private var dropOpen:Boolean=false,
                              private var loseData:Boolean=false,private val badLimit:Boolean=false):BleTransport {
        private val assembly=Reassembler()
        private val incoming=MutableSharedFlow<Notification>(extraBufferCapacity=64)
        override val notifications=incoming.asSharedFlow()
        override val connected=MutableStateFlow(true).asStateFlow()
        val requests=mutableListOf<Message>();val pcm=ByteArray(460){(it*13).toByte()}
        override suspend fun connect(address:String) {}
        override suspend fun subscribe(uuid:UUID) {}
        override suspend fun read(uuid:UUID)=hexBytes("01140002a8d59dfad4ea4e7d6800000000010101")
        override suspend fun write(value:ByteArray) {
            val m=Message.decode(assembly.accept(value,0)?:return);requests+=m
            if(m.opcode==Op.OPEN_BULK && dropOpen){dropOpen=false;return}
            val error=if(m.opcode in setOf(Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED,Op.OPEN_LONG,Op.OPEN_DIRECT))0x80 else if(m.opcode==Op.OPEN_BULK)reject else null
            val payload=when {
                error!=null -> Writer().u16(0).u16(0).u32(1).build()
                m.opcode==Op.HELLO -> hexBytes("a8d59dfad4ea4e7d680000000100000000000000")
                m.opcode==Op.READ -> Writer().u32(7).u32(0).u16(460).u16(0).build()
                m.opcode==Op.OPEN_BULK -> openPayload(if(badLimit)245 else 182)
                else -> openPayload().copyOf(20)
            }
            fragment(Message(m.opcode,error?:0,m.requestId,m.nonce,payload).encode(),1).forEach {
                incoming.emit(Notification(GattIds.response,it))
            }
            if(m.opcode==Op.READ) {
                val block=Writer().u32(7).u64(1uL).u32(2).u32(0).u16(460).u16(0).u32(crc32(pcm)).bytes(pcm).build()
                parts(Message(Op.DATA,0,m.requestId,m.nonce,block).encode(),182).forEachIndexed{i,f->
                    if(!loseData || i!=1)incoming.emit(Notification(GattIds.transfer,f))
                }
                loseData=false
            }
        }
        override fun close() {}
    }
    @Test fun optedInBulkReceivesLargeValuesAndRetriesSameOpenAndReadAfterLoss()=runTest {
        val radio=Radio(dropOpen=true,loseData=true);val s=ProtocolSession(radio,backgroundScope);s.handshake()
        assertEquals(Op.OPEN_BULK,s.openTransfer(1uL,2,0).message.opcode)
        assertArrayEquals(radio.pcm,PcmBlock.decode(s.readBlock(7,0,460).data!!.payload,460).data)
        for(op in listOf(Op.OPEN_BULK,Op.READ)) {
            val repeated=radio.requests.filter{it.opcode==op};assertEquals(2,repeated.size)
            assertArrayEquals(repeated[0].encode(),repeated[1].encode())
        }
        assertEquals(6000,testScheduler.currentTime);s.close()
    }
    @Test fun explicitUnsupportedFallsBackOnceButBusyAndInvalidMetadataNeverChangeOpen()=runTest {
        val old=Radio(reject=0x80);val s=ProtocolSession(old,backgroundScope);s.handshake()
        repeat(2){assertEquals(Op.OPEN_COMPACT,s.openTransfer(1uL,2,0).message.opcode)}
        assertEquals(listOf(Op.HELLO,Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED,Op.OPEN_LONG,Op.OPEN_DIRECT,Op.OPEN_BULK,Op.OPEN_COMPACT,Op.OPEN_COMPACT),old.requests.map{it.opcode});s.close()
        val busy=Radio(reject=0x82);val t=ProtocolSession(busy,backgroundScope);t.handshake()
        try{t.openTransfer(1uL,2,0);fail("Expected BUSY")}catch(e:DeviceError){assertEquals(0x82,e.code)}
        assertEquals(listOf(Op.HELLO,Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED,Op.OPEN_LONG,Op.OPEN_DIRECT,Op.OPEN_BULK),busy.requests.map{it.opcode});t.close()
        val bad=Radio(badLimit=true);val u=ProtocolSession(bad,backgroundScope);u.handshake()
        try{u.openTransfer(1uL,2,0);fail("Expected timeout")}catch(_:java.io.IOException){}
        val retries=bad.requests.filter{it.opcode==Op.OPEN_BULK};assertEquals(4,retries.size)
        assertTrue(retries.all{it.opcode==Op.OPEN_BULK && it.encode().contentEquals(retries[0].encode())});u.close()
    }
}
