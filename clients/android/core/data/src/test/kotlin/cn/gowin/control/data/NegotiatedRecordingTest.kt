package cn.gowin.control.data

import cn.gowin.control.ble.*
import cn.gowin.control.protocol.*
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test
import java.io.RandomAccessFile
import java.nio.file.Files
import java.util.UUID
import kotlin.math.sin

/** Offline peripheral fixture: real framing/CRC/session/PCM/checkpoint/WAV code. */
@OptIn(ExperimentalCoroutinesApi::class)
class NegotiatedRecordingTest {
    private val pcm=ByteArray(882*4).also { bytes -> repeat(882) { frame -> repeat(2) { channel ->
        val sample=(12000*sin(2*Math.PI*(if(channel==0)440 else 660)*frame/44100)).toInt()
        val at=frame*4+channel*2;bytes[at]=sample.toByte();bytes[at+1]=(sample shr 8).toByte()
    } } }
    private val info=RecordingInfo(7uL,9,4,2,2,2,44100,882,pcm.size.toLong(),882,crc32(pcm),1,0,1)
    private inner class Peer:BleTransport {
        private val incoming=Reassembler()
        private val outgoing=MutableSharedFlow<Notification>(extraBufferCapacity=64)
        override val notifications=outgoing.asSharedFlow()
        override val connected=MutableStateFlow(true).asStateFlow()
        private var granted=false
        override suspend fun connect(address:String) {}
        override suspend fun read(uuid:UUID)=Writer().u8(1).u8(20).u16(512).u64(info.boot).u32(0x68).u16(256).u8(1).u8(1).build()
        override suspend fun subscribe(uuid:UUID) {}
        private suspend fun emit(m:Message,uuid:UUID=GattIds.response) {
            fragment(m.encode(),1).forEach{outgoing.emit(Notification(uuid,it))}
        }
        override suspend fun write(value:ByteArray) {
            val raw=incoming.accept(value,0) ?: return;val m=Message.decode(raw);val r=Reader(m.payload)
            if(m.opcode==Op.INFO && !granted) {
                emit(m.copy(status=0x80,payload=Writer().u16(0).u16(0).u32(1).build()));return
            }
            val payload=when(m.opcode) {
                Op.HELLO -> {granted=false;Writer().u64(info.boot).u32(0x68).u32(1).u32(0).build()}
                Op.RECORDING_FORMATS -> {assertArrayEquals(RecordingFormats.requestPayload(),m.payload);granted=true
                    Writer().u16(1).u16(0).u32(3).u64(info.boot).build()}
                Op.INFO -> info.encode()
                Op.OPEN -> {check(granted);assertEquals(info.boot,r.u64());assertEquals(info.id,r.u32());val offset=r.u32()
                    Writer().u32(3).u32(info.bytes).u32(info.crc).u32(offset).u16(256).u8(1).u8(0).build()}
                Op.READ -> {assertEquals(3,r.u32());val offset=r.u32();val n=r.u16();r.zero(2)
                    val data=pcm.copyOfRange(offset.toInt(),offset.toInt()+n)
                    val block=Writer().u32(3).u64(info.boot).u32(info.id).u32(offset).u16(n).u16(0).u32(crc32(data)).bytes(data).build()
                    emit(Message(Op.DATA,0,m.requestId,m.nonce,block),GattIds.transfer)
                    Writer().u32(3).u32(offset).u16(n).u16(0).build()}
                Op.ACK -> {assertEquals(3,r.u32());val offset=r.u32();r.u32();Writer().u32(3).u32(offset).build()}
                Op.CLOSE,Op.CANCEL -> Writer().u32(3).build()
                else -> error("unexpected fixture opcode")
            }
            emit(m.copy(payload=payload))
        }
        override fun close() {}
    }
    @Test fun negotiated44100DownloadResumesOnlyAfterNewHelloGrantAndPackagesExactPcm()=runTest {
        val root=Files.createTempDirectory("recording-session-44100").toFile()
        try {
            val files=RecordingFiles(root)
            suspend fun connect():ProtocolSession {
                val session=ProtocolSession(Peer(),backgroundScope);session.handshake()
                try{session.request(Op.INFO,Writer().u32(0).build());fail("ungranted format2 exposed")}
                catch(e:DeviceError){assertEquals(0x80,e.code)}
                session.negotiateRecordingFormats();return session
            }
            var session=connect()
            var current=RecordingInfo.decode(session.request(Op.INFO,Writer().u32(0).build()).message.payload,session.recordingFormats)
            suspend fun open(offset:Long) {session.request(Op.OPEN,Writer().u64(info.boot).u32(info.id).u32(offset).build())}
            suspend fun block(offset:Long):Long {
                val n=minOf(256L,info.bytes-offset).toInt()
                val reply=session.request(Op.READ,Writer().u32(3).u32(offset).u16(n).u16(0).build(),data=true)
                val block=PcmBlock.decode(reply.data!!.payload)
                assertEquals(info.boot,block.boot);assertEquals(info.id,block.recording);assertEquals(offset,block.offset)
                RandomAccessFile(files.part(info),"rw").use { f ->
                    f.seek(offset);f.write(block.data);files.persist(info,f,offset+n,RecordingFiles.fileCrc(files.part(info)))
                }
                session.request(Op.ACK,Writer().u32(3).u32(offset+n).u32(block.crc).build())
                return offset+n
            }
            open(0);assertEquals(256,block(0));session.request(Op.CANCEL,Writer().u32(3).build());session.close()
            session=connect()
            current=RecordingInfo.decode(session.request(Op.INFO,Writer().u32(0).build()).message.payload,session.recordingFormats).also{assertTrue(current.samePcmObject(it))}
            var offset=files.recover(current).offset;assertEquals(256,offset);open(offset)
            while(offset<info.bytes)offset=block(offset)
            session.request(Op.CLOSE,Writer().u32(3).u32(info.crc).build())
            val saved=files.packageWav(current,false,formats=session.recordingFormats)
            assertArrayEquals(pcm,saved.file.readBytes().copyOfRange(44,saved.file.length().toInt()))
            assertEquals(44100,Reader(saved.file.readBytes().copyOfRange(24,28)).u32())
            assertEquals(176400,Reader(saved.file.readBytes().copyOfRange(28,32)).u32())
            session.close()
        }finally{root.deleteRecursively()}
    }
}
