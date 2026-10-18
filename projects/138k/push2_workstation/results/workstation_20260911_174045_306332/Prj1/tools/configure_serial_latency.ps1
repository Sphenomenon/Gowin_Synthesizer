# Inspect by default. -Apply requires an administrator PowerShell and changes
# only the previously identified UART channel B, never the USB/JTAG parent.
param(
    [ValidateSet(1, 2, 4, 8, 16)][int]$LatencyMs = 1,
    [string]$InstanceId = 'FTDIBUS\VID_0403+PID_6010+2025030317B\0000',
    [string]$ExpectedPort = 'COM26',
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
if ($InstanceId -notmatch '^FTDIBUS\\VID_0403\+PID_6010\+[^\\]+B\\0000$') {
    throw 'Expected an exact FT2232-compatible UART channel B instance.'
}
$registryPath = "SYSTEM\CurrentControlSet\Enum\$InstanceId\Device Parameters"
$deviceKey = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($registryPath, $false)
if ($null -eq $deviceKey) { throw "Device is missing: $InstanceId" }
try {
    $actualPort = $deviceKey.GetValue('PortName')
    $previousLatency = $deviceKey.GetValue('LatencyTimer')
    $valueKind = $deviceKey.GetValueKind('LatencyTimer')
} finally { $deviceKey.Dispose() }
if ($actualPort -ne $ExpectedPort -or $valueKind -ne [Microsoft.Win32.RegistryValueKind]::DWord) {
    throw "Identity/type mismatch: expected $ExpectedPort, got $actualPort / $valueKind"
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$isAdministrator = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$report = [ordered]@{
    instance_id = $InstanceId
    port = $actualPort
    registry_key = "HKEY_LOCAL_MACHINE\$registryPath"
    before_latency_ms = $previousLatency
    requested_latency_ms = $LatencyMs
    administrator = $isAdministrator
    applied = $false
    restarted = $false
}
if (-not $Apply) { $report | ConvertTo-Json; return }
if (-not $isAdministrator) {
    throw 'Windows denied changing this device setting. Run this exact script with -Apply from an administrator PowerShell.'
}
$evidenceDirectory = Join-Path $PSScriptRoot '../build'
[IO.Directory]::CreateDirectory($evidenceDirectory) | Out-Null
$stamp = [DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss_fffffff')
$evidencePath = Join-Path $evidenceDirectory "serial_driver_config_$stamp.json"
$report | ConvertTo-Json | Set-Content -LiteralPath $evidencePath -Encoding utf8
$deviceKey = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($registryPath, $true)
try {
    $deviceKey.SetValue('LatencyTimer', $LatencyMs, [Microsoft.Win32.RegistryValueKind]::DWord)
    $report.applied = $true
    # Exact child instance only: do not use /deviceid, /subtree or a USB parent.
    & "$env:WINDIR/System32/pnputil.exe" /restart-device $InstanceId
    if ($LASTEXITCODE -ne 0) {
        $deviceKey.SetValue('LatencyTimer', $previousLatency, [Microsoft.Win32.RegistryValueKind]::DWord)
        $report.applied = $false
        throw 'The UART child could not restart; the registry value was restored.'
    }
    $report.restarted = $true
} finally {
    $deviceKey.Dispose()
    $report | ConvertTo-Json | Set-Content -LiteralPath $evidencePath -Encoding utf8
}
$report | ConvertTo-Json
Write-Output "Evidence: $evidencePath"
