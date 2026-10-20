package cn.gowin.control.data

import cn.gowin.control.protocol.*
import cn.gowin.control.protocol.Writer
import java.io.*
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.Properties
import java.util.zip.CRC32

data class SavedRecording(val key: String,val name: String,val file: File,val bytes: Long,val savedAt: Long,val incomplete: Boolean,val demo: Boolean,val source: String=if(demo)"demo"else"workstation")
data class DownloadCheckpoint(val offset: Long,val prefixCrc: Long)

/** File bytes are synced before checkpoint publication; checkpoint is authoritative, not UI state. */
class RecordingFiles(private val root: File) {
    private val downloads=File(root,"downloads").apply{mkdirs()}
    private val recordings=File(root,"recordings").apply{mkdirs()}
    fun key(info: RecordingInfo)=info.boot.toString(16).padStart(16,'0')+"_"+info.id
    fun taskDir(info: RecordingInfo)=File(downloads,key(info)).apply{mkdirs()}
    fun part(info: RecordingInfo)=File(taskDir(info),"audio.pcm.part")
    private fun checkpoint(info: RecordingInfo)=File(taskDir(info),"checkpoint.properties")
    private fun identity(info: RecordingInfo)=Properties().apply {
        setProperty("version","1");setProperty("boot",info.boot.toString(16));setProperty("record",info.id.toString())
        setProperty("bytes",info.bytes.toString());setProperty("crc",info.crc.toString());setProperty("rate",info.sampleRate.toString())
        setProperty("channels",info.channels.toString());setProperty("format",info.format.toString())
    }
    fun recover(info: RecordingInfo): DownloadCheckpoint {
        val file=part(info);val manifest=checkpoint(info)
        if(!manifest.exists()) { RandomAccessFile(file,"rw").use{it.setLength(0)};return DownloadCheckpoint(0,0) }
        return try {
            val p=load(manifest)
            check(identity(info).entries.all{p[it.key]==it.value}){"录音身份或格式改变，旧临时文件不能续传"}
            val offset=p.getProperty("offset").toLong();val crc=p.getProperty("prefixCrc").toLong()
            check(offset in 0..info.bytes && offset%4==0L && file.length()>=offset)
            check(fileCrc(file,0,offset)==crc)
            RandomAccessFile(file,"rw").use{it.setLength(offset)}
            DownloadCheckpoint(offset,crc)
        } catch(e: Exception) {
            // Preserve mismatched objects for diagnosis; reset only the untrusted partial prefix.
            manifest.delete();RandomAccessFile(file,"rw").use{it.setLength(0)}
            DownloadCheckpoint(0,0)
        }
    }
    fun persist(info: RecordingInfo,file: RandomAccessFile,offset: Long,prefixCrc: Long) {
        require(offset in 0..info.bytes && offset%4==0L && file.length()>=offset)
        file.fd.sync()
        val p=identity(info).apply { setProperty("offset",offset.toString());setProperty("prefixCrc",prefixCrc.toString()) }
        atomicProperties(checkpoint(info),p)
    }
    fun discard(info: RecordingInfo) { taskDir(info).deleteRecursively() }
    fun packageWav(info: RecordingInfo,demo: Boolean,source: String=if(demo)"demo"else"workstation"): SavedRecording {
        val pcm=part(info)
        check(pcm.length()==info.bytes && fileCrc(pcm)==info.crc){"完整 PCM 校验失败"}
        check(info.bytes<=0xffffffffL-36 && info.format==1 && info.channels==2 && info.sampleRate==48000L && info.bytes==info.frames*4)
        val key=key(info);val tmp=File(recordings,"$key.wav.part");val target=File(recordings,"$key.wav")
        FileOutputStream(tmp).use { out ->
            out.write(wavHeader(info.bytes));pcm.inputStream().use{it.copyTo(out)};out.fd.sync()
        }
        check(tmp.length()==44+info.bytes && fileCrc(tmp,44,info.bytes)==info.crc){"WAV 文件校验失败"}
        atomicMove(tmp,target)
        val saved=System.currentTimeMillis()
        atomicProperties(File(recordings,"$key.properties"),Properties().apply {
            setProperty("name",(if(source=="builtin")"内置测试录音 "else if(demo)"模拟录音 " else "工作站录音 ")+info.id)
            setProperty("saved",saved.toString());setProperty("bytes",info.bytes.toString())
            setProperty("incomplete",info.incomplete.toString());setProperty("demo",demo.toString());setProperty("source",source)
        })
        return library().first{it.key==key}
    }
    fun library(): List<SavedRecording> = recordings.listFiles().orEmpty().filter{it.extension=="properties"}.mapNotNull { meta ->
        runCatching {
            val p=load(meta);val wav=File(recordings,"${meta.nameWithoutExtension}.wav")
            val size=p.getProperty("bytes").toLong();check(wav.length()==size+44)
            SavedRecording(meta.nameWithoutExtension,p.getProperty("name"),wav,size,p.getProperty("saved").toLong(),p.getProperty("incomplete").toBoolean(),p.getProperty("demo").toBoolean(),p.getProperty("source",if(p.getProperty("demo").toBoolean())"demo"else"workstation"))
        }.getOrNull()
    }.sortedByDescending{it.savedAt}
    fun rename(entry: SavedRecording,name: String) {
        require(name.isNotBlank() && name.length<=80)
        val f=File(recordings,"${entry.key}.properties");val p=load(f);p.setProperty("name",name.trim());atomicProperties(f,p)
    }
    fun delete(entry: SavedRecording) { entry.file.delete();File(recordings,"${entry.key}.properties").delete() }
    companion object {
        fun fileCrc(file: File,offset: Long=0,length: Long=file.length()-offset): Long {
            require(offset>=0&&length>=0&&offset+length<=file.length())
            val crc=CRC32()
            RandomAccessFile(file,"r").use { f ->
                f.seek(offset);var remaining=length;val buf=ByteArray(32768)
                while(remaining>0) { val n=f.read(buf,0,minOf(buf.size.toLong(),remaining).toInt());check(n>0);crc.update(buf,0,n);remaining-=n }
            }
            return crc.value
        }
        fun wavHeader(bytes: Long): ByteArray {
            require(bytes in 0..0xffffffffL-36 && bytes%4==0L)
            return Writer().bytes("RIFF".toByteArray()).u32(36+bytes).bytes("WAVEfmt ".toByteArray()).u32(16)
                .u16(1).u16(2).u32(48000).u32(192000).u16(4).u16(16).bytes("data".toByteArray()).u32(bytes).build()
        }
        private fun load(file: File)=Properties().apply{file.inputStream().use{load(it)}}
        private fun atomicProperties(file: File,p: Properties) {
            val tmp=File(file.parentFile,file.name+".new")
            FileOutputStream(tmp).use { p.store(it,null);it.fd.sync() }
            atomicMove(tmp,file)
        }
        private fun atomicMove(from: File,to: File) {
            try { Files.move(from.toPath(),to.toPath(),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING) }
            catch(_: java.nio.file.AtomicMoveNotSupportedException) { Files.move(from.toPath(),to.toPath(),StandardCopyOption.REPLACE_EXISTING) }
        }
    }
}
