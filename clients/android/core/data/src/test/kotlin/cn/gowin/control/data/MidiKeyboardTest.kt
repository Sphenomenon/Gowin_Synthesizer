package cn.gowin.control.data

import cn.gowin.control.ble.FoundDevice
import cn.gowin.control.ble.MidiTransport
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MidiKeyboardTest {
    private class Fake : MidiTransport {
        override val connected = MutableStateFlow(false)
        override val devices = MutableStateFlow<List<FoundDevice>>(emptyList())
        val sent = mutableListOf<ByteArray>()
        override fun startScan(onError: (String) -> Unit) {}
        override fun stopScan() {}
        override suspend fun connect(address: String) { connected.value = true }
        override suspend fun send(packet: ByteArray) { check(connected.value); sent += packet.copyOf() }
        override fun close() { connected.value = false }
    }
    @Test fun heldPressReleaseAndCleanDisconnect() = runTest {
        val link = Fake()
        val keyboard = MidiKeyboard(link, backgroundScope) { 0 }
        keyboard.connect("test", "GWK-MIDI"); runCurrent()
        assertTrue(keyboard.state.value.ready)
        assertEquals(32, link.sent.size)
        keyboard.setVelocity(77)
        keyboard.noteOn(48); keyboard.noteOn(48); runCurrent()
        assertEquals(setOf(48), keyboard.state.value.heldNotes)
        assertArrayEquals(byteArrayOf(0x80.toByte(), 0x80.toByte(), 0x90.toByte(), 48, 77), link.sent.last())
        assertEquals(33, link.sent.size)
        keyboard.noteOff(48); runCurrent()
        assertEquals(0x80, link.sent.last()[2].toInt() and 255)
        assertTrue(keyboard.state.value.heldNotes.isEmpty())
        keyboard.disconnect(); runCurrent()
        assertFalse(link.connected.value)
        assertEquals(66, link.sent.size)
    }
    @Test fun panicDropsQueuedPressesAndDisconnectNeverReplays() = runTest {
        val link = Fake()
        val keyboard = MidiKeyboard(link, backgroundScope) { 0 }
        keyboard.connect("test", "GWK-MIDI"); runCurrent(); link.sent.clear()
        keyboard.noteOn(50)
        keyboard.panic(); runCurrent()
        assertEquals(32, link.sent.size)
        assertTrue(link.sent.all { it[2].toInt() and 0xf0 == 0xb0 })
        keyboard.noteOn(51); runCurrent()
        link.connected.value = false; runCurrent()
        assertFalse(keyboard.state.value.ready)
        assertTrue(keyboard.state.value.heldNotes.isEmpty())
        keyboard.connect("test", "GWK-MIDI"); runCurrent()
        assertTrue(keyboard.state.value.ready)
        assertTrue(link.sent.takeLast(32).all { it[2].toInt() and 0xf0 == 0xb0 })
    }
    @Test fun changingChannelCleansPreviousHeldNotes() = runTest {
        val link = Fake()
        val keyboard = MidiKeyboard(link, backgroundScope) { 0 }
        keyboard.connect("test", "GWK-MIDI"); runCurrent()
        keyboard.noteOn(48); runCurrent()
        keyboard.setChannel(3); runCurrent()
        assertTrue(keyboard.state.value.heldNotes.isEmpty())
        keyboard.noteOn(48); runCurrent()
        assertEquals(0x93, link.sent.last()[2].toInt() and 255)
    }
}
