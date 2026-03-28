# pixel_pet_ai

This project slices the pixel cat sprite sheets in `PACK/PACK` into individual frames and exports each row as a GIF animation.

## Current Asset Layout

The files `cat 1 (64х64).png`, `cat 2 (64х64).png`, and `cat 3 (64х64).png` are all 64x64 sprite sheets.
Each sheet contains 14 columns and 72 rows, so every row is exported as a separate animation.

## Export Command

```powershell
powershell -ExecutionPolicy Bypass -File scripts\export-gifs.ps1 -ExportFrames
```

If you only want GIF files and do not want to keep the extracted PNG frames:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\export-gifs.ps1
```

## Naming Rules

Animation names come from `scripts/animation-names.json`.
After export, folders use the `index-slug` format, for example:

- `asset/export/cat-1-64-64/02-walk-down/animation.gif`
- `asset/export/cat-1-64-64/06-sit/animation.gif`
- `asset/export/cat-1-64-64/56-eat-food-stand-front/animation.gif`

`manifest.json` also stores:

- `row`: original row index
- `label`: human-readable animation name
- `slug`: code-friendly animation name
- `directory`: actual exported folder name
- `frames`: frame count for that row

The actions visible in the reference sheet have been mapped to readable names.
The last 6 rows are transparent empty rows and are currently labeled `unused-empty-01` through `unused-empty-06`.

## Output Directory

Exported files are written to `asset/export`:

- `asset/export/cat-1-64-64/02-walk-down/animation.gif`
- `asset/export/cat-1-64-64/02-walk-down/frame-01.png`
- `asset/export/cat-1-64-64/manifest.json`

`animation.gif` is the row animation, `frame-*.png` contains the extracted frames, and `manifest.json` records row numbers, action names, frame counts, and folder names.

## Configurable Parameters

```powershell
powershell -ExecutionPolicy Bypass -File scripts\export-gifs.ps1 -CellSize 64 -Fps 8 -ExportFrames
```

Available parameters:

- `-SourceDir`: source asset directory
- `-OutputDir`: export directory
- `-NamesPath`: animation naming table path
- `-CellSize`: frame size, default `64`
- `-Fps`: GIF frame rate, default `8`
- `-ExportFrames`: keep extracted PNG frames in addition to GIFs
