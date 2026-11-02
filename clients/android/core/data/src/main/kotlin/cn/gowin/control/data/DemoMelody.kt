package cn.gowin.control.data

import kotlin.math.PI
import kotlin.math.exp
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin

/** Local recording source. It never enters a real BLE session or the saved library directly. */
object DemoMelody {
    const val SAMPLE_RATE = 48000
    const val CAPACITY_FRAMES = SAMPLE_RATE * 10
    private const val BEAT_FRAMES = SAMPLE_RATE / 2
    private val notes = intArrayOf(60, 60, 67, 67, 69, 69, 67, 65, 65, 64, 64, 62, 62, 60)
    private val beats = intArrayOf(1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 2)
    private val radiansPerFrame = notes.map { 2 * PI * 440.0 * 2.0.pow((it - 69) / 12.0) / SAMPLE_RATE }

    /** PCM16 little endian, stereo. Only the elapsed recording prefix is materialized. */
    fun pcm(frames: Long): ByteArray {
        require(frames in 0..CAPACITY_FRAMES.toLong())
        val pcm = ByteArray(frames.toInt() * 4)
        val phraseFrames = beats.sum() * BEAT_FRAMES
        val attackFrames = SAMPLE_RATE * 12 / 1000
        val releaseFrames = SAMPLE_RATE * 35 / 1000
        val endFadeFrames = SAMPLE_RATE * 8 / 1000
        for (frame in 0 until frames.toInt()) {
            var position = frame % phraseFrames
            var note = 0
            while (position >= beats[note] * BEAT_FRAMES) {
                position -= beats[note] * BEAT_FRAMES
                note++
            }
            val soundingFrames = beats[note] * BEAT_FRAMES - SAMPLE_RATE * 30 / 1000
            var value = 0
            if (position < soundingFrames) {
                val time = position.toDouble() / SAMPLE_RATE
                val phase = radiansPerFrame[note] * position
                val envelope = min(1.0, position.toDouble() / attackFrames) *
                    min(1.0, (soundingFrames - position).toDouble() / releaseFrames) * exp(-1.6 * time)
                // A quiet, bell-like tone, with headroom for both harmonics.
                val tone = sin(phase) + 0.18 * sin(phase * 2) + 0.08 * sin(phase * 3)
                val endFade = min(1.0, (frames - 1 - frame).toDouble() / endFadeFrames)
                value = (10000 * envelope * tone * endFade).toInt()
            }
            val offset = frame * 4
            pcm[offset] = value.toByte()
            pcm[offset + 1] = (value shr 8).toByte()
            pcm[offset + 2] = value.toByte()
            pcm[offset + 3] = (value shr 8).toByte()
        }
        return pcm
    }
}
