package cn.gowin.control.protocol

/** OPEN_BULK adds an explicit DATA-only ATT value limit after the original fields. */
data class TransferOpen(val transfer:Long,val bytes:Long,val crc:Long,val offset:Long,
                        val maxChunk:Int,val valueLimit:Int) {
    companion object {
        fun decode(message:Message):TransferOpen {
            val bulk=message.opcode in setOf(Op.OPEN_BULK,Op.OPEN_DIRECT,Op.OPEN_LONG,Op.OPEN_EXTENDED,Op.OPEN_LOSSLESS,Op.OPEN_SECOND)
            checkWire(message.opcode in setOf(Op.OPEN,Op.OPEN_WIDE,Op.OPEN_COMPACT,Op.OPEN_BULK,Op.OPEN_DIRECT,Op.OPEN_LONG,Op.OPEN_EXTENDED,Op.OPEN_LOSSLESS,Op.OPEN_SECOND),"下载打开响应类型错误")
            checkWire(message.payload.size==if(bulk)24 else 20,"下载会话长度错误")
            val r=Reader(message.payload)
            val id=r.u32();val bytes=r.u32();val crc=r.u32();val offset=r.u32();val chunk=r.u16();val window=r.u8();r.zero(1)
            val value=if(bulk)r.u16() else 20
            if(bulk)r.zero(2)
            r.end()
            checkWire(id!=0L && chunk in 4..(if(message.opcode in setOf(Op.OPEN_EXTENDED,Op.OPEN_LOSSLESS,Op.OPEN_SECOND))minOf(8112,(value-4)*64-48) else if(message.opcode==Op.OPEN_LONG)972 else if(message.opcode==Op.OPEN)256 else 460) && chunk%4==0 && window==1,"下载能力错误")
            checkWire(value in 20..244,"下载通知长度无效")
            return TransferOpen(id,bytes,crc,offset,chunk,value)
        }
    }
}

