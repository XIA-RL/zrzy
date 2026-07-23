<#.SYNOPSIS
  Clip Zhejiang LULC raster to Anji County using SAGA saga_cmd (SAGA 9.x).

.DESCRIPTION
  1) Import raster (io_gdal) and county boundaries (io_gdal Import Shapes).
  2) Select the county feature by string attribute (shapes_tools).
  3) Project the selected polygon to the raster CRS (pj_proj4) using the raster's embedded `.prj`.
  4) Clip grid with polygon (shapes_grid) and export GeoTIFF (io_gdal).

  County polygons are often WGS84 geographic while CLCD GeoTIFFs are commonly projected (for example
  Albers China). Without a CRS alignment step, clipping can fail or produce empty output.

  Tool indices can differ slightly between SAGA 9.x builds. This script tries to
  auto-detect "Clip Grid with Polygon" from `saga_cmd shapes_grid` output; you can
  override with -ClipToolIndex (use -1 for auto-detect).

  IMPORTANT: ESRI Shapefiles require sidecar files next to the .shp:
  .dbf, .shx, and preferably .prj. Without them, SAGA cannot read attributes or geometry.

  IMPORTANT: "Clip Grid with Polygon" requires polygon/multipolygon features. If you keep
  both line and poly shapefiles in the folder (e.g. BOUNT_line.shp and BOUNT_poly.shp), the
  default picker prefers basenames containing 'poly'. For line-only boundaries, pass a
  polygon layer with -CountyShpPath or use a different masking workflow.

.PARAMETER SagaCmd
  Full path to saga_cmd.exe. If omitted, uses env SAGA_CMD, then common install paths.

.EXAMPLE
  .\clip_anji_saga.ps1 -NameField "NAME"

.EXAMPLE
  .\clip_anji_saga.ps1 -ListTools
