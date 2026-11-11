# Headless Ghidra import + analysis + export for a NightSky image.
# Runs at BelowNormal priority (owner rule). Usage:
#   pwsh tools/ghidra_analyze.ps1 -Image out/fwu_v107.bin -Base 0x0800C000 -Name fwu107
param(
  [Parameter(Mandatory)][string]$Image,
  [Parameter(Mandatory)][string]$Base,
  [Parameter(Mandatory)][string]$Name
)
$ErrorActionPreference = 'Stop'
(Get-Process -Id $PID).PriorityClass = 'BelowNormal'

$root    = Split-Path $PSScriptRoot -Parent
$ghidra  = 'C:\Tools\ghidra_12.1.3_PUBLIC\support\analyzeHeadless.bat'
$proj    = Join-Path $root 'out\ghidra-proj'
$scripts = Join-Path $PSScriptRoot 'ghidra'
$outdir  = Join-Path $root "out\ghidra\$Name"
New-Item -ItemType Directory -Force $proj, $outdir | Out-Null
$img = Resolve-Path (Join-Path $root $Image)

$env:JAVA_HOME = 'C:\Tools\jdk-21.0.12.1+1'
$args = @(
  $proj, 'nightsky',
  '-import', $img,
  '-loader', 'BinaryLoader',
  '-loader-baseAddr', $Base,
  '-processor', 'ARM:LE:32:Cortex',
  '-scriptPath', $scripts,
  '-preScript', 'RecoverCortexM.java',
  '-postScript', 'ExportFw.java', $outdir,
  '-overwrite'
)
Write-Host "analyzeHeadless $Name  base=$Base  -> $outdir"
& $ghidra @args
Write-Host "done: $outdir"