data class Capability(val boot: ULong, val flags: Long, val maxChunk: Int, val window: Int, val recordingSlots: Int = 1) {
    val protocolTestOnly get() = flags == 0L && maxChunk == 0 && recordingSlots == 0
    fun has(bit: Int) = flags and (1L shl bit) != 0L
    companion object {
        fun decode(raw: ByteArray): Capability {
            checkWire(raw.size == 20, "能力报文长度错误")
            val r = Reader(raw)
            checkWire(r.u8() == 1 && r.u8() == 20 && r.u16() == 512, "设备协议版本不兼容")
            val boot = r.u64(); val flags = r.u32(); val chunk = r.u16(); val window = r.u8(); val slots = r.u8()
            val records = flags and 0x18L != 0L
            val downloads = flags and 0x20L != 0L
            checkWire(boot != 0uL && flags and 0xffffff00L == 0L && window == 1, "设备能力字段无效")
            checkWire(slots in 0..1 && (!records || slots == 1), "录音槽能力无效")
            checkWire((chunk == 0 && !downloads) || (chunk in 4..256 && chunk % 4 == 0), "PCM 块能力无效")
            checkWire(!downloads || slots == 1, "下载能力缺少录音槽")
            return Capability(boot, flags, chunk, window, slots)
        }
    }
}
data class Snapshot(
    val id: Long = 0, val time: Long = 0, val valid: Long = 0, val revision: Long = 1,
    val requestedMode: Int = 2, val mode: Int = 2, val profile: Int = 0, val volume: Int = 100,
    val route: Int = 0, val effectsEnabled: Boolean = false, val effects: List<Int> = emptyList(),
    val voices: Int = 0, val recordState: Int = 0, val recordId: Long = 0, val frames: Long = 0,
    val capacity: Long = 0, val leftPeak: Int = 0, val rightPeak: Int = 0, val flags: Long = 0,
    val deadline: Long = 0, val underrun: Long = 0, val noteDrop: Long = 0, val recordDrop: Long = 0
) {
    fun valid(bit: Int) = valid and (1L shl bit) != 0L
    companion object {
        fun decode(bytes: ByteArray): Snapshot {
            checkWire(bytes.size == 64, "状态报文长度错误")
            val r = Reader(bytes)
            val id = r.u32(); val time = r.u32(); val valid = r.u32(); val rev = r.u32()
            val requested = r.u8(); val mode = r.u8(); val profile = r.u8(); val volume = r.u8()
            val route = r.u8(); val enabled = r.u8(); val count = r.u8(); val chain = List(3) { r.u8() }
            checkWire(count <= 3 && enabled <= 1 && valid and 0xffffffe0L == 0L, "状态字段错误")
            if(valid and 1L!=0L) {
                checkWire(requested in 0..2 && mode in 0..2 && profile in 0..4 && volume<=127 && route<=3,"设置状态字段错误")
                checkWire(chain.take(count).all{it in 0..2} && chain.take(count).distinct().size==count && chain.drop(count).all{it==255},"效果顺序字段错误")
            }
            val voices = r.u8(); val state = r.u8(); val recordId = r.u32(); val frames = r.u32(); val cap = r.u32()
            val l = r.u16(); val rr = r.u16(); val flags = r.u32()
            return Snapshot(id,time,valid,rev,requested,mode,profile,volume,route,enabled==1,chain.take(count),voices,state,recordId,frames,cap,l,rr,flags,r.u32(),r.u32(),r.u32(),r.u32())
        }
    }
    fun encode(): ByteArray = Writer().u32(id).u32(time).u32(valid).u32(revision).u8(requestedMode).u8(mode).u8(profile).u8(volume)
        .u8(route).u8(if(effectsEnabled) 1 else 0).u8(effects.size).bytes(ByteArray(3) { effects.getOrElse(it) { 255 }.toByte() })
        .u8(voices).u8(recordState).u32(recordId).u32(frames).u32(capacity).u16(leftPeak).u16(rightPeak).u32(flags)
        .u32(deadline).u32(underrun).u32(noteDrop).u32(recordDrop).build()
}
data class RecordingInfo(
    val boot: ULong, val id: Long, val state: Int, val format: Int, val channels: Int, val flags: Int,
    val sampleRate: Long, val frames: Long, val bytes: Long, val capacity: Long, val crc: Long,
    val reason: Int, val detail: Int, val operation: Long
) {
    val ready get() = state == 4 && flags and 2 != 0
    val incomplete get() = flags and 1 != 0
    companion object {
        fun decode(raw: ByteArray): RecordingInfo {
            checkWire(raw.size == 48, "录音信息长度错误")
            val r=Reader(raw)
            val info=RecordingInfo(r.u64(),r.u32(),r.u8(),r.u8(),r.u8(),r.u8(),r.u32(),r.u32(),r.u32(),r.u32(),r.u32(),r.u16(),r.u16(),r.u32())
            r.zero(4); checkWire(info.state in 0..5 && info.flags and 0xf8 == 0, "录音状态错误")
            return info
        }
    }
    fun encode(): ByteArray = Writer().u64(boot).u32(id).u8(state).u8(format).u8(channels).u8(flags).u32(sampleRate).u32(frames)
        .u32(bytes).u32(capacity).u32(crc).u16(reason).u16(detail).u32(operation).u32(0).build()
}
data class PcmBlock(val transfer: Long, val boot: ULong, val recording: Long, val offset: Long, val crc: Long, val data: ByteArray) {
    companion object {
        fun decode(raw: ByteArray,maxChunk: Int=256,allowLossless:Boolean=false,allowSecond:Boolean=false): PcmBlock {
            checkWire(maxChunk in 4..8112 && maxChunk%4==0,"PCM 块上限无效")
            val r=Reader(raw); val transfer=r.u32(); val boot=r.u64(); val rec=r.u32(); val offset=r.u32(); val n=r.u16(); val codec=r.u8(); r.zero(1); val crc=r.u32()
            checkWire(n in 4..maxChunk && n%4==0 && offset%4==0L, "PCM 数据块长度错误")
            checkWire(codec==0 || allowLossless && codec==10 || allowLossless && allowSecond && codec==11,"未协商 PCM 编码")
            val data=PcmRice.decode(r.bytes(r.remaining),n,codec,allowSecond); checkWire(crc32(data)==crc,"PCM 块校验失败")
            return PcmBlock(transfer,boot,rec,offset,crc,data)
        }
    }
}