#>
[CmdletBinding()]
param(
  # Script directory (works with -File); falls back to cwd if unavailable.
  [string] $WorkDir = $(if ($PSScriptRoot) { $PSScriptRoot } elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { (Get-Location).Path }),

  [string] $RasterPath = (Join-Path $WorkDir "CLCD_v01_2023_albert_zhejiang.tif"),

  [string] $CountyShpPath = "",

  [string] $OutputTif = (Join-Path $WorkDir "CLCD_2023_Anji.tif"),

  # Default: Anji County (UTF-16 code units avoid encoding issues when the script file is not UTF-8 with BOM).
  [string] $CountyName = "$([char]0x5B89)$([char]0x5409)$([char]0x53BF)",

  [string] $NameField = "NAME99",

  [string] $SagaCmd = $env:SAGA_CMD,

  [ValidateSet("Equals", "Contains")]
  [string] $NameMatch = "Equals",

  # Use -1 to auto-detect "Clip Grid with Polygon" from `saga_cmd shapes_grid` output.
  [int] $ClipToolIndex = -1,

  [int] $IoGdalImportRaster = 0,
  [int] $IoGdalExportRaster = 1,
  # GDAL driver choice for Export Raster (SAGA 9.12.0: [12] = GeoTIFF).
  [int] $IoGdalExportFormat = 12,
  [int] $IoGdalImportShapes = 3,
  [int] $ShapesToolsSelectString = 4,
  [int] $PjProjSetCrs = 0,
  [int] $PjProjTransformShapes = 2,

  # CRS assigned to the selected county shapefile before reprojection (typical for unprojected GADM-like data).
  [string] $CountySourceCrs = "EPSG:4326",

  [switch] $ListTools,
  [switch] $WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-SagaCmd {
  param([string] $Candidate)
  if ($Candidate -and (Test-Path -LiteralPath $Candidate)) { return (Resolve-Path -LiteralPath $Candidate).Path }

  $search = @(
    "D:\download\SAGA 9.12.0\saga_cmd.exe"
    Join-Path ${env:ProgramFiles} "SAGA-GIS-9.12.0\saga_cmd.exe"
    Join-Path ${env:ProgramFiles} "SAGA-GIS-9.1.2\saga_cmd.exe"
    Join-Path ${env:ProgramFiles} "SAGA-GIS-9.1.2.0\saga_cmd.exe"
    Join-Path ${env:ProgramFiles} "SAGA-GIS\saga_cmd.exe"
    Join-Path ${env:ProgramFiles} "SAGA\saga_cmd.exe"
    "C:\OSGeo4W64\bin\saga_cmd.exe"
    "C:\OSGeo4W\bin\saga_cmd.exe"
  )
  foreach ($p in $search) {
    if (Test-Path -LiteralPath $p) { return (Resolve-Path -LiteralPath $p).Path }
  }
  return $null
}

function Find-DefaultCountyShp {
  param([string] $Dir)
  $all = @(Get-ChildItem -LiteralPath $Dir -Filter "*.shp" -File -ErrorAction SilentlyContinue | Sort-Object Name)
  if ($all.Count -eq 0) { throw "No .shp found under: $Dir" }

  # Prefer polygon layers (e.g. BOUNT_poly.shp) when both line and poly bundles exist.
  $polyLike = $all | Where-Object { $_.BaseName -match "(?i)poly" } | Select-Object -First 1
  if ($polyLike) { return $polyLike.FullName }

  if ($all.Count -gt 1) {
    throw (
      "Multiple .shp files found in $Dir but none matched '*poly*' in the basename. " +
      "Pass the polygon layer explicitly, e.g. -CountyShpPath (Join-Path '$Dir' 'BOUNT_poly.shp')."
    )
  }
  return $all[0].FullName
}

function Assert-ShapefileSidecars {
  param([string] $ShpPath)
  $dir = Split-Path -Parent $ShpPath
  $stem = [System.IO.Path]::GetFileNameWithoutExtension($ShpPath)
  $need = @(".dbf", ".shx")
  $missing = @()
  foreach ($ext in $need) {
    $side = Join-Path $dir ($stem + $ext)
    if (-not (Test-Path -LiteralPath $side)) { $missing += $side }
  }
  if ($missing.Count -gt 0) {
    throw (
      "Incomplete shapefile. Missing files:`n" +
      ($missing -join [Environment]::NewLine) +
      "`nWithout a .dbf, SAGA cannot read attributes. Without a .shx, the spatial index is missing."
    )
  }
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

function Get-SagaLibraryListing {
  param([Parameter(Mandatory)] [string] $Exe, [Parameter(Mandatory)] [string] $Library)
  if ($WhatIf) { return "" }
  $prevEa = $ErrorActionPreference
  $ErrorActionPreference = "SilentlyContinue"
  try {
    $raw = & $Exe $Library 2>&1 | ForEach-Object { $_.ToString() }
    return ($raw -join [Environment]::NewLine)
  }
  finally {
    $ErrorActionPreference = $prevEa
  }
}

function Export-RasterCrsPrjFromSagaGrid {
  param(
    [Parameter(Mandatory)] [string] $SgGrdZPath,
    [Parameter(Mandatory)] [string] $GridDatasetBasePath,
    [Parameter(Mandatory)] [string] $DestPrjPath
  )
  if (-not (Test-Path -LiteralPath $SgGrdZPath)) {
    throw "Expected SAGA grid archive not found: $SgGrdZPath"
  }
  $stem = [System.IO.Path]::GetFileName($GridDatasetBasePath)
  $entryName = "$stem.prj"
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $zip = [System.IO.Compression.ZipFile]::OpenRead($SgGrdZPath)
  try {
    $entry = $zip.GetEntry($entryName)
    if (-not $entry) {
      throw "Could not find '$entryName' inside '$SgGrdZPath'. Grid dataset base was: $GridDatasetBasePath"
    }
    $entryStream = $entry.Open()
    try {
      $outStream = [System.IO.File]::Create($DestPrjPath)
      try {
        $entryStream.CopyTo($outStream)
      }
      finally {
        $outStream.Close()
      }
    }
    finally {
      $entryStream.Close()
    }
  }
  finally {
    $zip.Dispose()
  }
}

function Find-ToolIndexByName {
  param(
    [Parameter(Mandatory)] [string] $Listing,
    [Parameter(Mandatory)] [string] $Pattern
  )
  foreach ($line in ($Listing -split "`r?`n")) {
    $idx = $null
    $name = $null
    if ($line -match '^\s*\[(\d+)\]\s+(.+?)\s*$') {
      $idx = [int]$Matches[1]
      $name = $Matches[2]
    }
    elseif ($line -match '^\s*(\d+)\s*-\s*(.+)$') {
      $idx = [int]$Matches[1]
      $name = $Matches[2]
    }
    if ($null -ne $idx -and $name -match $Pattern) { return $idx }
  }
  return $null
}

$sagaExe = Resolve-SagaCmd $SagaCmd
if (-not $sagaExe) {
  throw "Could not find saga_cmd.exe. Install SAGA 9.x or set -SagaCmd / env:SAGA_CMD to the full path."
}

if ($ListTools) {
  Write-Host "Using: $sagaExe"
  Write-Host "---- io_gdal ----"
  Write-Host (Get-SagaLibraryListing -Exe $sagaExe -Library "io_gdal")
  Write-Host "---- shapes_tools ----"
  Write-Host (Get-SagaLibraryListing -Exe $sagaExe -Library "shapes_tools")
  Write-Host "---- shapes_grid ----"
  Write-Host (Get-SagaLibraryListing -Exe $sagaExe -Library "shapes_grid")
  Write-Host ""
  Write-Host "Tip: if tool numbers differ from the defaults in this script, re-run with:"
  Write-Host "  -IoGdalImportRaster / -IoGdalImportShapes / -IoGdalExportRaster / -IoGdalExportFormat"
  Write-Host "  -ShapesToolsSelectString / -ClipToolIndex / -CountySourceCrs / -PjProjSetCrs / -PjProjTransformShapes"
  return
}

if (-not $CountyShpPath) {
  $CountyShpPath = Find-DefaultCountyShp $WorkDir
}

if (-not (Test-Path -LiteralPath $RasterPath)) { throw "Raster not found: $RasterPath" }
if (-not (Test-Path -LiteralPath $CountyShpPath)) { throw "County shapefile not found: $CountyShpPath" }

if ([System.IO.Path]::GetExtension($CountyShpPath).ToLowerInvariant() -eq ".shp") {
  Assert-ShapefileSidecars -ShpPath $CountyShpPath
}

$clipIdx =
  if ($ClipToolIndex -ge 0) {
    $ClipToolIndex
  }
  else {
    $shapesGridListing = Get-SagaLibraryListing -Exe $sagaExe -Library "shapes_grid"
    Find-ToolIndexByName -Listing $shapesGridListing -Pattern "Clip Grid with Polygon"
  }
if ($null -eq $clipIdx) {
  throw (
    "Could not auto-detect Clip Grid with Polygon from saga_cmd shapes_grid. " +
    "Run: .\clip_anji_saga.ps1 -ListTools then pass -ClipToolIndex (e.g. 7 for SAGA 9.12.0)."
  )
}

$tmp = Join-Path $WorkDir ("_saga_work_" + [Guid]::NewGuid().ToString("N"))
if (-not $WhatIf) {
  New-Item -ItemType Directory -Path $tmp | Out-Null
}

$gridImported = Join-Path $tmp "lulc"
$gridSgGrdZ = "$gridImported.sg-grd-z"
$gridRasterCrsPrj = Join-Path $tmp "lulc_raster.prj"
$shpImportedBase = Join-Path $tmp "counties"
$shpImported = "$shpImportedBase.shp"
$shpSelectedBase = Join-Path $tmp "anji"
$shpSelected = "$shpSelectedBase.shp"
$shpProjectedBase = Join-Path $tmp "anji_proj"
$shpProjected = "$shpProjectedBase.shp"
$gridClipped = Join-Path $tmp "lulc_anji"
$gridClippedSgGrdZ = "$gridClipped.sg-grd-z"

try {
  Push-Location $tmp
  try {
    Invoke-Saga $sagaExe @(
      "io_gdal", "$IoGdalImportRaster"
      "-FILES", $RasterPath
      "-GRIDS", $gridImported
    )

    if (-not $WhatIf) {
      Export-RasterCrsPrjFromSagaGrid -SgGrdZPath $gridSgGrdZ -GridDatasetBasePath $gridImported -DestPrjPath $gridRasterCrsPrj
    }

    Invoke-Saga $sagaExe @(
      "io_gdal", "$IoGdalImportShapes"
      "-FILES", $CountyShpPath
      "-SHAPES", $shpImportedBase
    )

    $compareCode = if ($NameMatch -eq "Contains") { "1" } else { "0" }

    # SAGA 9.12 string selection: COMPARE [0]=identical, [1]=contains, [2]=contained-in. CASE is boolean (0=false).
    # Export selected features via POSTJOB=1 (copy). CLI workflows cannot rely on in-memory selection for a separate copy step.
    Invoke-Saga $sagaExe @(
      "shapes_tools", "$ShapesToolsSelectString"
      "-SHAPES", $shpImported
      "-FIELD", $NameField
      "-EXPRESSION", $CountyName
      "-CASE", "0"
      "-COMPARE", $compareCode
      "-METHOD", "0"
      "-POSTJOB", "1"
      "-COPY", $shpSelectedBase
    )

    Invoke-Saga $sagaExe @(
      "pj_proj4", "$PjProjSetCrs"
      "-SHAPES", $shpSelected
      "-CRS_STRING", $CountySourceCrs
    )

    Invoke-Saga $sagaExe @(
      "pj_proj4", "$PjProjTransformShapes"
      "-SOURCE", $shpSelected
      "-TARGET", $shpProjectedBase
      "-CRS_FILE", $gridRasterCrsPrj
      "-TRANSFORM_Z", "0"
    )

    # EXTENT: 1 = target extent from polygons (typical for clipping/masking)
    Invoke-Saga $sagaExe @(
      "shapes_grid", "$clipIdx"
      "-INPUT", $gridSgGrdZ
      "-POLYGONS", $shpProjected
      "-OUTPUT", $gridClipped
      "-EXTENT", "1"
    )

    if (Test-Path -LiteralPath $OutputTif) {
      Remove-Item -LiteralPath $OutputTif -Force
    }

    Invoke-Saga $sagaExe @(
      "io_gdal", "$IoGdalExportRaster"
      "-GRIDS", $gridClippedSgGrdZ
      "-FILE", $OutputTif
      "-FORMAT", "$IoGdalExportFormat"
    )
  }
  finally {
    Pop-Location
  }

  Write-Host ""
  Write-Host "Done. Output: $OutputTif"
}
finally {
  if (-not $WhatIf -and (Test-Path -LiteralPath $tmp)) {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
  }
}
