package cn.gowin.control.protocol

/** A grant is accepted only by REC_FORMATS in the current boot/HELLO session. */
class RecordingFormats private constructor(val mask: Long, private val boot: ULong = 0uL) {
    fun allows(format: Int) = format in 1..2 && mask and (1L shl (format-1)) != 0L
    fun sampleRate(format: Int): Long {
        checkWire(allows(format), "未协商录音格式")
        return if(format==1)48000L else 44100L
    }

    fun validate(info: RecordingInfo, requireReady: Boolean = false) {
        val rate=sampleRate(info.format)
        checkWire(boot==0uL || info.boot==boot, "录音格式授权不属于此启动身份")
        checkWire(info.channels==2 && info.sampleRate==rate, "录音格式与实际采样率不匹配")
        checkWire(info.boot!=0uL && info.state in 0..5 && info.flags and 0xf8==0, "录音状态错误")
        checkWire(info.frames in 0..info.capacity && info.bytes in 0..0xffffffffL && info.bytes==info.frames*4,
            "录音帧数或长度错误")
        checkWire((info.state==0 && info.id==0L && info.bytes==0L && info.crc==0L && info.operation==0L) ||
            (info.state!=0 && info.id in 1..0xffffffffL), "录音对象身份错误")
        checkWire((info.flags and 2!=0)==(info.state==4), "录音 CRC 状态错误")
        checkWire(!requireReady || info.ready, "录音尚未封存")
    }

    companion object {
        const val SUPPORTED_MASK=3L
        val LEGACY=RecordingFormats(1)
        fun requestPayload(): ByteArray = Writer().u16(1).u16(0).u32(SUPPORTED_MASK).build()
        fun decodeResponse(message: Message, boot: ULong): RecordingFormats {
            checkWire(message.opcode==Op.RECORDING_FORMATS && message.status==0 && message.payload.size==16,
                "录音格式协商响应错误")
            val r=Reader(message.payload)
            checkWire(r.u16()==1, "录音格式扩展版本错误");r.zero(2)
            val mask=r.u32()
            checkWire(boot!=0uL && r.u64()==boot, "录音格式协商启动身份错误");r.end()
            checkWire(mask and 1L!=0L && mask and SUPPORTED_MASK==mask, "录音格式协商集合错误")
            return RecordingFormats(mask,boot)
        }
    }
}

/** Reconnect/resume cannot reinterpret the same bytes using a new rate or format. */
fun RecordingInfo.samePcmObject(other: RecordingInfo): Boolean =
    ready && other.ready && boot==other.boot && id==other.id && format==other.format &&
    channels==other.channels && sampleRate==other.sampleRate && frames==other.frames &&
    bytes==other.bytes && capacity==other.capacity && crc==other.crc
