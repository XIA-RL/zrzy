<#.SYNOPSIS
  Reclassify clipped Anji CLCD raster into 5 LULC classes using SAGA 9.12.0.

.DESCRIPTION
  Maps CLCD v1 classes to:
    1 耕地 (cropland)   <- CLCD 1
    2 林地 (forest)     <- CLCD 2, 3 (shrub merged into forest)
    3 草地 (grassland)  <- CLCD 4
    4 水域 (water)      <- CLCD 5, 9
    5 居民用地          <- CLCD 8

  SAGA "Reclassify Grid Values" lookup tables can mis-handle rows whose new value is 1
  on some builds, so this script applies a short chain of single-value replacements (METHOD 0).

.EXAMPLE
  .\reclass_anji_saga.ps1

.EXAMPLE
  .\reclass_anji_saga.ps1 -InputTif "CLCD_2023_Anji.tif" -OutputTif "CLCD_2023_Anji_5class.tif"
#>
[CmdletBinding()]
param(
  [string] $WorkDir = $(if ($PSScriptRoot) { $PSScriptRoot } elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { (Get-Location).Path }),

  [string] $InputTif = (Join-Path $WorkDir "CLCD_2023_Anji.tif"),
  [string] $OutputTif = (Join-Path $WorkDir "CLCD_2023_Anji_5class.tif"),

  [string] $SagaCmd = $env:SAGA_CMD,

  [int] $IoGdalImportRaster = 0,
  [int] $IoGdalExportRaster = 1,
  [int] $IoGdalExportFormat = 12,
  [int] $ReclassifyTool = 15,

  [switch] $WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-SagaCmd {
  param([string] $Candidate)
  if ($Candidate -and (Test-Path -LiteralPath $Candidate)) { return (Resolve-Path -LiteralPath $Candidate).Path }

  $search = @(
    "D:\download\SAGA 9.12.0\saga_cmd.exe"
    (Join-Path ${env:ProgramFiles} "SAGA-GIS-9.12.0\saga_cmd.exe")
    (Join-Path ${env:ProgramFiles} "SAGA-GIS\saga_cmd.exe")
    "C:\OSGeo4W64\bin\saga_cmd.exe"
  )
  foreach ($p in $search) {
    if (Test-Path -LiteralPath $p) { return (Resolve-Path -LiteralPath $p).Path }
  }
  return $null
}

function Invoke-Saga {
  param(
    [Parameter(Mandatory)] [string] $Exe,
    [Parameter(Mandatory)] [string[]] $Args
  )
  Write-Host (">> saga_cmd " + ($Args -join " "))
  if ($WhatIf) { return }
  $prevEa = $ErrorActionPreference
  $ErrorActionPreference = "SilentlyContinue"
  try {
    & $Exe @Args
    $exit = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $prevEa
  }
  if ($exit -ne 0) {
    throw "saga_cmd failed (exit $exit). Command: saga_cmd $($Args -join ' ')"
  }
}

function Invoke-ReclassSingle {
  param(
    [string] $Exe,
    [string] $InputGrid,
    [string] $OutputGrid,
    [double] $OldValue,
    [double] $NewValue
  )
  Invoke-Saga $Exe @(
    "grid_tools", "$ReclassifyTool"
    "-INPUT", $InputGrid
    "-RESULT", $OutputGrid
    "-METHOD", "0"
    "-OLD", "$OldValue"
    "-NEW", "$NewValue"
    "-SOPERATOR", "0"
  )
}

$sagaExe = Resolve-SagaCmd $SagaCmd
if (-not $sagaExe) {
  throw "Could not find saga_cmd.exe. Set -SagaCmd or env:SAGA_CMD (e.g. D:\download\SAGA 9.12.0\saga_cmd.exe)."
}
if (-not (Test-Path -LiteralPath $InputTif)) { throw "Input raster not found: $InputTif" }

# Order matters: convert source codes before they become targets of later steps.
# Example: 5->4 must run before 4->3, otherwise water (4) is turned into grassland (3).
$reclassSteps = @(
  @{ Old = 3; New = 2 }  # shrub -> forest
  @{ Old = 4; New = 3 }  # grassland
  @{ Old = 5; New = 4 }  # water
  @{ Old = 6; New = 5 }  # bare land -> residential/built-up
  @{ Old = 7; New = 3 }  # snow/ice -> grassland (rare, fallback)
  @{ Old = 9; New = 4 }  # wetland -> water
  @{ Old = 8; New = 5 }  # impervious -> residential
)

$tmp = Join-Path $WorkDir ("_saga_reclass_" + [Guid]::NewGuid().ToString("N"))
if (-not $WhatIf) { New-Item -ItemType Directory -Path $tmp | Out-Null }

$gridImported = Join-Path $tmp "lulc_in"
$gridA = Join-Path $tmp "lulc_a"
$gridB = Join-Path $tmp "lulc_b"

try {
  Push-Location $tmp
  try {
    Invoke-Saga $sagaExe @(
      "io_gdal", "$IoGdalImportRaster"
      "-FILES", $InputTif
      "-GRIDS", $gridImported
    )

    $srcBase = $gridImported
    $dstBase = $gridA
    foreach ($rule in $reclassSteps) {
      Invoke-ReclassSingle -Exe $sagaExe -InputGrid "$srcBase.sg-grd-z" -OutputGrid $dstBase -OldValue $rule.Old -NewValue $rule.New
      $srcBase, $dstBase = $dstBase, $srcBase
    }
    $gridFinalSg = "$srcBase.sg-grd-z"

    if (Test-Path -LiteralPath $OutputTif) { Remove-Item -LiteralPath $OutputTif -Force }

    Invoke-Saga $sagaExe @(
      "io_gdal", "$IoGdalExportRaster"
      "-GRIDS", $gridFinalSg
      "-FILE", $OutputTif
      "-FORMAT", "$IoGdalExportFormat"
    )
  }
  finally {
    Pop-Location
  }

  Write-Host ""
  Write-Host "Reclassification complete."
  Write-Host "  Input : $InputTif"
  Write-Host "  Output: $OutputTif"
  Write-Host "  Classes: 1=耕地 2=林地 3=草地 4=水域 5=居民用地"
}
finally {
  if (-not $WhatIf -and (Test-Path -LiteralPath $tmp)) {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
  }
}
