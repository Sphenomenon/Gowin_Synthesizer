package cn.gowin.control.ble

import java.io.IOException
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class GattConnectionRecoveryTest {
    private fun bonded() = MutableStateFlow(BondObservation(true, BondState.BONDED))
    private fun cleared() = MutableStateFlow(BondObservation(true, BondState.NONE, removed = true))

    private suspend fun failure(block: suspend () -> Unit): Exception {
        try { block() } catch (error: Exception) { return error }
        throw AssertionError("Expected failure")
    }

    @Test fun successfulConnectionDoesNotResetOrRetry() = runTest {
        var attempts = 0
        val result = connectWithBondRecovery(bonded(), { fail("Unexpected reset") }) { attempts++; "ready" }
        assertEquals("ready", result)
        assertEquals(1, attempts)
    }

    @Test fun clearedOldBondRecoversSubscription133Once() = runTest {
        var attempts = 0
        var resets = 0
        val progress = mutableListOf<String>()
        val result = connectWithBondRecovery(cleared(), { resets++ }, { progress += it }) {
            attempts++
            if (attempts == 1) throw GattFailure("subscribe", 133)
            "ready"
        }
        assertEquals("ready", result)
        assertEquals(2, attempts)
        assertEquals(1, resets)
        assertTrue(progress.last().contains("仅一次"))
    }

    @Test fun authenticationFailureWaitsForSystemBondRemoval() = runTest {
        val observations = bonded()
        var attempts = 0
        launch { delay(500); observations.value = observations.value.changed(BondState.NONE) }
        connectWithBondRecovery(observations, {}) {
            attempts++
            if (attempts == 1) throw GattFailure("subscribe", 5)
        }
        assertEquals(2, attempts)
        assertEquals(850, testScheduler.currentTime)
    }

    @Test fun unbondedGeneric133IsNotCalledAKeyFailure() = runTest {
        val observations = MutableStateFlow(BondObservation(false, BondState.NONE))
        var attempts = 0
        val original = GattFailure("subscribe", 133)
        val error = failure { connectWithBondRecovery(observations, {}) { attempts++; throw original } }
        assertSame(original, error)
        assertEquals(1, attempts)
        assertFalse(error.message!!.contains("密钥"))
        assertEquals(0, testScheduler.currentTime)
    }

    @Test fun bondedGeneric133WithoutRemovalHasNoSpeculativeRetry() = runTest {
        var attempts = 0
        val original = GattFailure("subscribe", 133)
        val error = failure { connectWithBondRecovery(bonded(), {}) { attempts++; throw original } }
        assertSame(original, error)
        assertEquals(1, attempts)
        assertEquals(3000, testScheduler.currentTime)
        assertFalse(error.message!!.contains("密钥"))
    }

    @Test fun keyMissingWithoutSystemRemovalRequiresUserAction() = runTest {
        val observations = bonded().apply { value = value.copy(keyMissing = true) }
        var attempts = 0
        val error = failure {
            connectWithBondRecovery(observations, {}) { attempts++; throw GattFailure("subscribe", 133) }
        }
        assertEquals(1, attempts)
        assertTrue(error.message!!.contains("旧配对密钥"))
        assertTrue(error.message!!.contains("仅取消此设备"))
        assertTrue(error.message!!.contains("133"))
    }

    @Test fun authenticationFailureWithOldBondOffersQualifiedGuidance() = runTest {
        val error = failure { connectWithBondRecovery(bonded(), {}) { throw GattFailure("connect", 5) } }
        assertTrue(error.message!!.contains("可能已失效"))
        assertTrue(error.message!!.contains("GATT 5"))
        assertFalse(error.message!!.contains("未能提供旧配对密钥"))
    }

    @Test fun cancelledNewPairingDoesNotCountAsRemovedOldBond() = runTest {
        val initial = BondObservation(false, BondState.NONE)
        val observations = MutableStateFlow(initial.changed(BondState.BONDING).changed(BondState.NONE))
        assertFalse(observations.value.canRetry)
        var attempts = 0
        failure { connectWithBondRecovery(observations, {}) { attempts++; throw GattFailure("connect", 5) } }
        assertEquals(1, attempts)
    }

    @Test fun secondFailureStopsAndPreservesBothErrors() = runTest {
        var attempts = 0
        val first = GattFailure("subscribe", 5)
        val second = GattFailure("discover", 133)
        val error = failure {
            connectWithBondRecovery(cleared(), {}) {
                attempts++
                throw if (attempts == 1) first else second
            }
        }
        assertEquals(2, attempts)
        assertSame(second, error.cause)
        assertSame(first, error.suppressed.single())
        assertTrue(error.message!!.contains("服务发现"))
        assertTrue(error.message!!.contains("已停止重试"))
    }

    @Test fun missingBusinessServiceIsNotRetriedEvenAfterBondRemoval() = runTest {
        var attempts = 0
        val original = IOException("设备尚未提供 GW138K 业务服务")
        val error = failure { connectWithBondRecovery(cleared(), {}) { attempts++; throw original } }
        assertSame(original, error)
        assertEquals(1, attempts)
    }

    @Test fun cancellationWhileWaitingNeverReconnects() = runTest {
        val observations = bonded()
        var attempts = 0
        val connecting = launch {
            connectWithBondRecovery(observations, {}) { attempts++; throw GattFailure("subscribe", 5) }
        }
        runCurrent()
        connecting.cancel()
        observations.value = observations.value.changed(BondState.NONE)
        runCurrent()
        assertTrue(connecting.isCancelled)
        assertEquals(1, attempts)
    }

    @Test fun cancellationDuringRetryDelayNeverReconnects() = runTest {
        var attempts = 0
        val connecting = launch {
            connectWithBondRecovery(cleared(), {}) { attempts++; throw GattFailure("subscribe", 5) }
        }
        runCurrent()
        advanceTimeBy(100)
        connecting.cancel()
        runCurrent()
        assertEquals(1, attempts)
    }

    @Test fun newPairingDuringRetryDelayStopsRecovery() = runTest {
        val observations = cleared()
        var attempts = 0
        launch { delay(100); observations.value = observations.value.changed(BondState.BONDING) }
        val error = failure {
            connectWithBondRecovery(observations, {}) { attempts++; throw GattFailure("subscribe", 5) }
        }
        assertEquals(1, attempts)
        assertTrue(error.message!!.contains("配对状态已改变"))
    }

    @Test fun transportAndGattErrorsKeepStageAndRawStatus() {
        val error = GattFailure("subscribe", 5, "连接已断开")
        assertEquals("subscribe", error.operation)
        assertEquals(5, error.status)
        assertTrue(error.message!!.contains("通知订阅"))
        assertTrue(error.message!!.contains("GATT 5"))
        assertTrue(error.message!!.contains("认证或加密"))
    }

    @Test fun bondingIsNotAutomaticallyTreatedAsCleared() {
        val observation = BondObservation(true, BondState.BONDED).changed(BondState.NONE).changed(BondState.BONDING)
        assertTrue(observation.removed)
        assertFalse(observation.canRetry)
    }

    @Test fun genericGattFailuresDoNotRetryOnlyBecauseDeviceIsBonded() = runTest {
        val original = GattFailure("write", 3)
        assertSame(original, failure { connectWithBondRecovery(bonded(), {}) { throw original } })
        assertEquals(0, testScheduler.currentTime)
    }
}
