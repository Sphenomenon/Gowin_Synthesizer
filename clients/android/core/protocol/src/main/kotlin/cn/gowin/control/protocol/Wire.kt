package cn.gowin.control.protocol

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID
import java.util.zip.CRC32

object GattIds {
    fun uuid(id: Int): UUID = UUID.fromString("9b6d%04x-4c2a-4f87-9a31-138000000001".format(id))
    val service = uuid(0)
    val capability = uuid(1)
    val command = uuid(2)
    val response = uuid(3)
    val status = uuid(4)
    val transfer = uuid(5)
    val cccd: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
}

class ProtocolException(message: String) : Exception(message)
fun checkWire(condition: Boolean, message: String) { if (!condition) throw ProtocolException(message) }
fun crc32(bytes: ByteArray): Long = CRC32().apply { update(bytes) }.value
fun ByteArray.hex(): String = joinToString("") { "%02x".format(it.toInt() and 255) }
fun hexBytes(value: String): ByteArray {
    val s = value.filterNot(Char::isWhitespace)
    require(s.length % 2 == 0)
    return ByteArray(s.length / 2) { s.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
}

class Writer {
    private val out = java.io.ByteArrayOutputStream()
    fun u8(v: Int) = apply { require(v in 0..255); out.write(v) }
    fun u16(v: Int) = apply { require(v in 0..65535); repeat(2) { out.write(v ushr (it * 8) and 255) } }
    fun u32(v: Long) = apply { require(v in 0..0xffffffffL); repeat(4) { out.write((v ushr (it * 8)).toInt() and 255) } }
    fun u64(v: ULong) = apply { repeat(8) { out.write((v shr (it * 8)).toInt() and 255) } }
    fun bytes(v: ByteArray) = apply { out.write(v) }
    fun build(): ByteArray = out.toByteArray()
}
class Reader(private val bytes: ByteArray) {
    private var pos = 0
    val remaining get() = bytes.size - pos
    fun u8(): Int { checkWire(remaining >= 1, "报文长度不足"); return bytes[pos++].toInt() and 255 }
    fun u16(): Int = u8() or (u8() shl 8)
    fun u32(): Long { var v = 0L; repeat(4) { v = v or (u8().toLong() shl (8 * it)) }; return v }
    fun u64(): ULong { var v = 0uL; repeat(8) { v = v or (u8().toULong() shl (8 * it)) }; return v }
    fun bytes(n: Int): ByteArray { checkWire(n >= 0 && remaining >= n, "报文长度不足"); return bytes.copyOfRange(pos, pos + n).also { pos += n } }
    fun zero(n: Int) { checkWire(bytes(n).all { it == 0.toByte() }, "保留字段非零") }
    fun end() { checkWire(remaining == 0, "报文包含额外数据") }
}

data class Message(val opcode: Int, val status: Int, val requestId: Long, val nonce: ULong, val payload: ByteArray = byteArrayOf()) {
    fun encode(maximum:Int=512): ByteArray {
        require(maximum in setOf(512,1020,8160) && payload.size <= maximum-20 && (payload.size<=492 || opcode==Op.DATA && status==0))
        val body = Writer().u8(opcode).u8(status).u16(payload.size).u32(requestId).u64(nonce).bytes(payload).build()
        return body + Writer().u32(crc32(body)).build()
    }
    companion object {
        fun decode(raw: ByteArray,maximum:Int=512): Message {
            checkWire(maximum in setOf(512,1020,8160),"逻辑报文上限无效")
            checkWire(raw.size in 20..maximum, "逻辑报文大小无效")
            val r = Reader(raw)
            val op = r.u8(); val status = r.u8(); val length = r.u16()
            checkWire(raw.size<=512 || op==Op.DATA && status==0,"仅允许协商后的长音频块")
            val id = r.u32(); val nonce = r.u64()
            checkWire(length == raw.size - 20, "逻辑报文长度不符")
            val payload = r.bytes(length)
            checkWire(r.u32() == crc32(raw.copyOfRange(0, raw.size - 4)), "CRC32 校验失败")
            return Message(op, status, id, nonce, payload)
        }
    }
}

fun fragment(raw: ByteArray, token: Int): List<ByteArray> {
    require(raw.isNotEmpty() && raw.size <= 512 && token in 0..65535)
    return raw.toList().chunked(14).mapIndexed { i, data ->
        val flags = (if (i == 0) 1 else 0) or (if ((i + 1) * 14 >= raw.size) 2 else 0)
        Writer().u8(0xb1).u16(token).u8(i).u8(flags).u8(data.size).bytes(data.toByteArray()).build()
    }
}

/** One instance per notification characteristic; duplicate FIRST must not reset a received prefix. */
class Reassembler(private val allowCompact: Boolean = false,private val bulkValueLimit:Int?=null,private val longData:Boolean=false,private val extendedData:Boolean=false) {
    private var token = -1
    init { require((bulkValueLimit==null || bulkValueLimit in 20..244) && (!(longData || extendedData) || bulkValueLimit!=null)) }
    private var marker = -1
    private var next = 0
    private var lastTime = 0L
    private var previous: ByteArray? = null
    private val buffer = java.io.ByteArrayOutputStream()
    fun clear() { token = -1; marker = -1; next = 0; buffer.reset(); previous = null }
    fun accept(value: ByteArray, nowMs: Long): ByteArray? {
        try {
            checkWire(value.size in 5..(bulkValueLimit?:20), "分片长度错误")
            val r = Reader(value)
            val version = r.u8()
            val bulk = version == 0xb3
            val compact = version == 0xb2 || bulk
            checkWire(version == 0xb1 || version == 0xb2 && allowCompact || bulk && bulkValueLimit!=null, "未协商的分片版本")
            val t = r.u16()
            val tag = r.u8()
            val index = if (compact) tag and 63 else tag
            val flags = if (compact) tag ushr 6 else r.u8()
            val length = if (compact) r.remaining else r.u8()
            checkWire(value.size <= if(bulk)bulkValueLimit!! else 20,"分片超过协商通知长度")
            val capacity = if(bulk)bulkValueLimit!!-4 else if (compact) 16 else 14
            val maxIndex = if(bulk && (longData || extendedData))63 else if (compact) 31 else 36
            checkWire(flags and 0xfc == 0 && length in 1..capacity && r.remaining == length, "分片字段错误")
            checkWire((flags and 1 != 0) == (index == 0), "FIRST 标志错误")
            checkWire(flags and 2 != 0 || length == capacity, "中间分片过短")
            checkWire(index <= maxIndex, "分片编号超出上限")
            if (token != -1 && nowMs - lastTime > 2000) clear()
            if (t == token && index == next - 1 && previous?.contentEquals(value) == true) return null
            if (t == token && index == next - 1) checkWire(previous?.contentEquals(value) == true, "重复分片内容冲突")
            if (flags and 1 != 0) { clear(); token = t; marker = version }
            checkWire(t == token && index == next && marker == version, "分片顺序错误")
            buffer.write(r.bytes(length)); checkWire(buffer.size() <= if(bulk && extendedData)minOf(8160,(bulkValueLimit!!-4)*64) else if(bulk && longData)1020 else 512, "重组超出上限")
            previous = value.copyOf(); next++; lastTime = nowMs
            if (flags and 2 != 0) return buffer.toByteArray().also { clear() }
            return null
        } catch (e: Exception) { clear(); throw e }
    }
}

fun isNewerSequence(candidate: Long, previous: Long): Boolean = ((candidate - previous) and 0xffffffffL) in 1..0x7fffffffL

object Op {
    const val HELLO = 1; const val STATUS = 2; const val SUBSCRIBE = 3; const val OPERATION = 4
    const val GET_PARAM = 0x10; const val SET_PARAM = 0x11; const val GET_EFFECTS = 0x12; const val SET_EFFECTS = 0x13
    const val START = 0x20; const val STOP = 0x21; const val INFO = 0x22; const val CLEAR = 0x23
    const val OPEN = 0x30; const val READ = 0x31; const val ACK = 0x32; const val CLOSE = 0x33; const val CANCEL = 0x34
    const val ACK_READ = 0x35 // Optional extension; UNSUPPORTED falls back to ACK + READ.
    const val OPEN_WIDE = 0x36 // Optional 460-byte transfer; legacy OPEN remains 256.
    const val OPEN_COMPACT = 0x37 // Optional B2 DATA framing, 460-byte blocks.
    const val OPEN_SECOND = 0x40 // Opt-in codec0/10/11; best per-block predictor.
    const val READ_SECOND = 0x41; const val ACK_READ_SECOND = 0x42
    const val OPEN_LOSSLESS = 0x3d // Explicit DATA codec0/10; same PCM limits as3c.
    const val READ_LOSSLESS = 0x3e; const val ACK_READ_LOSSLESS = 0x3f
    const val OPEN_EXTENDED = 0x3c // Explicit MTU-bound DATA, PCM up to8112.
    const val OPEN_LONG = 0x3b // Optional B3 DATA-only logical1020 / PCM972.
    const val OPEN_DIRECT = 0x39 // Optional B3 DATA as successful READ/ACK_READ receipt.
    const val OPEN_BULK = 0x38 // Optional B3 DATA using negotiated ATT value length.
    const val DATA = 0xd0; const val TASK_EVENT = 0xe0; const val STATUS_EVENT = 0xe1
}

class DeviceError(val code: Int, val revision: Long = 0) : Exception(when (code) {
    0x80 -> "设备尚未支持此功能"; 0x81 -> "设备拒绝了参数"; 0x82 -> "设备忙，请稍后重试"
    0x83 -> "设备当前状态不允许此操作"; 0x84 -> "设置已被其他控制端更新，请刷新"
    0x85 -> "连接会话已失效，请重新连接"; 0x86 -> "请求编号冲突，请重新连接"
    0x87 -> "请求已过期，请重新连接并恢复"; 0x88 -> "设备端录音已失效"
    0x89 -> "录音读取范围无效"; 0x8a -> "设备存储错误"; 0x8b -> "设备操作超时"
    0x8c -> "请在设备上开启蓝牙控制窗口"; 0x8d -> "下载确认状态冲突"
    else -> "设备错误 0x%02X".format(code)
})

fun Message.checked(): Message {
    if (status >= 0x80) {
        checkWire(payload.size == 8, "错误响应长度无效")
        val r = Reader(payload); r.u16(); r.zero(2)
        throw DeviceError(status, r.u32())
    }
    checkWire(status in 0..2, "未知业务状态")
    return this
}
