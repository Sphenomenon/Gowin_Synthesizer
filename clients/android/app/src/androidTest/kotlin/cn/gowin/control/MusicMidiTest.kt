package cn.gowin.control

import android.graphics.Bitmap
import android.net.Uri
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import cn.gowin.control.ble.FoundDevice
import cn.gowin.control.ble.MidiTransport
import cn.gowin.control.data.MidiKeyboard
import cn.gowin.control.data.MusicPlayback
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.*
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Real Android media lifecycle; MIDI uses an explicitly labelled transport fixture. */
class MusicMidiTest {
    @get:Rule val compose = createComposeRule()
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var music: MusicPlayback? = null
    @After fun close() {
        compose.runOnIdle { music?.close() }
        scope.cancel()
    }
    private fun screenshot(name: String) {
        val out = context.getExternalFilesDir("ui-evidence")!!.resolve(name)
        out.parentFile!!.mkdirs()
        out.outputStream().use { compose.onRoot().captureToImage().asAndroidBitmap().compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
    @Test fun explicitLocalOutputActualRouteSeekAndPause() {
        val dataBytes = 48_000 * 4 * 10
        val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
            .put("RIFF".toByteArray()).putInt(36 + dataBytes).put("WAVEfmt ".toByteArray()).putInt(16)
            .putShort(1).putShort(2).putInt(48_000).putInt(192_000).putShort(4).putShort(16)
            .put("data".toByteArray()).putInt(dataBytes).array()
        val file = context.cacheDir.resolve("local-route-lifecycle-10s.wav")
        file.outputStream().use { it.write(header); it.write(ByteArray(dataBytes)) }
        val playback = MusicPlayback(context).also { music = it }
        compose.setContent { MaterialTheme { Column(Modifier.verticalScroll(rememberScrollState())) { Music(playback, null) {} } } }
        compose.runOnIdle { playback.select(Uri.fromFile(file)) }
        compose.waitUntil(10_000) { playback.state.value.ready }
        compose.runOnIdle {
            Assert.assertNull(playback.state.value.selectedOutputId)
            playback.play()
            Assert.assertFalse(playback.state.value.playing)
            val local = playback.state.value.outputs.first { !it.a2dp }
            playback.selectOutput(local.id)
            playback.play()
        }
        compose.waitUntil(5_000) { playback.state.value.playing && playback.state.value.routeConfirmed }
        compose.onNodeWithText("已确认实际路由与选择一致").assertIsDisplayed()
        compose.runOnIdle { playback.seek(4000) }
        compose.waitUntil(5_000) { playback.state.value.positionMs >= 4000 }
        compose.runOnIdle { playback.pause() }
        compose.waitUntil { !playback.state.value.playing }
        screenshot("music-local-route-confirmed.png")
    }
    private class Fixture : MidiTransport {
        override val connected = MutableStateFlow(false)
        override val devices = MutableStateFlow<List<FoundDevice>>(emptyList())
        val sent = mutableListOf<ByteArray>()
        override fun startScan(onError: (String) -> Unit) {}
        override fun stopScan() {}
        override suspend fun connect(address: String) { connected.value = true }
        override suspend fun send(packet: ByteArray) { sent += packet.copyOf() }
        override fun close() { connected.value = false }
    }
    @Test fun keyboardPressReleaseCancelAndPanic() {
        val link = Fixture()
        val midi = MidiKeyboard(link, scope) { 0 }
        compose.setContent { MaterialTheme { Column(Modifier.verticalScroll(rememberScrollState())) { MidiKeyboardPanel(midi) } } }
        compose.runOnIdle { midi.connect("fixture", "UI fixture - not a real 25K") }
        compose.waitUntil { midi.state.value.ready }
        val key = compose.onNodeWithContentDescription("MIDI音符48")
        key.performScrollTo().performTouchInput { down(center) }
        compose.waitUntil { 48 in midi.state.value.heldNotes }
        key.performTouchInput { up() }
        compose.waitUntil { midi.state.value.heldNotes.isEmpty() && link.sent.size == 34 }
        key.performTouchInput { down(center) }
        compose.waitUntil { 48 in midi.state.value.heldNotes }
        key.performTouchInput { cancel() }
        compose.waitUntil { midi.state.value.heldNotes.isEmpty() && link.sent.size == 36 }
        compose.onNodeWithText("PANIC · 全通道停音").performScrollTo().performClick()
        compose.waitUntil { link.sent.size == 68 }
        Assert.assertEquals(0x90, link.sent[32][2].toInt() and 255)
        Assert.assertEquals(0x80, link.sent[33][2].toInt() and 255)
        Assert.assertEquals(0x80, link.sent[35][2].toInt() and 255)
        screenshot("midi-keyboard-fixture.png")
    }
}
