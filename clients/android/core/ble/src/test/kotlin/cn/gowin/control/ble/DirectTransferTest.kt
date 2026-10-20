package cn.gowin.control.ble

import cn.gowin.control.protocol.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class DirectTransferTest {
    private class Radio(val reject:Int?=null,var corrupt:String?=null,var dropOpen:Boolean=false,
                        val badOpen:Boolean=false):BleTransport {
        val requests=mutableListOf<Message>()
        val pcm=ByteArray(460){(it*13).toByte()}
        private val assembly=Reassembler()
        private val incoming=MutableSharedFlow<Notification>(extraBufferCapacity=64)
        override val notifications=incoming.asSharedFlow()
        override val connected=MutableStateFlow(true).asStateFlow()
        override suspend fun connect(address:String){}
        override suspend fun subscribe(uuid:UUID){}
        override suspend fun read(uuid:UUID)=hexBytes("01140002a8d59dfad4ea4e7d6800000000010101")
        private suspend fun response(m:Message,payload:ByteArray,status:Int=0) {
            fragment(Message(m.opcode,status,m.requestId,m.nonce,payload).encode(),1).forEach {
                incoming.emit(Notification(GattIds.response,it))
            }
        }
        override suspend fun write(value:ByteArray) {
            val m=Message.decode(assembly.accept(value,0)?:return);requests+=m
            when(m.opcode) {
                Op.HELLO -> response(m,hexBytes("a8d59dfad4ea4e7d680000000100000000000000"))
                Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED,Op.OPEN_LONG -> response(m,Writer().u16(0).u16(0).u32(1).build(),0x80)
                Op.OPEN_DIRECT,Op.OPEN_BULK -> {
                    if(m.opcode==Op.OPEN_DIRECT && dropOpen){dropOpen=false;return}
                    if(m.opcode==Op.OPEN_DIRECT && reject!=null)response(m,Writer().u16(0).u16(0).u32(1).build(),reject)
                    else response(m,Writer().u32(7).u32(192000).u32(23).u32(if(badOpen)4 else 0).u16(460).u8(1).u8(0).u16(182).u16(0).build())
                }
                Op.READ,Op.ACK_READ -> {
                    if(corrupt=="error") {
                        corrupt=null;response(m,Writer().u16(0).u16(0).u32(1).build(),0x8d);return
                    }
                    val r=Reader(m.payload);val tid=r.u32();val offset=r.u32();val n=r.u16();r.zero(2)
                    val fault=corrupt;corrupt=null
                    val payload=Writer().u32(if(fault=="transfer")8 else tid).u64(if(fault=="boot")2uL else 1uL)
                        .u32(if(fault=="record")3 else 2).u32(if(fault=="offset")offset+4 else offset)
                        .u16(n).u16(if(fault=="reserved")1 else 0).u32(if(fault=="crc")0 else crc32(pcm)).bytes(pcm).build()
                    val raw=Message(Op.DATA,0,m.requestId,if(fault=="nonce")m.nonce+1uL else m.nonce,payload).encode()
                    val parts=raw.toList().chunked(178)
                    parts.forEachIndexed { i,p ->
                        if(fault!="loss" || i!=1)incoming.emit(Notification(GattIds.transfer,
                            Writer().u8(0xb3).u16(7).u8(i or (if(i==0)64 else 0) or (if(i==parts.lastIndex)128 else 0)).bytes(p.toByteArray()).build()))
                    }
                    // No positive Response. It must be negotiated, validated DATA.
                }
            }
        }
        override fun close(){}
    }
    @Test fun directDataCompletesReadAndAckReadWithoutResponse()=runTest {
        val radio=Radio();val s=ProtocolSession(radio,backgroundScope);s.handshake()
        assertEquals(Op.OPEN_DIRECT,s.openTransfer(1uL,2,0).message.opcode)
        assertArrayEquals(radio.pcm,PcmBlock.decode(s.readBlock(7,0,460).data!!.payload,460).data)
        assertEquals(Op.ACK_READ,s.readBlock(7,460,460,crc32(radio.pcm)).message.opcode)
        assertEquals(0,testScheduler.currentTime);s.close()
    }
    @Test fun missingOrInvalidDataRetriesIdenticalRequestRatherThanConfirmingIt()=runTest {
        for(fault in listOf("loss","crc","transfer","boot","record","offset","reserved","nonce")) {
            val radio=Radio(corrupt=fault);val s=ProtocolSession(radio,backgroundScope);s.handshake();s.openTransfer(1uL,2,0)
            assertArrayEquals(radio.pcm,PcmBlock.decode(s.readBlock(7,0,460).data!!.payload,460).data)
            val reads=radio.requests.filter{it.opcode==Op.READ};assertEquals(fault,2,reads.size)
            assertArrayEquals(reads[0].encode(),reads[1].encode());s.close()
        }
        assertEquals(24000,testScheduler.currentTime)
    }
    @Test fun lostOpenRetriesSameIdAndErrorsRemainExplicit()=runTest {
        val radio=Radio(dropOpen=true,corrupt="error");val s=ProtocolSession(radio,backgroundScope);s.handshake();s.openTransfer(1uL,2,0)
        val opens=radio.requests.filter{it.opcode==Op.OPEN_DIRECT};assertEquals(2,opens.size);assertArrayEquals(opens[0].encode(),opens[1].encode())
        try{s.readBlock(7,0,460);fail("Expected explicit error")}catch(e:DeviceError){assertEquals(0x8d,e.code)}
        assertEquals(3000,testScheduler.currentTime);s.close()
    }
    @Test fun mismatchedDirectOpenMetadataNeverEnablesReceiptsOrDowngrades()=runTest {
        val radio=Radio(badOpen=true);val s=ProtocolSession(radio,backgroundScope);s.handshake()
        try{s.openTransfer(1uL,2,0);fail("Invalid metadata")}catch(_:java.io.IOException){}
        val opens=radio.requests.filter{it.opcode==Op.OPEN_DIRECT};assertEquals(4,opens.size)
        assertTrue(opens.all{it.opcode==Op.OPEN_DIRECT && it.encode().contentEquals(opens[0].encode())})
        assertEquals(12000,testScheduler.currentTime);s.close()
    }
    @Test fun unsupportedProbesOnceAndBusyDoesNotDowngrade()=runTest {
        val old=Radio(reject=0x80);val s=ProtocolSession(old,backgroundScope);s.handshake()
        repeat(2){assertEquals(Op.OPEN_BULK,s.openTransfer(1uL,2,0).message.opcode)}
        assertEquals(listOf(Op.HELLO,Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED,Op.OPEN_LONG,Op.OPEN_DIRECT,Op.OPEN_BULK,Op.OPEN_BULK),old.requests.map{it.opcode})
        // Same DATA without a successful 0x39 may not replace the Response.
        try{s.readBlock(7,0,460);fail("Unnegotiated receipt")}catch(_:java.io.IOException){}
        assertEquals(12000,testScheduler.currentTime);s.close()
        val busy=Radio(reject=0x82);val t=ProtocolSession(busy,backgroundScope);t.handshake()
        try{t.openTransfer(1uL,2,0);fail("Expected BUSY")}catch(e:DeviceError){assertEquals(0x82,e.code)}
        assertEquals(listOf(Op.HELLO,Op.OPEN_SECOND,Op.OPEN_LOSSLESS,Op.OPEN_EXTENDED,Op.OPEN_LONG,Op.OPEN_DIRECT),busy.requests.map{it.opcode});t.close()
    }
}
