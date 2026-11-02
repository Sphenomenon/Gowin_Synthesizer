package cn.gowin.control

import android.graphics.Bitmap
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.test.platform.app.InstrumentationRegistry
import cn.gowin.control.data.MusicPlayback
import cn.gowin.control.data.Workstation
import cn.gowin.control.data.WorkstationState
import cn.gowin.control.protocol.Capability
import cn.gowin.control.protocol.Snapshot
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import org.junit.After
import org.junit.Rule
import org.junit.Test

/** UI fixtures exercise advertised capability handling, not a physical device. */
class ControlCapabilitiesTest {
    @get:Rule val compose = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun closeScope() = scope.cancel()

    private fun render(state: WorkstationState, openMusic: () -> Unit = {}) {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val model = ControlViewModel(Workstation(context, scope), MusicPlayback(context))
        compose.setContent { MaterialTheme { Column { Controls(state, model, openMusic) } } }
    }

    @Test fun recordingOnlyDeviceDoesNotInventSynthState() {
        var openedMusic = false
        render(WorkstationState(ready = true, name = "GW138K-W", capability = Capability(1uL, 0x68, 256, 1),
            snapshot = Snapshot(valid = 4, recordState = 4))) { openedMusic = true }
        compose.onNodeWithText("工作站").assertIsDisplayed()
        compose.onNodeWithText("使用工作站或 25K 面板调节声音。").assertIsDisplayed()
        compose.onNodeWithText("设备录音：已开放").assertIsDisplayed()
        compose.onNodeWithText("录音下载：已开放").assertIsDisplayed()
        compose.onNodeWithText("合成模式").assertDoesNotExist()
        compose.onNodeWithText("内置音色").assertDoesNotExist()
        compose.onNodeWithText("活动声部：", substring = true).assertDoesNotExist()
        compose.onNodeWithText("刷新状态").assertIsDisplayed()
        val output = InstrumentationRegistry.getInstrumentation().targetContext.getExternalFilesDir("ui-evidence")!!
        output.mkdirs()
        output.resolve("recording-only-controls.png").outputStream().use {
            compose.onRoot().captureToImage().asAndroidBitmap().compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        compose.onNodeWithText("前往音乐").performClick()
        compose.runOnIdle { check(openedMusic) }
    }

    @Test fun existing25kBuiltInAudioBranchIsPreserved() {
        render(WorkstationState(ready = true, name = "GW25K-PROTO", capability = Capability(1uL, 0x68, 256, 1)))
        compose.onNodeWithText("25K 设备").assertIsDisplayed()
        compose.onNodeWithText("刷新状态").assertIsDisplayed()
        compose.onNodeWithText("工作站").assertDoesNotExist()
    }

    @Test fun existingProtocolOnlyBranchIsPreserved() {
        render(WorkstationState(ready = true, name = "GW25K-PROTO", capability = Capability(1uL, 0, 0, 1, 0)))
        compose.onNodeWithText("25K 设备").assertIsDisplayed()
        compose.onNodeWithText("刷新状态").assertIsDisplayed()
        compose.onNodeWithText("工作站").assertDoesNotExist()
    }
}
