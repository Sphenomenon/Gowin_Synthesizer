package cn.gowin.control.ble

import cn.gowin.control.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.util.UUID

@OptIn(ExperimentalCoroutinesApi::class)
class RecordingFormatsSessionTest {
    private class Peer(val mode:String):BleTransport {
        val live=MutableStateFlow(true)
        private val received=MutableSharedFlow<Notification>(extraBufferCapacity=32)
        override val connected=live.asStateFlow()
        override val notifications=received.asSharedFlow()
        private val assembler=Reassembler()
        val formatRequests=mutableListOf<ByteArray>()
        override suspend fun connect(address:String) {}
        override suspend fun read(uuid:UUID)=Writer().u8(1).u8(20).u16(512).u64(7uL).u32(0x68).u16(256).u8(1).u8(1).build()
        override suspend fun subscribe(uuid:UUID) {}
        override suspend fun write(value:ByteArray) {
            val raw=assembler.accept(value,0) ?: return
            val request=Message.decode(raw)
            var status=0
            val payload=when(request.opcode) {
                Op.HELLO -> Writer().u64(7uL).u32(0x68).u32(1).u32(0).build()
                Op.STATUS -> if(mode=="expired") {
                    status=0x85;Writer().u16(0).u16(0).u32(1).build()
                } else Snapshot(flags=0).encode()
                Op.RECORDING_FORMATS -> {
                    assertArrayEquals(RecordingFormats.requestPayload(),request.payload)
                    formatRequests+=raw
                    if(mode=="timeout")return
                    if(mode in listOf("unsupported","busy")) {
                        status=if(mode=="unsupported")0x80 else 0x82
                        Writer().u16(0).u16(0).u32(1).build()
                    } else Writer().u16(1).u16(if(mode=="reserved")1 else 0).u32(3).u64(if(mode=="boot")8uL else 7uL).build()
                }
                else -> error("unexpected command")
            }
            val wrongNonce=request.opcode==Op.RECORDING_FORMATS && mode=="nonce"
            val reply=Message(request.opcode,status,request.requestId,if(wrongNonce)request.nonce xor 1uL else request.nonce,payload).encode()
            if(request.opcode==Op.RECORDING_FORMATS && mode=="crc")reply[reply.lastIndex]=(reply.last().toInt() xor 1).toByte()
            fragment(reply,1).forEach{received.emit(Notification(GattIds.response,it))}
        }
        override fun close(){live.value=false}
    }
    @Test fun explicitUnsupportedIsTheOnlyLegacyFallback()=runTest {
        val peer=Peer("unsupported");val session=ProtocolSession(peer,backgroundScope)
        session.handshake();assertEquals(1,session.recordingFormats.mask)
        assertEquals(1,session.negotiateRecordingFormats().mask)
        assertEquals(1,peer.formatRequests.size);session.close()
    }
    @Test fun grantIsClearedOnDisconnectAndNewSessionStartsLegacy()=runTest {
        val peer=Peer("success");val session=ProtocolSession(peer,backgroundScope)
        session.handshake();assertEquals(3,session.negotiateRecordingFormats().mask)
        peer.live.value=false;runCurrent()
        assertEquals(1,session.recordingFormats.mask);session.close()
        val next=ProtocolSession(Peer("success"),backgroundScope)
        next.handshake();assertEquals(1,next.recordingFormats.mask);next.close()
    }
    @Test fun corruptMissingOrMismatchedReceiptNeverGrantsOrSilentlyFallsBack()=runTest {
        for(mode in listOf("boot","reserved","busy","timeout","nonce","crc")) {
            val peer=Peer(mode);val session=ProtocolSession(peer,backgroundScope);session.handshake()
            var rejected=false
            try{session.negotiateRecordingFormats()}catch(e:Exception){
                assertTrue(e is ProtocolException || e is DeviceError || e is IOException);rejected=true
            }
            assertTrue("accepted $mode",rejected);assertEquals(1,session.recordingFormats.mask)
            if(mode in listOf("timeout","nonce","crc")) {
                assertEquals(4,peer.formatRequests.size)
                peer.formatRequests.forEach{assertArrayEquals(peer.formatRequests.first(),it)}
            }
            session.close()
        }
    }
    @Test fun explicitClosedWindowAndExpiredSessionRevokeGrant()=runTest {
        for(mode in listOf("window","expired")) {
            val peer=Peer(mode);val session=ProtocolSession(peer,backgroundScope)
            session.handshake();assertEquals(3,session.negotiateRecordingFormats().mask)
            try{session.request(Op.STATUS)}catch(e:DeviceError){assertEquals(0x85,e.code)}
            assertEquals(1,session.recordingFormats.mask)
            var rejected=false
            try{session.negotiateRecordingFormats()}catch(e:ProtocolException){rejected=true}
            assertTrue(rejected);session.close()
        }
    }
}
