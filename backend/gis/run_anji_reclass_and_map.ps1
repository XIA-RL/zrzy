<#.SYNOPSIS
  One-click pipeline: SAGA reclassify + Python map export.

.EXAMPLE
  .\run_anji_reclass_and_map.ps1
#>
[CmdletBinding()]
param(
  [string] $WorkDir = $(if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }),
  [string] $InputTif = "",
  [string] $ReclassTif = "",
  [string] $MapPng = "",
  [string] $SagaCmd = $env:SAGA_CMD,
  [string] $Python = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $InputTif) { $InputTif = Join-Path $WorkDir "CLCD_2023_Anji.tif" }
if (-not $ReclassTif) { $ReclassTif = Join-Path $WorkDir "CLCD_2023_Anji_5class.tif" }
if (-not $MapPng) { $MapPng = Join-Path $WorkDir "CLCD_2023_Anji_5class_map.png" }

$reclassScript = Join-Path $WorkDir "reclass_anji_saga.ps1"
$plotScript = Join-Path $WorkDir "plot_anji_lulc_map.py"

if (-not (Test-Path -LiteralPath $reclassScript)) { throw "Missing: $reclassScript" }
if (-not (Test-Path -LiteralPath $plotScript)) { throw "Missing: $plotScript" }

& $reclassScript -WorkDir $WorkDir -InputTif $InputTif -OutputTif $ReclassTif -SagaCmd $SagaCmd
if ($LASTEXITCODE -ne 0) { throw "Reclassification failed." }

& $Python $plotScript --input $ReclassTif --output $MapPng
if ($LASTEXITCODE -ne 0) { throw "Map plotting failed." }

Write-Host ""
Write-Host "Pipeline finished."
Write-Host "  Raster: $ReclassTif"
Write-Host "  Map   : $MapPng"
