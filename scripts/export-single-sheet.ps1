param(
  [Parameter(Mandatory = $true)]
  [string]$InputImage,
  [Parameter(Mandatory = $true)]
  [string]$OutputDir,
  [int]$CellSize = 64,
  [int]$Fps = 8,
  [int]$FrameInset = 0,
  [string]$TransparentColor,
  [double]$TransparentSimilarity = 0.07,
  [double]$TransparentBlend = 0.01,
  [switch]$ExportFrames
)

$ErrorActionPreference = 'Stop'
$MinimumVisiblePixels = 30

Add-Type -AssemblyName System.Drawing

function Get-PngSize {
  param([string]$Path)

  $image = [System.Drawing.Image]::FromFile($Path)
  try {
    return @{
      Width = $image.Width
      Height = $image.Height
    }
  }
  finally {
    $image.Dispose()
  }
}

function Test-FrameHasVisiblePixels {
  param([string]$Path)

  $bitmap = [System.Drawing.Bitmap]::new($Path)
  try {
    $visiblePixels = 0
    for ($x = 0; $x -lt $bitmap.Width; $x++) {
      for ($y = 0; $y -lt $bitmap.Height; $y++) {
        if ($bitmap.GetPixel($x, $y).A -gt 0) {
          $visiblePixels++
          if ($visiblePixels -ge $MinimumVisiblePixels) {
            return $true
          }
        }
      }
    }
    return $false
  }
  finally {
    $bitmap.Dispose()
  }
}

function Get-FilteredFrameFiles {
  param([string]$FramesDir)

  $frameFiles = @(Get-ChildItem -Path $FramesDir -Filter 'frame-*.png' | Sort-Object Name)
  if (-not $frameFiles) {
    throw "No extracted frames found in $FramesDir"
  }

  $visibleFrames = @()
  foreach ($frameFile in $frameFiles) {
    if (Test-FrameHasVisiblePixels -Path $frameFile.FullName) {
      $visibleFrames += $frameFile
    }
  }

  if (-not $visibleFrames) {
    $visibleFrames = @($frameFiles[0])
  }

  $filteredDir = Join-Path $FramesDir '_filtered'
  if (Test-Path $filteredDir) {
    Remove-Item $filteredDir -Recurse -Force
  }
  New-Item -ItemType Directory -Force -Path $filteredDir | Out-Null

  for ($index = 0; $index -lt $visibleFrames.Count; $index++) {
    $destination = Join-Path $filteredDir ('frame-{0:d2}.png' -f ($index + 1))
    Copy-Item -Path $visibleFrames[$index].FullName -Destination $destination -Force
  }

  return @{
    FrameDir = $filteredDir
    VisibleFrameCount = $visibleFrames.Count
    RemovedBlankFrames = $frameFiles.Count - $visibleFrames.Count
  }
}

function Invoke-Ffmpeg {
  param([string[]]$FfmpegArgs)

  & ffmpeg -y -loglevel error @FfmpegArgs
  if ($LASTEXITCODE -ne 0) {
    throw "ffmpeg failed: $($FfmpegArgs -join ' ')"
  }
}

function Optimize-Frame {
  param(
    [string]$Path,
    [int]$CellSize,
    [int]$FrameInset,
    [string]$TransparentColor,
    [double]$TransparentSimilarity,
    [double]$TransparentBlend
  )

  $filters = @()

  if ($FrameInset -gt 0) {
    $innerSize = $CellSize - ($FrameInset * 2)
    if ($innerSize -le 0) {
      throw "FrameInset $FrameInset is too large for CellSize $CellSize"
    }

    $filters += "crop=$innerSize`:$innerSize`:$FrameInset`:$FrameInset"
  }

  if ($TransparentColor) {
    $filters += 'format=rgba'
    $filters += "colorkey=$TransparentColor`:$TransparentSimilarity`:$TransparentBlend"
  }

  if ($FrameInset -gt 0) {
    $filters += "pad=$CellSize`:$CellSize`:$FrameInset`:$FrameInset`:color=black@0"
  }

  if (-not $filters) {
    return
  }

  $tempPath = Join-Path ([System.IO.Path]::GetDirectoryName($Path)) ([System.IO.Path]::GetFileNameWithoutExtension($Path) + '.optimized.png')
  Invoke-Ffmpeg -FfmpegArgs @(
    '-i', $Path,
    '-vf', ($filters -join ','),
    '-frames:v', '1',
    '-update', '1',
    $tempPath
  )

  Move-Item -Path $tempPath -Destination $Path -Force
}

