package cn.gowin.control

import java.util.Locale
import org.junit.Assert.assertEquals
import org.junit.Test

class RecordingDurationTest {
    @Test fun shortRecordingAndCapacityRemainVisible() {
        assertEquals("00:00.100", duration(4800, 48000))
        assertEquals("00:00.341", duration(16384, 48000))
        assertEquals("00:00.100", duration(4410, 44100))
        assertEquals("00:00.371", duration(16384, 44100))
    }

    @Test fun durationUsesWholeFramesWithoutRoundingUp() {
        assertEquals("00:00.000", duration(0, 48000))
        assertEquals("00:00.000", duration(47, 48000))
        assertEquals("00:00.001", duration(48, 48000))
        assertEquals("00:59.999", duration(60 * 48000 - 1L, 48000))
        assertEquals("01:00.000", duration(60 * 48000L, 48000))
        assertEquals("60:00.000", duration(3600 * 48000L, 48000))
    }

    @Test fun displayDoesNotMultiplyTheFullFrameCount() {
        assertEquals("3202559735019:01.162", duration(Long.MAX_VALUE, 48000))
    }

    @Test fun unknownMetadataIsNotShownAsARealDuration() {
        assertEquals("--:--.---", duration(4800, 0))
        assertEquals("--:--.---", duration(4800, -1))
        assertEquals("--:--.---", duration(-1, 48000))
    }

    @Test fun deviceLocaleDoesNotChangeNumericIdentity() {
        val previous = Locale.getDefault()
        try {
            Locale.setDefault(Locale.forLanguageTag("ar"))
            assertEquals("00:00.100", duration(4800, 48000))
        } finally {
            Locale.setDefault(previous)
        }
    }
}
