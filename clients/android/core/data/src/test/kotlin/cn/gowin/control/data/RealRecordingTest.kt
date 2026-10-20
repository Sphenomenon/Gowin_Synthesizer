package cn.gowin.control.data

import cn.gowin.control.ble.*
import cn.gowin.control.protocol.*
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.io.RandomAccessFile
import java.util.zip.CRC32

/** APK session, PCM parser, durable checkpoints and WAV packaging over physical BLE. */
class RealRecordingTest {
    @Test fun builtInRecordingDownloadAndReconnectToWav() = runBlocking {
        val port=System.getenv("GW25K_BLE_BRIDGE_PORT")?.toIntOrNull()
        val output=System.getenv("GW25K_RECORDING_OUTPUT")
        assumeTrue(port!=null && output!=null)
        val scope=CoroutineScope(SupervisorJob()+Dispatchers.Default)
        val files=RecordingFiles(File(output!!))
        var radio:RadioBridge?=null
        var session:ProtocolSession?=null
        suspend fun connect():ProtocolSession {
            val t=RadioBridge(port!!);radio=t;t.connect("GW25K-PROTO")
            val s=ProtocolSession(t,scope);session=s
            val cap=s.handshake();assertEquals(0x68L,cap.flags);assertTrue(cap.has(3));assertTrue(cap.has(5))
            return s
        }
        suspend fun info(s:ProtocolSession)=RecordingInfo.decode(s.request(Op.INFO,Writer().u32(0).build()).message.payload)
        suspend fun operation(s:ProtocolSession,id:Long) {
            withTimeout(5000) {
                while(true) {
                    val raw=s.request(Op.OPERATION,Writer().u32(id).build()).message.payload
                    if(raw[9].toInt()==2) break
                    delay(25)
                }
            }
        }
        try {
            var s=connect()
            // Dropping a transport write must trigger the existing identical-ID
            // logical retry; no partial recording command may execute.
            val injectLoss=System.getenv("GW25K_DROP_ONE_COMMAND_FRAGMENT")=="1"
            if(injectLoss) radio!!.dropNextWrite=true
            var rec=info(s)
            if(rec.state in listOf(4,5)) {s.request(Op.CLEAR,Writer().u64(rec.boot).u32(rec.id).build());rec=info(s)}
            assertEquals(0,rec.state)
            val start=Reader(s.request(Op.START,Writer().u8(1).u8(0).u16(0).u32(0).build()).message.payload)
            operation(s,start.u32())
            withTimeout(5000) {while(true){rec=info(s);if(rec.ready)break;delay(100)}}
            assertEquals(48000L,rec.frames);assertEquals(192000L,rec.bytes)
            assertEquals(2773108656L,rec.crc)
            val checksum=CRC32()
            var offset=0L;var transfer=0L;var limit=0
            var previousCrc:Long?=null;var combinedBlocks=0;var injectedOffset:Long?=null
            suspend fun open() {
                val opened=s.openTransfer(rec.boot,rec.id,offset).message
                val r=Reader(opened.payload)
                transfer=r.u32();assertEquals(rec.bytes,r.u32());assertEquals(rec.crc,r.u32());assertEquals(offset,r.u32())
                limit=r.u16()
                System.getenv("GW25K_EXPECT_WIDE_OPEN")?.let { expected ->
                    assertEquals(if(System.getenv("GW25K_EXPECT_EXTENDED_OPEN")=="1")8112 else if(System.getenv("GW25K_EXPECT_LONG_OPEN")=="1")972 else if(expected=="1")460 else 256,limit)
                    assertEquals(if(expected=="1") {
                        when {
                            System.getenv("GW25K_EXPECT_SECOND_OPEN")=="1" -> Op.OPEN_SECOND
                            System.getenv("GW25K_EXPECT_LOSSLESS_OPEN")=="1" -> Op.OPEN_LOSSLESS
                            System.getenv("GW25K_EXPECT_EXTENDED_OPEN")=="1" -> Op.OPEN_EXTENDED
                            System.getenv("GW25K_EXPECT_LONG_OPEN")=="1" -> Op.OPEN_LONG
                            System.getenv("GW25K_EXPECT_DIRECT_OPEN")=="1" -> Op.OPEN_DIRECT
                            System.getenv("GW25K_EXPECT_BULK_OPEN")=="1" -> Op.OPEN_BULK
                            System.getenv("GW25K_EXPECT_COMPACT_OPEN")=="1" -> Op.OPEN_COMPACT
                            else -> Op.OPEN_WIDE
                        }
                    } else Op.OPEN,opened.opcode)
                }
                assertTrue(limit in 4..(if(opened.opcode in setOf(Op.OPEN_EXTENDED,Op.OPEN_LOSSLESS,Op.OPEN_SECOND))8112 else if(opened.opcode==Op.OPEN_LONG)972 else if(opened.opcode in setOf(Op.OPEN_DIRECT,Op.OPEN_BULK,Op.OPEN_WIDE,Op.OPEN_COMPACT))460 else 256));assertEquals(0,limit%4)
            }
            open()
            val downloadStart=System.nanoTime()
            RandomAccessFile(files.part(rec),"rw").use { pcm ->
                while(offset<rec.bytes) {
                    val boundary=listOf(14720L,29440L).firstOrNull{it>offset}?:rec.bytes
                    val n=minOf(limit.toLong(),rec.bytes-offset,boundary-offset).toInt()
                    if(injectLoss && injectedOffset==null && previousCrc!=null && System.getenv("GW25K_EXPECT_ACK_READ")=="1") {
                        injectedOffset=offset
                        if(System.getenv("GW25K_EXPECT_DIRECT_OPEN")=="1")radio!!.dropNextTransfer=true else radio!!.dropNextResponse=true
                    }
                    val reply=s.readBlock(transfer,offset,n,previousCrc)
                    if(reply.message.opcode in setOf(Op.ACK_READ,Op.ACK_READ_LOSSLESS,Op.ACK_READ_SECOND))combinedBlocks++
                    if(injectLoss && offset==injectedOffset && System.getenv("GW25K_EXPECT_DIRECT_OPEN")=="1") {
                        assertFalse(radio!!.dropNextTransfer);assertEquals(1,radio!!.droppedTransfers)
                    }
                    val block=PcmBlock.decode(reply.data!!.payload,limit)
                    assertEquals(rec.boot,block.boot);assertEquals(rec.id,block.recording);assertEquals(transfer,block.transfer)
                    assertEquals(offset,block.offset);assertEquals(n,block.data.size)
                    pcm.seek(offset);pcm.write(block.data);checksum.update(block.data)
                    offset+=n
                    files.persist(rec,pcm,offset,checksum.value)
                    val ack=Writer().u32(transfer).u32(offset).u32(block.crc).build()
                    previousCrc=block.crc
                    if(offset in listOf(limit.toLong(),14720L,29440L)) {
                        s.acknowledgeBlock(transfer,offset,block.crc);previousCrc=null
                    }
                    if(offset==limit.toLong()) s.request(Op.ACK,ack)
                    if(offset==14720L) {s.request(Op.CANCEL,Writer().u32(transfer).build());open()}
                    if(offset==29440L) {
                        session?.close();radio?.close();s=connect()
                        val again=info(s);assertEquals(rec.boot,again.boot);assertEquals(rec.id,again.id);assertEquals(rec.crc,again.crc)
                        val cp=files.recover(rec);assertEquals(offset,cp.offset);assertEquals(checksum.value,cp.prefixCrc)
                        open()
                    }
                    if(offset%16384==0L) println("APP recording download $offset/${rec.bytes}")
                }
            }
            previousCrc?.let{s.acknowledgeBlock(transfer,offset,it)}
            System.getenv("GW25K_EXPECT_ACK_READ")?.let { expected ->
                if(expected=="1")assertTrue(combinedBlocks>(rec.bytes+limit-1)/limit-8) else assertEquals(0,combinedBlocks)
            }
            assertEquals(rec.crc,checksum.value)
            s.request(Op.CLOSE,Writer().u32(transfer).u32(rec.crc).build())
            val saved=files.packageWav(rec,false,"builtin")
            assertEquals("builtin",saved.source);assertEquals(192044L,saved.file.length())
            File(output,"download_result.txt").writeText("boot=${rec.boot.toString(16)}\nrecord=${rec.id}\ncrc=${rec.crc}\nbytes=${rec.bytes}\ndownload_seconds=${(System.nanoTime()-downloadStart)/1e9}\nack_read_blocks=$combinedBlocks\nchunk=$limit\ninjected_offset=$injectedOffset\nwide_open=${System.getenv("GW25K_EXPECT_WIDE_OPEN")}\ninjected_ack_read_response_loss=${injectLoss && System.getenv("GW25K_EXPECT_ACK_READ")=="1" && System.getenv("GW25K_EXPECT_DIRECT_OPEN")!="1"}\ninjected_data_receipt_loss=${injectLoss && System.getenv("GW25K_EXPECT_DIRECT_OPEN")=="1"}\ninjected_fragment_loss=$injectLoss\nfile=${saved.file.absolutePath}\n")
        } finally {session?.close();radio?.close();scope.cancel()}
    }
}
