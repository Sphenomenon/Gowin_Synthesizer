package cn.gowin.control

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.*
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import cn.gowin.control.data.MidiKeyboard

@Composable internal fun MidiKeyboardPanel(midi: MidiKeyboard) {
    val state by midi.state.collectAsStateWithLifecycle()
    val devices by midi.devices.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val permissions = remember {
        if (Build.VERSION.SDK_INT >= 31) arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        else arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
        if (permissions.all { result[it] == true || ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED }) midi.scan()
        else midi.reportError("需要附近设备权限才能扫描25K MIDI；请在应用设置中授权。")
    }
    DisposableEffect(midi) { onDispose { midi.panic(); midi.stopScan() } }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("手机 → 25K MIDI 控制", style = MaterialTheme.typography.titleMedium)
            Text("25K USB继续接138K Host；手机使用独立的 BLE MIDI 连接。当前25K固件将接收音符用于灯光反馈，尚未转发到138K发声。", style = MaterialTheme.typography.bodySmall)
            Text(if (state.connecting) "连接及清理旧音符中…" else if (state.ready) "MIDI 已连接 · ${state.name}" else "MIDI 未连接 · ${state.name}")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(enabled = !state.connecting, onClick = {
                    if (permissions.all { ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED }) midi.scan()
                    else permission.launch(permissions)
                }) { Text("扫描25K MIDI") }
                if (state.ready || state.connecting) TextButton(onClick = midi::disconnect) { Text("断开MIDI") }
            }
            if (!state.ready) devices.forEach { device ->
                OutlinedButton(enabled = !state.connecting, onClick = { midi.connect(device.address, device.name) }) {
                    Text("${device.name} · ${device.address}")
                }
            }
            Text("通道 ${state.channel + 1} · 力度 ${state.velocity}")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { midi.setChannel((state.channel + 15) % 16) }) { Text("通道 −") }
                OutlinedButton(onClick = { midi.setChannel((state.channel + 1) % 16) }) { Text("通道 +") }
            }
            Slider(value = state.velocity.toFloat(), onValueChange = { midi.setVelocity(it.toInt()) }, valueRange = 1f..127f,
                modifier = Modifier.semantics { contentDescription = "新音符力度" })
            (48..63).toList().chunked(4).forEach { row ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    row.forEach { note ->
                        val down = note in state.heldNotes
                        Box(Modifier.weight(1f).height(64.dp)
                            .background(if (down) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(8.dp))
                            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(8.dp))
                            .semantics {
                                contentDescription = "MIDI音符$note"
                                role = Role.Button
                                if (!state.ready) disabled()
                                onClick { if (state.ready) { midi.noteOn(note); midi.noteOff(note); true } else false }
                            }
                            .pointerInput(note, state.ready) {
                                if (state.ready) detectTapGestures(onPress = {
                                    midi.noteOn(note)
                                    try { tryAwaitRelease() } finally { midi.noteOff(note) }
                                })
                            }, contentAlignment = Alignment.Center) {
                            Text(note.toString(), color = if (down) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
            Button(enabled = state.ready, onClick = midi::panic) { Text("PANIC · 全通道停音") }
            Text("按住发送 Note On，松开或取消手势发送 Note Off。切页／后台发送PANIC，断开前清理，重连先清理再接受新按键。已发送 ${state.sentEvents} 个事件；发送完成不代表138K已发声。", style = MaterialTheme.typography.bodySmall)
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            TextButton(onClick = { context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}"))) }) { Text("MIDI蓝牙权限设置") }
        }
    }
}
