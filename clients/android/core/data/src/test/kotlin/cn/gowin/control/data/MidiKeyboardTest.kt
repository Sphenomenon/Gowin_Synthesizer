package cn.gowin.control.data

import cn.gowin.control.ble.FoundDevice
import cn.gowin.control.ble.MidiTransport
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MidiKeyboardTest {
    private class Fake : MidiTransport {
        override val connected = MutableStateFlow(false)
        override val devices = MutableStateFlow<List<FoundDevice>>(emptyList())
        override val connectionProgress = MutableStateFlow<String?>(null)
        var connectGate: CompletableDeferred<Unit>? = null
        var connectCalls = 0
        var closeCalls = 0
        var scanning = false
        var sendError: Exception? = null
        val sent = mutableListOf<ByteArray>()
        override fun startScan(onError: (String) -> Unit) { scanning = true }
        override fun stopScan() { scanning = false }
        override suspend fun connect(address: String) { connectCalls++; connectGate?.await(); connected.value = true }
        override suspend fun send(packet: ByteArray) { sendError?.let { throw it }; check(connected.value); sent += packet.copyOf() }
        override fun close() { closeCalls++; connected.value = false }
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
    @Test fun recoveryKeepsKeysDisabledUntilConnectedAndPanicComplete() = runTest {
        val link = Fake().apply { connectGate = CompletableDeferred() }
        val keyboard = MidiKeyboard(link, backgroundScope) { 0 }
        keyboard.connect("test", "GWK-MIDI"); runCurrent()
        link.connectionProgress.value = "系统已清除旧配对，正在自动重连（仅一次）…"
        runCurrent()
        assertTrue(keyboard.state.value.connecting)
        assertFalse(keyboard.state.value.ready)
        assertTrue(keyboard.state.value.connectionProgress!!.contains("自动重连"))
        keyboard.noteOn(48); runCurrent()
        assertTrue(link.sent.isEmpty())
        link.connectGate!!.complete(Unit); runCurrent()
        assertTrue(keyboard.state.value.ready)
        assertEquals(32, link.sent.size)
        assertTrue(link.sent.all { it[2].toInt() and 0xf0 == 0xb0 })
        assertTrue(keyboard.state.value.heldNotes.isEmpty())
    }
    @Test fun leavingControlsStopsNotesAndScanningWithoutClosingConnection() = runTest {
        val link = Fake()
        val keyboard = MidiKeyboard(link, backgroundScope) { 0 }
        keyboard.connect("test", "GWK-MIDI"); runCurrent()
        val closesBeforeLeaving = link.closeCalls
        keyboard.scan()
        keyboard.noteOn(48); runCurrent()
        link.sent.clear()
        keyboard.noteOn(49)
        keyboard.releaseControls(); runCurrent()
        assertFalse(link.scanning)
        assertTrue(link.connected.value)
        assertTrue(keyboard.state.value.ready)
        assertTrue(keyboard.state.value.active)
        assertTrue(keyboard.state.value.heldNotes.isEmpty())
        assertEquals(closesBeforeLeaving, link.closeCalls)
        assertEquals(32, link.sent.size)
        assertTrue(link.sent.all { it[2].toInt() and 0xf0 == 0xb0 })
    }
    @Test fun returningToControlsPlaysNewNotesWithoutReconnectOrOldNoteReplay() = runTest {
        val link = Fake()
        val keyboard = MidiKeyboard(link, backgroundScope) { 0 }
        keyboard.connect("test", "GWK-MIDI"); runCurrent()
        keyboard.noteOn(48); runCurrent()
        keyboard.releaseControls(); runCurrent(); link.sent.clear()
        keyboard.noteOn(52); keyboard.noteOff(52); runCurrent()
        assertEquals(1, link.connectCalls)
        assertEquals(2, link.sent.size)
        assertEquals(52, link.sent.first()[3].toInt())
        assertEquals(0x90, link.sent.first()[2].toInt() and 255)
        assertEquals(0x80, link.sent.last()[2].toInt() and 255)
        assertTrue(keyboard.state.value.ready)
    }
    @Test fun leavingDuringConnectDoesNotCancelConnectionAttempt() = runTest {
        val link = Fake().apply { connectGate = CompletableDeferred() }
        val keyboard = MidiKeyboard(link, backgroundScope) { 0 }
        keyboard.connect("test", "GWK-MIDI"); runCurrent()
        val closesBeforeLeaving = link.closeCalls
        keyboard.releaseControls(); runCurrent()
        assertTrue(keyboard.state.value.connecting)
        assertTrue(keyboard.state.value.active)
        assertEquals(closesBeforeLeaving, link.closeCalls)
        link.connectGate!!.complete(Unit); runCurrent()
        assertTrue(keyboard.state.value.ready)
        assertTrue(link.connected.value)
        assertEquals(1, link.connectCalls)
        assertEquals(32, link.sent.size)
    }
    @Test fun repeatedLifecycleCleanupKeepsTheSameConnection() = runTest {
        val link = Fake()
        val keyboard = MidiKeyboard(link, backgroundScope) { 0 }
        keyboard.connect("test", "GWK-MIDI"); runCurrent()
        val closesBeforeLeaving = link.closeCalls
        repeat(3) { keyboard.releaseControls(); runCurrent() }
        assertTrue(keyboard.state.value.ready)
        assertTrue(link.connected.value)
        assertEquals(closesBeforeLeaving, link.closeCalls)
        assertEquals(1, link.connectCalls)
    }
    @Test fun explicitDisconnectStaysActiveUntilCleanupCompletes() = runTest {
        val link = Fake()
        val keyboard = MidiKeyboard(link, backgroundScope) { 0 }
        keyboard.connect("test", "GWK-MIDI"); runCurrent(); link.sent.clear()
        keyboard.disconnect()
        assertFalse(keyboard.state.value.ready)
        assertTrue(keyboard.state.value.disconnecting)
        assertTrue(keyboard.state.value.active)
        assertTrue(link.connected.value)
        keyboard.releaseControls()
        keyboard.disconnect()
        runCurrent()
        assertEquals(32, link.sent.size)
        assertFalse(link.connected.value)
        assertFalse(keyboard.state.value.disconnecting)
        assertFalse(keyboard.state.value.active)
    }
    @Test fun cleanupSendFailureIsReportedInsteadOfClaimingTheConnectionSurvives() = runTest {
        val link = Fake()
        val keyboard = MidiKeyboard(link, backgroundScope) { 0 }
        keyboard.connect("test", "GWK-MIDI"); runCurrent()
        link.sendError = IllegalStateException("GATT write failed")
        keyboard.releaseControls(); runCurrent()
        assertFalse(link.connected.value)
        assertFalse(keyboard.state.value.active)
        assertTrue(keyboard.state.value.error!!.contains("MIDI 发送失败"))
        assertTrue(keyboard.state.value.error!!.contains("GATT write failed"))
    }
}
