package cn.gowin.control

import android.content.ContextWrapper
import android.graphics.Bitmap
import android.media.MediaPlayer
import android.os.SystemClock
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import cn.gowin.control.data.MusicPlayback
import cn.gowin.control.data.Workstation
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Exercises the local presentation path; it makes no radio or physical-board claim. */
class PresentationRecordingTest {
    @get:Rule val compose = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val storage = File(context.cacheDir, "presentation-ui-${System.nanoTime()}").apply { mkdirs() }
    private val repo = Workstation(object : ContextWrapper(context) {
        override fun getFilesDir() = storage
    }, scope)
    private val music = MusicPlayback(context)
    private var player: MediaPlayer? = null

    @After fun close() {
        player?.release()
        repo.disconnect()
        music.close()
        scope.cancel()
        storage.deleteRecursively()
    }

    private fun screenshot(name: String) {
        val output = context.getExternalFilesDir("ui-evidence")!!.apply { mkdirs() }
        output.resolve(name).outputStream().use {
            compose.onRoot().captureToImage().asAndroidBitmap().compress(Bitmap.CompressFormat.PNG, 100, it)
        }
    }

    @Test fun recordingRequiresElapsedTimeThenDownloadsAndPlaysMelody() {
        val model = ControlViewModel(repo, music)
        compose.setContent {
            MaterialTheme {
                ControlRoot(model, {}, { repo.disconnect() }, { file ->
                    player = MediaPlayer().apply { setDataSource(file.absolutePath); prepare(); start() }
                }, {}, {})
            }
        }
        compose.onNodeWithText("扫描并接入 138K").performClick()
        compose.waitUntil(10000) { repo.state.value.ready }
        assertTrue(repo.state.value.library.isEmpty())
        assertEquals(0, repo.state.value.record!!.frames)
        compose.onNodeWithText("录音", useUnmergedTree = true).performClick()
        compose.onNodeWithText("下载 / 继续").performScrollTo().assertIsNotEnabled()
        compose.onNodeWithText("开始录音").performScrollTo().performClick()
        compose.waitUntil { repo.state.value.record?.state == 2 }
        SystemClock.sleep(2300)
        assertTrue(repo.state.value.library.isEmpty())
        compose.onNodeWithText("下载 / 继续").performScrollTo().assertIsNotEnabled()
        compose.onNodeWithText("停止", substring = false).performScrollTo().performClick()
        compose.waitUntil { repo.state.value.record?.state == 4 && !repo.state.value.busy }
        val frames = repo.state.value.record!!.frames
        assertTrue("recorded duration follows elapsed time", frames in 110400..240000)
        screenshot("presentation-recorded.png")
        compose.onNodeWithText("下载 / 继续").performScrollTo().performClick()
        compose.waitUntil(60000) { repo.state.value.library.isNotEmpty() }
        val entry = repo.state.value.library.single()
        assertEquals(frames * 4 + 44, entry.file.length())
        assertTrue(entry.demo) // Retain provenance in data, independently of presentation copy.
        compose.onNodeWithText("作品", useUnmergedTree = true).performClick()
        compose.onNodeWithText("试听").performScrollTo().performClick()
        compose.runOnIdle {
            assertTrue(player!!.isPlaying)
            assertTrue(player!!.duration >= 2300)
        }
        compose.onNodeWithText("模拟", substring = true).assertDoesNotExist()
        compose.onNodeWithText("测试", substring = true).assertDoesNotExist()
        compose.onNodeWithText("不代表", substring = true).assertDoesNotExist()
        screenshot("presentation-library.png")
    }
}
