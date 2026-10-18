param([string]$ToolsRoot='C:\AMDDesignTools\2026.1')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskBin=Join-Path $ToolsRoot 'Vivado/bin'
$env:PROCESSOR_ARCHITECTURE='AMD64'
Push-Location $taskRoot
try {
    python scripts/verify_package.py
    if($LASTEXITCODE -ne 0){throw 'Export package integrity check failed'}
    New-Item -ItemType Directory -Force -Path sim_output | Out-Null
    $taskCases=@(
        @{Name='h5'; Top='tb_bt_h5'; Token='SIM_BT_H5_PASS';
          Files=@('rtl/bt_uart.v','rtl/bt_h5_transport.v','tests/tb_bt_h5.v')},
        @{Name='gatt'; Top='tb_bt_gatt'; Token='SIM_BT_GATT_PASS';
          Files=@('rtl/bt_gatt.v','tests/tb_bt_gatt.v')},
        @{Name='system'; Top='tb_bt_verilog_system'; Token='SIM_BT_VERILOG_SYSTEM_PASS';
          Files=@('rtl/bt_uart.v','rtl/bt_h5_transport.v','rtl/bt_hci_init.v',
                  'rtl/bt_gatt.v','rtl/bt_verilog_core.v','rtl/reset_release_sync.v',
                  'rtl/rtl8723ds_ble.v','tests/tb_bt_verilog_system.v')}
    )
    foreach($taskCase in $taskCases) {
        $taskLibrary="portable_$($taskCase.Name)"
        $taskSnapshot="portable_$($taskCase.Name)_sim"
        & "$taskBin/xvlog.bat" -work $taskLibrary @($taskCase.Files)
        if($LASTEXITCODE -ne 0){throw "Compile failed: $($taskCase.Name)"}
        & "$taskBin/xelab.bat" "$taskLibrary.$($taskCase.Top)" -s $taskSnapshot -debug typical
        if($LASTEXITCODE -ne 0){throw "Elaboration failed: $($taskCase.Name)"}
        $taskVariants=@('normal')
        if($taskCase.Name -eq 'system') {$taskVariants+= 'wrong_rom'}
        foreach($taskVariant in $taskVariants) {
            $taskLog="sim_output/$($taskCase.Name)_$taskVariant.log"
            if(Test-Path -LiteralPath $taskLog){Remove-Item -LiteralPath $taskLog}
            $taskArgs=@($taskSnapshot,'-tclbatch',"scripts/sim_bt_$($taskCase.Name).tcl",'-log',$taskLog)
            if($taskVariant -eq 'wrong_rom'){$taskArgs+=@('-testplusarg','wrong_rom')}
            & "$taskBin/xsim.bat" @taskArgs
            if($LASTEXITCODE -ne 0){throw "Simulator failed: $($taskCase.Name)/$taskVariant"}
            $taskText=Get-Content -LiteralPath $taskLog -Raw
            $taskPattern='(?m)^'+[regex]::Escape($taskCase.Token)+'\r?$'
            if($taskText -notmatch $taskPattern -or $taskText -match '(?m)^Fatal:|^ERROR:|^FAIL:') {
                throw "Simulation failed: $($taskCase.Name)/$taskVariant"
            }
        }
    }
    & "$taskBin/xvlog.bat" -work portable_board examples/rtl8723ds_ble_board_top.v @(Get-Content sources.f)
    if($LASTEXITCODE -ne 0){throw 'Board example compile failed'}
    & "$taskBin/xelab.bat" portable_board.rtl8723ds_ble_board_top -s portable_board_example
    if($LASTEXITCODE -ne 0){throw 'Board example elaboration failed'}
    Write-Output 'PORTABLE_BT_SIMULATIONS=PASS'
} finally {Pop-Location}
