package cn.gowin.control.protocol

import org.junit.Assert.*
import org.junit.Test

class RecordingFormatsTest {
    private val info=RecordingInfo(7uL,1,4,1,2,2,48000,2,8,100,0,1,0,7)
    private fun grant(mask:Long=3,boot:ULong=7uL)=Message(Op.RECORDING_FORMATS,0,2,1uL,
        Writer().u16(1).u16(0).u32(mask).u64(boot).build())
    @Test fun explicitGrantKeepsLegacyAndAllowsOnlyMatching44100Tuple() {
        assertArrayEquals(hexBytes("0100000003000000"),RecordingFormats.requestPayload())
        assertEquals(info,RecordingInfo.decode(info.encode()))
        val at441=info.copy(format=2,sampleRate=44100)
        assertThrows(ProtocolException::class.java){RecordingInfo.decode(at441.encode())}
        val formats=RecordingFormats.decodeResponse(grant(),7uL)
        assertEquals(at441,RecordingInfo.decode(at441.encode(),formats))
        for(bad in listOf(info.copy(sampleRate=44100),at441.copy(sampleRate=48000),at441.copy(channels=1),
            at441.copy(format=3),at441.copy(bytes=4),at441.copy(frames=101,bytes=404),at441.copy(flags=0),at441.copy(boot=8uL))) {
            assertThrows(ProtocolException::class.java){RecordingInfo.decode(bad.encode(),formats)}
        }
    }
    @Test fun rejectUnknownOrMalformedOrDifferentBootGrants() {
        for(message in listOf(grant(0),grant(2),grant(5),grant(3,8uL),grant().copy(status=1),
            grant().copy(payload=grant().payload+0),
            grant().copy(payload=grant().payload.copyOf().apply{this[2]=1}))) {
            assertThrows(ProtocolException::class.java){RecordingFormats.decodeResponse(message,7uL)}
        }
    }
    @Test fun reconnectIdentityIncludesRateFormatAndFrameGeometry() {
        assertTrue(info.samePcmObject(info.copy()))
        for(changed in listOf(info.copy(boot=8uL),info.copy(id=2),info.copy(format=2,sampleRate=44100),
            info.copy(sampleRate=44100),info.copy(channels=1),info.copy(frames=3),info.copy(bytes=4),
            info.copy(crc=1),info.copy(state=2,flags=0))) assertFalse(info.samePcmObject(changed))
    }
}
