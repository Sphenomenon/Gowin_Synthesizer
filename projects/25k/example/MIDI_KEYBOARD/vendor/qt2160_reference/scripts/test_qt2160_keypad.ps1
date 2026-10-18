$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$binDir = 'D:\AAA_Vivado_installation\2025.1\Vivado\bin'
Push-Location $projectDir
try {
    & (Join-Path $binDir 'xvlog.bat') --sv rtl/qt2160_i2c_master.v rtl/qt2160_keypad_reader.v rtl/qt2160_keypad_uart.v rtl/uart_rx.v rtl/uart_tx.v rtl/led_breath_channel.v rtl/uart_led_controller.v sim/tb_qt2160_keypad.sv -log uart_debug/keypad_xvlog.log
    if ($LASTEXITCODE -ne 0) { throw 'Keypad compilation failed' }
    & (Join-Path $binDir 'xelab.bat') work.tb_qt2160_keypad -s tb_qt2160_keypad_sim --debug typical -log uart_debug/keypad_xelab.log
    if ($LASTEXITCODE -ne 0) { throw 'Keypad elaboration failed' }
    & (Join-Path $binDir 'xsim.bat') tb_qt2160_keypad_sim -runall -log uart_debug/keypad_simulation.log
    if ($LASTEXITCODE -ne 0) { throw 'Keypad simulation failed' }
    $taskLog = Get-Content -LiteralPath 'uart_debug/keypad_simulation.log' -Raw
    if ($taskLog -match 'Fatal:|Error:' -or $taskLog -notmatch '(?m)^PASS:') { throw 'Keypad assertions failed' }
    'QT2160_KEYPAD_SIMULATION_PASS'
} finally { Pop-Location }
