package cn.gowin.control.data

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin

class DemoMelodyTest {
    private fun sample(pcm: ByteArray, frame: Int, channel: Int = 0): Int {
        val offset = frame * 4 + channel * 2
        return ((pcm[offset].toInt() and 255) or (pcm[offset + 1].toInt() shl 8)).toShort().toInt()
    }

    @Test fun elapsedStereoPcmHasHeadroomAndSmoothBoundaries() {
        assertTrue(DemoMelody.pcm(0).isEmpty())
        val frames = 3L * 48000 + 137
        val pcm = DemoMelody.pcm(frames)
        assertEquals(frames * 4, pcm.size.toLong())
        var peak = 0
        var maxStep = 0
        var previous = 0
        for (frame in 0 until frames.toInt()) {
            val value = sample(pcm, frame)
            assertEquals(value, sample(pcm, frame, 1))
            peak = maxOf(peak, abs(value))
            maxStep = maxOf(maxStep, abs(value - previous))
            previous = value
        }
        assertTrue("quiet but audible peak: $peak", peak in 7000..15000)
        assertTrue("sample discontinuity: $maxStep", maxStep < 1300)
        assertEquals(0, sample(pcm, 0))
        assertEquals(0, sample(pcm, frames.toInt() - 1))
        assertEquals(DemoMelody.CAPACITY_FRAMES * 4, DemoMelody.pcm(DemoMelody.CAPACITY_FRAMES.toLong()).size)
        assertThrows(IllegalArgumentException::class.java) { DemoMelody.pcm(-1) }
        assertThrows(IllegalArgumentException::class.java) { DemoMelody.pcm(480001) }
    }

    @Test fun firstPhraseContainsTheRecognizableTwinkleNoteSequence() {
        val pcm = DemoMelody.pcm(8L * 48000)
        // Independent musical oracle: C C G G A A G(2) / F F E E D D C(2).
        val pitches = doubleArrayOf(261.625565, 293.664768, 329.627557, 349.228231, 391.995436, 440.0)
        val expected = intArrayOf(0, 0, 4, 4, 5, 5, 4, 3, 3, 2, 2, 1, 1, 0)
        val lengths = intArrayOf(1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 2)
        var startBeat = 0
        expected.forEachIndexed { note, pitch ->
            val start = startBeat * 24000 + 4800
            val powers = pitches.map { frequency ->
                var real = 0.0
                var imaginary = 0.0
                for (index in 0 until 9600) {
                    val phase = 2 * PI * frequency * index / 48000
                    val value = sample(pcm, start + index)
                    real += value * cos(phase)
                    imaginary += value * sin(phase)
                }
                real * real + imaginary * imaginary
            }
            val strongest = powers.indices.maxBy { powers[it] }
            assertEquals("note $note", pitch, strongest)
            assertTrue(powers[pitch] > powers.filterIndexed { index, _ -> index != pitch }.max() * 4)
            val gapStart = (startBeat + lengths[note]) * 24000 - 960
            assertTrue((gapStart until gapStart + 480).all { sample(pcm, it) == 0 })
            startBeat += lengths[note]
        }
    }
}