$size = Get-PngSize -Path $InputImage
if (($size.Width % $CellSize) -ne 0 -or ($size.Height % $CellSize) -ne 0) {
  throw "$InputImage is not divisible by $CellSize"
}

$columns = [int]($size.Width / $CellSize)
$rows = [int]($size.Height / $CellSize)

if (Test-Path $OutputDir) {
  Remove-Item $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$manifest = [ordered]@{
  source = [System.IO.Path]::GetFileName($InputImage)
  cellSize = $CellSize
  columns = $columns
  rows = $rows
  fps = $Fps
  frameInset = $FrameInset
  transparentColor = $TransparentColor
  animations = @()
}

for ($rowIndex = 0; $rowIndex -lt $rows; $rowIndex++) {
  $folderName = ('row-{0:d2}' -f $rowIndex)
  $rowDir = Join-Path $OutputDir $folderName
  $framesDir = Join-Path $rowDir '_frames'
  $stripPath = Join-Path $framesDir 'row-strip.png'
  $framePattern = Join-Path $framesDir 'frame-%02d.png'
  $gifPath = Join-Path $rowDir 'animation.gif'
  $y = $rowIndex * $CellSize

  New-Item -ItemType Directory -Force -Path $framesDir | Out-Null

  Invoke-Ffmpeg -FfmpegArgs @(
    '-i', $InputImage,
    '-vf', ([string]::Format('crop={0}:{1}:0:{2}', ($columns * $CellSize), $CellSize, $y)),
    '-frames:v', '1',
    '-update', '1',
    $stripPath
  )

  Invoke-Ffmpeg -FfmpegArgs @(
    '-i', $stripPath,
    '-vf', "untile=$columns`x1",
    $framePattern
  )

  Get-ChildItem -Path $framesDir -Filter 'frame-*.png' | ForEach-Object {
    Optimize-Frame -Path $_.FullName `
      -CellSize $CellSize `
      -FrameInset $FrameInset `
      -TransparentColor $TransparentColor `
      -TransparentSimilarity $TransparentSimilarity `
      -TransparentBlend $TransparentBlend
  }

  $filteredFrames = Get-FilteredFrameFiles -FramesDir $framesDir

  Invoke-Ffmpeg -FfmpegArgs @(
    '-framerate', "$Fps",
    '-i', (Join-Path $filteredFrames.FrameDir 'frame-%02d.png'),
    '-filter_complex', 'split[a][b];[a]palettegen=reserve_transparent=1[p];[b][p]paletteuse=dither=bayer:bayer_scale=3',
    '-loop', '0',
    $gifPath
  )

  $manifest.animations += [ordered]@{
    row = $rowIndex
    directory = $folderName
    frames = $filteredFrames.VisibleFrameCount
    removedBlankFrames = $filteredFrames.RemovedBlankFrames
  }

  if (Test-Path $stripPath) {
    Remove-Item $stripPath -Force
  }

  if ($ExportFrames) {
    Get-ChildItem -Path $filteredFrames.FrameDir -Filter 'frame-*.png' | ForEach-Object {
      Copy-Item -Path $_.FullName -Destination (Join-Path $rowDir $_.Name) -Force
    }
  }

  Remove-Item $framesDir -Recurse -Force
}

$manifest | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $OutputDir 'manifest.json') -Encoding utf8
Write-Host "Exported $rows animations from $InputImage to $OutputDir"
