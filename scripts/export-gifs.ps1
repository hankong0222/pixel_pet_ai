param(
  [string]$SourceDir = (Join-Path $PSScriptRoot '..\PACK\PACK'),
  [string]$OutputDir = (Join-Path $PSScriptRoot '..\asset\export'),
  [string]$NamesPath = (Join-Path $PSScriptRoot 'animation-names.json'),
  [int]$CellSize = 64,
  [int]$Fps = 8,
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
  $blankFrames = @()

  foreach ($frameFile in $frameFiles) {
    if (Test-FrameHasVisiblePixels -Path $frameFile.FullName) {
      $visibleFrames += $frameFile
    }
    else {
      $blankFrames += $frameFile
    }
  }

  if (-not $visibleFrames) {
    $visibleFrames = @($frameFiles[0])
    if ($frameFiles.Count -gt 1) {
      $blankFrames = @($frameFiles[1..($frameFiles.Count - 1)])
    }
  }

  foreach ($blankFrame in $blankFrames) {
    Remove-Item $blankFrame.FullName -Force
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
    RemovedBlankFrames = $blankFrames.Count
  }
}

function Get-SafeName {
  param([string]$Name)

  $baseName = [System.IO.Path]::GetFileNameWithoutExtension($Name)
  $safeName = [System.Text.RegularExpressions.Regex]::Replace($baseName, '[^A-Za-z0-9]+', '-')
  return $safeName.Trim('-').ToLowerInvariant()
}

function Invoke-Ffmpeg {
  param([string[]]$FfmpegArgs)

  & ffmpeg -y -loglevel error @FfmpegArgs
  if ($LASTEXITCODE -ne 0) {
    throw "ffmpeg failed: $($FfmpegArgs -join ' ')"
  }
}

$animationNames = Get-Content $NamesPath -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$sprites = Get-ChildItem -Path $SourceDir -Filter 'cat *.png' | Sort-Object Name
if (-not $sprites) {
  throw "No sprite sheets found in $SourceDir"
}

foreach ($sprite in $sprites) {
  $size = Get-PngSize -Path $sprite.FullName
  if (($size.Width % $CellSize) -ne 0 -or ($size.Height % $CellSize) -ne 0) {
    throw "$($sprite.Name) is not divisible by $CellSize"
  }

  $columns = [int]($size.Width / $CellSize)
  $rows = [int]($size.Height / $CellSize)
  if ($animationNames.Count -lt $rows) {
    throw "animation-names.json only contains $($animationNames.Count) names, but $($sprite.Name) has $rows rows"
  }

  $spriteOutputDir = Join-Path $OutputDir (Get-SafeName -Name $sprite.Name)
  $spriteCopyPath = Join-Path $spriteOutputDir 'source.png'

  if (Test-Path $spriteOutputDir) {
    Remove-Item $spriteOutputDir -Recurse -Force
  }

  New-Item -ItemType Directory -Force -Path $spriteOutputDir | Out-Null
  Copy-Item -Path $sprite.FullName -Destination $spriteCopyPath -Force

  $manifest = [ordered]@{
    source = $sprite.Name
    cellSize = $CellSize
    columns = $columns
    rows = $rows
    fps = $Fps
    animations = @()
  }

  for ($rowIndex = 0; $rowIndex -lt $rows; $rowIndex++) {
    $nameEntry = $animationNames[$rowIndex]
    $folderName = ('{0:d2}-{1}' -f $rowIndex, $nameEntry.slug)
    $rowDir = Join-Path $spriteOutputDir $folderName
    $framesDir = Join-Path $rowDir '_frames'
    $stripPath = Join-Path $framesDir 'row-strip.png'
    $framePattern = Join-Path $framesDir 'frame-%02d.png'
    $gifPath = Join-Path $rowDir 'animation.gif'
    $y = $rowIndex * $CellSize

    $animationEntry = [ordered]@{
      row = $rowIndex
      label = $nameEntry.label
      slug = $nameEntry.slug
      directory = $folderName
      frames = $columns
      removedBlankFrames = 0
    }

    New-Item -ItemType Directory -Force -Path $framesDir | Out-Null

    Invoke-Ffmpeg -FfmpegArgs @(
      '-i', $spriteCopyPath,
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

    $filteredFrames = Get-FilteredFrameFiles -FramesDir $framesDir
    $animationEntry.frames = $filteredFrames.VisibleFrameCount
    $animationEntry.removedBlankFrames = $filteredFrames.RemovedBlankFrames

    Invoke-Ffmpeg -FfmpegArgs @(
      '-framerate', "$Fps",
      '-i', (Join-Path $filteredFrames.FrameDir 'frame-%02d.png'),
      '-filter_complex', 'split[a][b];[a]palettegen=reserve_transparent=1[p];[b][p]paletteuse=dither=bayer:bayer_scale=3',
      '-loop', '0',
      $gifPath
    )

    $manifest.animations += $animationEntry

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

  $manifest | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $spriteOutputDir 'manifest.json') -Encoding utf8
  Write-Host "Exported $rows animations from $($sprite.Name) to $spriteOutputDir"
}
