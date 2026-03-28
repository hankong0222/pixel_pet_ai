param(
  [string]$SourceDir = (Join-Path $PSScriptRoot '..\PACK\PACK'),
  [string]$OutputDir = (Join-Path $PSScriptRoot '..\asset\export'),
  [string]$NamesPath = (Join-Path $PSScriptRoot 'animation-names.json'),
  [int]$CellSize = 64,
  [int]$Fps = 8,
  [switch]$ExportFrames
)

$ErrorActionPreference = 'Stop'

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

    $manifest.animations += [ordered]@{
      row = $rowIndex
      label = $nameEntry.label
      slug = $nameEntry.slug
      directory = $folderName
      frames = $columns
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

    Invoke-Ffmpeg -FfmpegArgs @(
      '-framerate', "$Fps",
      '-i', (Join-Path $framesDir 'frame-%02d.png'),
      '-filter_complex', 'split[a][b];[a]palettegen=reserve_transparent=1[p];[b][p]paletteuse=dither=bayer:bayer_scale=3',
      '-loop', '0',
      $gifPath
    )

    Remove-Item $stripPath -Force

    if ($ExportFrames) {
      Get-ChildItem -Path $framesDir -Filter 'frame-*.png' | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination (Join-Path $rowDir $_.Name) -Force
      }
    }

    Remove-Item $framesDir -Recurse -Force
  }

  $manifest | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $spriteOutputDir 'manifest.json')
  Write-Host "Exported $rows animations from $($sprite.Name) to $spriteOutputDir"
}

