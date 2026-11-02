package cn.gowin.control.data

import org.junit.Assert.*
import org.junit.Test

class MusicRouteTest {
    @Test fun explicitDeviceIdentityMustMatchAvailableActualOutput() {
        assertFalse(MusicRoute.accepts(null, 1, setOf(1)))
        assertFalse(MusicRoute.accepts(2, 1, setOf(1, 2)))
        assertFalse(MusicRoute.accepts(2, 2, setOf(1)))
        assertFalse(MusicRoute.accepts(2, null, setOf(1, 2)))
        assertTrue(MusicRoute.accepts(2, 2, setOf(1, 2)))
    }
}
