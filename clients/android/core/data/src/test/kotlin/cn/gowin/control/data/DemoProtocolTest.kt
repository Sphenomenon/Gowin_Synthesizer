package cn.gowin.control.data

import cn.gowin.control.ble.*
import cn.gowin.control.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayOutputStream

@OptIn(ExperimentalCoroutinesApi::class)
class DemoProtocolTest {
    @Test fun handshakeParametersRecordAndTransferBeforeResponse()=runTest {
        val fake=DemoTransport(backgroundScope)
        fake.connect("demo")
        val session=ProtocolSession(fake,backgroundScope)
        val cap=session.handshake();assertTrue(cap.has(5));assertFalse(cap.has(4))
        assertEquals(1,session.negotiateRecordingFormats().mask) // Real legacy command/PCM flow continues after UNSUPPORTED.
        var status=Snapshot.decode(session.request(Op.STATUS).message.payload)
        session.request(Op.SET_PARAM,Writer().u16(1).u16(0).u32(82).u32(status.revision).build())
        status=Snapshot.decode(session.request(Op.STATUS).message.payload);assertEquals(82,status.volume)
        try {
            session.request(Op.SET_PARAM,Writer().u16(1).u16(0).u32(12).u32(1).build());fail("stale revision accepted")
        }catch(e:DeviceError){assertEquals(0x84,e.code)}
        session.request(Op.START,Writer().u8(1).u8(0).u16(0).u32(48).build())
        // A one-millisecond recording reaches capacity based on wall time without relying on virtual time.
        Thread.sleep(5)
        val info=RecordingInfo.decode(session.request(Op.INFO,Writer().u32(0).build()).message.payload)
        assertTrue(info.ready);assertEquals(48,info.frames)
        val open=Reader(session.request(Op.OPEN,Writer().u64(info.boot).u32(info.id).u32(0).build()).message.payload)
        val transfer=open.u32();val data=ByteArrayOutputStream();var offset=0L
        while(offset<info.bytes){
            val n=minOf(256L,info.bytes-offset).toInt()
            val reply=session.request(Op.READ,Writer().u32(transfer).u32(offset).u16(n).u16(0).build(),data=true)
            val block=PcmBlock.decode(reply.data!!.payload);data.write(block.data);offset+=n
            session.request(Op.ACK,Writer().u32(transfer).u32(offset).u32(block.crc).build())
            // A semantically duplicate ACK with a fresh request ID must not advance twice.
            session.request(Op.ACK,Writer().u32(transfer).u32(offset).u32(block.crc).build())
        }
        assertEquals(info.bytes,data.size().toLong());assertEquals(info.crc,crc32(data.toByteArray()))
        assertArrayEquals(DemoMelody.pcm(info.frames),data.toByteArray())
        session.request(Op.CLOSE,Writer().u32(transfer).u32(info.crc).build())
        session.close();fake.close()
    }

    @Test fun recordingNeedsElapsedTimeThenStopBeforeItCanBeDownloaded()=runTest {
        var clock=1000L
        val fake=DemoTransport(backgroundScope){clock}
        fake.connect("demo")
        val session=ProtocolSession(fake,backgroundScope)
        session.handshake()
        fun identity(info:RecordingInfo)=Writer().u64(info.boot).u32(info.id).u32(0).build()
        suspend fun info()=RecordingInfo.decode(session.request(Op.INFO,Writer().u32(0).build()).message.payload)
        val empty=info()
        assertEquals(0,empty.state);assertEquals(0,empty.frames)
        session.request(Op.START,Writer().u8(1).u8(0).u16(0).u32(0).build())
        val starting=info()
        assertEquals(2,starting.state);assertEquals(0,starting.frames);assertFalse(starting.ready)
        clock+=3250
        val recording=info()
        assertEquals(156000,recording.frames);assertFalse(recording.ready)
        try {
            session.request(Op.OPEN,identity(recording));fail("active recording opened for download")
        }catch(e:DeviceError){assertEquals(0x83,e.code)}
        session.request(Op.STOP,Writer().u64(recording.boot).u32(recording.id).build())
        val sealed=info()
        assertTrue(sealed.ready);assertEquals(156000,sealed.frames);assertEquals(624000,sealed.bytes)
        assertEquals(crc32(DemoMelody.pcm(sealed.frames)),sealed.crc)
        clock+=5000
        assertEquals(sealed.frames,info().frames)
        session.close();fake.close()
    }
}
