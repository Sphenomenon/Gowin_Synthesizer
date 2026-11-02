package cn.gowin.control

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import cn.gowin.control.ble.FoundDevice
import cn.gowin.control.ble.MidiTransport
import cn.gowin.control.data.MidiKeyboard
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class BleRecoveryUiTest {
    @get:Rule val compose = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun close() { scope.cancel() }

    private class Fixture : MidiTransport {
        override val connected = MutableStateFlow(false)
        override val devices = MutableStateFlow<List<FoundDevice>>(emptyList())
        override val connectionProgress = MutableStateFlow<String?>(null)
        val gate = CompletableDeferred<Unit>()
        var sent = 0
        var connectCalls = 0
        var closeCalls = 0
        override fun startScan(onError: (String) -> Unit) {}
        override fun stopScan() {}
        override suspend fun connect(address: String) { connectCalls++; gate.await(); connected.value = true }
        override suspend fun send(packet: ByteArray) {
            check(connected.value)
            sent++
        }
        override fun close() { closeCalls++; connected.value = false }
    }

    @Test fun recoveryProgressDisablesKeysAndAllowsCancellation() {
        val link = Fixture()
        val midi = MidiKeyboard(link, scope) { 0 }
        compose.setContent {
            MaterialTheme {
                Column(Modifier.verticalScroll(rememberScrollState())) { MidiKeyboardPanel(midi) }
            }
        }
        compose.runOnIdle {
            midi.connect("fixture", "Recovery UI fixture - not a real board")
            link.connectionProgress.value = "系统已清除旧配对，正在自动重连（仅一次）…"
        }
        compose.onNodeWithText("系统已清除旧配对，正在自动重连（仅一次）…").assertExists()
        compose.onNodeWithContentDescription("MIDI音符48").assertIsNotEnabled()
        compose.onNodeWithText("断开MIDI").performScrollTo().performClick()
        compose.runOnIdle { link.gate.complete(Unit) }
        compose.waitUntil { !midi.state.value.connecting }
        compose.runOnIdle {
            assertFalse(midi.state.value.ready)
            assertEquals(0, link.sent)
        }
    }

    @Test fun successfulRecoveryCleansNotesBeforeEnablingKeys() {
        val link = Fixture()
        val midi = MidiKeyboard(link, scope) { 0 }
        compose.setContent {
            MaterialTheme {
                Column(Modifier.verticalScroll(rememberScrollState())) { MidiKeyboardPanel(midi) }
            }
        }
        compose.runOnIdle { midi.connect("fixture", "Recovery UI fixture - not a real board") }
        compose.onNodeWithContentDescription("MIDI音符48").assertIsNotEnabled()
        compose.runOnIdle { link.gate.complete(Unit) }
        compose.waitUntil { midi.state.value.ready }
        compose.runOnIdle { assertEquals(32, link.sent) }
        compose.onNodeWithContentDescription("MIDI音符48").assertIsEnabled()
        compose.onNodeWithText("打开系统蓝牙设置 · 处理旧配对").assertExists()
    }

    @Test fun leavingAndReturningToPanelKeepsConnectionAndClearsHeldNotes() {
        val link = Fixture()
        val midi = MidiKeyboard(link, scope) { 0 }
        val visible = mutableStateOf(true)
        compose.setContent {
            MaterialTheme {
                if (visible.value) Column(Modifier.verticalScroll(rememberScrollState())) { MidiKeyboardPanel(midi) }
            }
        }
        compose.runOnIdle {
            midi.connect("fixture", "Lifecycle UI fixture - not a real board")
            link.gate.complete(Unit)
        }
        compose.waitUntil { midi.state.value.ready }
        var closesBeforeLeaving = 0
        compose.runOnIdle {
            closesBeforeLeaving = link.closeCalls
            midi.noteOn(48)
            visible.value = false
        }
        compose.waitUntil { midi.state.value.heldNotes.isEmpty() }
        compose.runOnIdle {
            assertTrue(midi.state.value.ready)
            assertTrue(link.connected.value)
            assertEquals(closesBeforeLeaving, link.closeCalls)
            assertEquals(1, link.connectCalls)
            visible.value = true
        }
        compose.onNodeWithContentDescription("MIDI音符48").assertIsEnabled()
        compose.runOnIdle { assertTrue(midi.state.value.heldNotes.isEmpty()) }
    }
}
