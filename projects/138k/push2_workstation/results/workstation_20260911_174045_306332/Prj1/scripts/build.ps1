param(
    [ValidateSet('all','syn')][string]$Flow = 'all',
    [string]$GowinShell = $env:GOWIN_SHELL,
    [string]$WorkDir,
    [string]$Simlib = $env:GOWIN_SIMLIB
)
$ErrorActionPreference = 'Stop'
# Python discovers PATH/native tools and builds a fresh snapshot. The existing
# source-tree impl/pnr and build evidence are never output targets.
$arguments = @((Join-Path $PSScriptRoot 'build.py'), '--flow', $Flow)
if ($GowinShell) { $arguments += @('--gowin-shell', $GowinShell) }
if ($WorkDir) { $arguments += @('--work-dir', $WorkDir) }
if ($Simlib) { $arguments += @('--simlib', $Simlib) }
python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Isolated Gowin build failed' }
