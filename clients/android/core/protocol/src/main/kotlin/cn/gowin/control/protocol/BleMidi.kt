package cn.gowin.control.protocol

import java.util.UUID

/** Existing GW25K BLE MIDI profile: one complete event per ATT value, no running status. */
object BleMidi {
    val service: UUID = UUID.fromString("03b80e5a-ede8-4b33-a751-6ce34ec4c700")
    val characteristic: UUID = UUID.fromString("7772e5db-3868-4112-a1a9-f2669d106bf3")
    val cccd: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

    fun noteOn(channel: Int, note: Int, velocity: Int): ByteArray {
        require(velocity in 1..127)
        return message(0x90, channel, note, velocity)
    }
    fun noteOff(channel: Int, note: Int): ByteArray = message(0x80, channel, note, 0)
    fun panic(): List<ByteArray> = (0..15).flatMap { channel ->
        listOf(message(0xb0, channel, 120, 0), message(0xb0, channel, 123, 0))
    }
    private fun message(status: Int, channel: Int, first: Int, second: Int): ByteArray {
        require(channel in 0..15 && first in 0..127 && second in 0..127)
        return byteArrayOf((status or channel).toByte(), first.toByte(), second.toByte())
    }
    fun packet(message: ByteArray, timeMillis: Long): ByteArray {
        require(message.size == 3)
        val status = message[0].toInt() and 255
        require(status and 0xf0 in listOf(0x80, 0x90, 0xb0))
        require(message.drop(1).all { it.toInt() and 0x80 == 0 })
        val timestamp = (timeMillis and 0x1fff).toInt()
        return byteArrayOf((0x80 or (timestamp shr 7)).toByte(), (0x80 or (timestamp and 127)).toByte()) + message
    }
}
