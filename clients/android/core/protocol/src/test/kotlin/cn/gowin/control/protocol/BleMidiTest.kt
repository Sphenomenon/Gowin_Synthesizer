package cn.gowin.control.protocol

import org.junit.Assert.*
import org.junit.Test

class BleMidiTest {
    @Test fun exactExisting25kValueAndTimestampRollover() {
        assertArrayEquals(byteArrayOf(0x80.toByte(), 0x80.toByte(), 0x90.toByte(), 48, 100),
            BleMidi.packet(BleMidi.noteOn(0, 48, 100), 8192))
        assertArrayEquals(byteArrayOf(0xbf.toByte(), 0xff.toByte(), 0x8f.toByte(), 63, 0),
            BleMidi.packet(BleMidi.noteOff(15, 63), 8191))
    }
    @Test fun panicClearsEveryChannelWithoutBatching() {
        val events = BleMidi.panic()
        assertEquals(32, events.size)
        (0..15).forEach { channel ->
            assertArrayEquals(byteArrayOf((0xb0 or channel).toByte(), 120, 0), events[channel * 2])
            assertArrayEquals(byteArrayOf((0xb0 or channel).toByte(), 123, 0), events[channel * 2 + 1])
            assertEquals(5, BleMidi.packet(events[channel * 2], 0).size)
        }
    }
    @Test(expected = IllegalArgumentException::class) fun rejectZeroNoteOnVelocity() { BleMidi.noteOn(0, 48, 0) }
    @Test(expected = IllegalArgumentException::class) fun rejectBatchedMessages() { BleMidi.packet(byteArrayOf(0x90.toByte(), 48, 100, 0x80.toByte(), 48, 0), 0) }
}
