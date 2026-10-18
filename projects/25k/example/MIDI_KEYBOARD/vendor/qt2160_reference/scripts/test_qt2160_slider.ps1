$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$binDir = 'D:\AAA_Vivado_installation\2025.1\Vivado\bin'
Push-Location $projectDir
try {
    & (Join-Path $binDir 'xvlog.bat') --sv rtl/qt2160_i2c_master.v rtl/qt2160_slider_reader.v rtl/uart_rx.v rtl/uart_tx.v rtl/led_breath_channel.v rtl/uart_led_controller.v sim/tb_qt2160_slider.sv -log uart_debug/slider_xvlog.log
    if ($LASTEXITCODE -ne 0) { throw 'Slider compilation failed' }
    & (Join-Path $binDir 'xelab.bat') work.tb_qt2160_slider -s tb_qt2160_slider_sim --debug typical -log uart_debug/slider_xelab.log
    if ($LASTEXITCODE -ne 0) { throw 'Slider elaboration failed' }
    & (Join-Path $binDir 'xsim.bat') tb_qt2160_slider_sim -runall -log uart_debug/slider_simulation.log
    if ($LASTEXITCODE -ne 0) { throw 'Slider simulation failed' }
    $taskLog = Get-Content -LiteralPath 'uart_debug/slider_simulation.log' -Raw
    if ($taskLog -match 'Fatal:|Error:' -or $taskLog -notmatch '(?m)^PASS:') { throw 'Slider assertions failed' }
    'QT2160_SLIDER_SIMULATION_PASS'
} finally { Pop-Location }
