package cn.gowin.control.data

import cn.gowin.control.protocol.*
import org.junit.Assert.*
import org.junit.Test
import java.io.RandomAccessFile
import java.nio.file.Files

class RecordingFilesTest {
    private val pcm=ByteArray(1024){(it*17).toByte()}
    private fun info()=RecordingInfo(ULong.MAX_VALUE,1,4,1,2,2,48000,256,1024,48000,crc32(pcm),1,0,1)
    @Test fun checkpointRecoveryTruncatesUnsavedTailAndPackagesValidWav() {
        val root=Files.createTempDirectory("recording-test").toFile()
        try {
            val files=RecordingFiles(root);val info=info()
            assertEquals(0,files.recover(info).offset)
            RandomAccessFile(files.part(info),"rw").use{
                it.write(pcm,0,256);files.persist(info,it,256,crc32(pcm.copyOfRange(0,256)))
                it.write(ByteArray(100)) // Simulates crash after a write, before checkpoint publication.
            }
            assertEquals(256,files.recover(info).offset);assertEquals(256,files.part(info).length())
            RandomAccessFile(files.part(info),"rw").use{it.seek(256);it.write(pcm,256,768);files.persist(info,it,1024,crc32(pcm))}
            val saved=files.packageWav(info,false)
            assertEquals(1068,saved.file.length());assertEquals(info.crc,RecordingFiles.fileCrc(saved.file,44,1024))
            val r=Reader(saved.file.readBytes().copyOfRange(0,44))
            assertEquals("RIFF",String(r.bytes(4)));assertEquals(1060,r.u32());assertEquals("WAVEfmt ",String(r.bytes(8)))
            assertEquals(16,r.u32());assertEquals(1,r.u16());assertEquals(2,r.u16());assertEquals(48000,r.u32())
            assertEquals(192000,r.u32());assertEquals(4,r.u16());assertEquals(16,r.u16());assertEquals("data",String(r.bytes(4)));assertEquals(1024,r.u32())
            files.rename(saved,"测试作品");assertEquals("测试作品",files.library().single().name)
            files.delete(saved);assertTrue(files.library().isEmpty())
        } finally {root.deleteRecursively()}
    }
    @Test fun corruptPrefixCannotBeAcknowledgedAfterRestart() {
        val root=Files.createTempDirectory("recording-corruption").toFile()
        try {
            val files=RecordingFiles(root);val info=info()
            RandomAccessFile(files.part(info),"rw").use{it.write(pcm);files.persist(info,it,1024,crc32(pcm));it.seek(0);it.write(127)}
            assertEquals(0,files.recover(info).offset)
            assertThrows(IllegalStateException::class.java){files.packageWav(info,false)}
        }finally{root.deleteRecursively()}
    }
    @Test fun negotiated44100WavUsesActualRateAndRejectsUnnegotiatedPackaging() {
        val root=Files.createTempDirectory("recording-44100").toFile()
        try {
            val files=RecordingFiles(root);val info=info().copy(format=2,sampleRate=44100)
            RandomAccessFile(files.part(info),"rw").use{it.write(pcm)}
            assertThrows(ProtocolException::class.java){files.packageWav(info,false)}
            val formats=RecordingFormats.decodeResponse(Message(Op.RECORDING_FORMATS,0,2,1uL,
                Writer().u16(1).u16(0).u32(3).u64(info.boot).build()),info.boot)
            val saved=files.packageWav(info,false,formats=formats)
            val r=Reader(saved.file.readBytes().copyOfRange(24,44))
            assertEquals(44100,r.u32());assertEquals(176400,r.u32());assertEquals(4,r.u16());assertEquals(16,r.u16())
            assertEquals("data",String(r.bytes(4)));assertEquals(info.bytes,r.u32())
            assertEquals(44100,saved.sampleRate);assertEquals(44100,files.library().single().sampleRate)
            assertEquals(info.crc,RecordingFiles.fileCrc(saved.file,44,info.bytes))
        }finally{root.deleteRecursively()}
    }
    @Test fun changedFormatOrRateCannotResumeAnOldDurablePrefix() {
        val root=Files.createTempDirectory("recording-format-identity").toFile()
        try {
            val files=RecordingFiles(root);val original=info()
            RandomAccessFile(files.part(original),"rw").use{it.write(pcm);files.persist(original,it,1024,crc32(pcm))}
            assertEquals(0,files.recover(original.copy(format=2,sampleRate=44100)).offset)
            assertEquals(0,files.part(original).length())
        }finally{root.deleteRecursively()}
    }
}
