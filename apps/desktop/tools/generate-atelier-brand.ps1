[CmdletBinding()]
param([string]$ResourcesDirectory = (Join-Path $PSScriptRoot '../resources'))
# Géométrie pixel originale ACP. Aucun pixel LimeZu ni d’un autre tiers n’est utilisé.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
$ResourcesDirectory=[IO.Path]::GetFullPath($ResourcesDirectory)
$icons=Join-Path $ResourcesDirectory 'icons'
$images=Join-Path $ResourcesDirectory 'images'
New-Item -ItemType Directory -Path $icons,$images -Force | Out-Null
$glyph=@(@(0,1,2,1),@(1,2,2,1),@(2,3,2,1),@(3,1,4,1),@(3,2,1,2),@(6,2,1,2),@(3,4,4,1),@(6,3,2,1),@(7,2,2,1),@(8,1,2,1))
function New-Graphics($bitmap) {
    $g=[Drawing.Graphics]::FromImage($bitmap)
    $g.InterpolationMode=[Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
    $g.PixelOffsetMode=[Drawing.Drawing2D.PixelOffsetMode]::Half
    $g.SmoothingMode=[Drawing.Drawing2D.SmoothingMode]::None
    return $g
}
function Paint($g,[string]$hex,[int]$x,[int]$y,[int]$w,[int]$h) {
    $brush=[Drawing.SolidBrush]::new([Drawing.ColorTranslator]::FromHtml($hex))
    try {$g.FillRectangle($brush,$x,$y,$w,$h)}finally{$brush.Dispose()}
}
function Paint-Glyph($g,[int]$x,[int]$y,[int]$scale,[string]$color='#9B8BC6') {
    foreach($r in $glyph) {Paint $g $color ($x+$r[0]*$scale) ($y+$r[1]*$scale) ($r[2]*$scale) ($r[3]*$scale)}
}
function Save-Png($bitmap,[string]$path){$bitmap.Save($path,[Drawing.Imaging.ImageFormat]::Png)}
$svgRects=foreach($r in $glyph){'  <rect x="{0}" y="{1}" width="{2}" height="{3}"/>' -f ($r[0]+1),($r[1]+1),$r[2],$r[3]}
$svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 9" shape-rendering="crispEdges" fill="#9B8BC6">' + "`n" + ($svgRects -join "`n") + "`n</svg>`n"
[IO.File]::WriteAllText((Join-Path $icons 'acp-atelier.svg'),$svg)
$frames=[Collections.Generic.List[object]]::new()
foreach($size in @(16,24,32,48,64,128,256)) {
    $bitmap=[Drawing.Bitmap]::new($size,$size);$g=New-Graphics $bitmap
    $scale=[Math]::Max(1,[Math]::Floor($size/12))
    Paint-Glyph $g ([Math]::Floor(($size-10*$scale)/2)) ([Math]::Floor(($size-7*$scale)/2)) $scale
    $g.Dispose()
    if($size -eq 256){Save-Png $bitmap (Join-Path $icons 'acp-atelier.png')}
    $memory=[IO.MemoryStream]::new()
    $bitmap.Save($memory,[Drawing.Imaging.ImageFormat]::Png)
    $frames.Add(@{size=$size;bytes=$memory.ToArray()})
    $memory.Dispose();$bitmap.Dispose()
}
$stream=[IO.File]::Create((Join-Path $icons 'acp-atelier.ico'))
$writer=[IO.BinaryWriter]::new($stream)
try {
    $writer.Write([uint16]0);$writer.Write([uint16]1);$writer.Write([uint16]$frames.Count)
    $offset=6+16*$frames.Count
    foreach($frame in $frames) {
        $dimension=if($frame.size -eq 256){0}else{$frame.size}
        $writer.Write([byte]$dimension);$writer.Write([byte]$dimension)
        $writer.Write([byte]0);$writer.Write([byte]0)
        $writer.Write([uint16]1);$writer.Write([uint16]32)
        $writer.Write([uint32]$frame.bytes.Length);$writer.Write([uint32]$offset)
        $offset+=$frame.bytes.Length
    }
    foreach($frame in $frames){$writer.Write([byte[]]$frame.bytes)}
} finally {$writer.Dispose();$stream.Dispose()}

# Hand-authored geometric studio fallback, deliberately distinct from licensed art.
$scene=[Drawing.Bitmap]::new(240,120);$g=New-Graphics $scene
Paint $g '#D6D0C0' 24 103 192 7
Paint $g '#ACBA9A' 20 17 200 88
Paint $g '#C5D0B4' 22 19 196 34
Paint $g '#E8E0CB' 22 53 196 50
Paint $g '#B2BC9F' 22 51 196 3
for($y=66;$y -lt 103;$y+=12){Paint $g '#D9D0BB' 22 $y 196 1}
Paint $g '#B9C3A7' 68 79 103 19
Paint $g '#B5997D' 70 65 100 7
Paint $g '#DEC19B' 68 62 104 7
Paint $g '#978475' 72 72 5 21
Paint $g '#978475' 163 72 5 21
Paint $g '#867B9C' 96 27 54 32
Paint $g '#C5BED5' 98 29 50 26
Paint $g '#403C4A' 100 31 46 22
Paint-Glyph $g 108 34 3 '#B9A7E1'
Paint $g '#9489A4' 119 59 8 5
Paint $g '#A89EB4' 112 64 22 2
Paint $g '#ADA3B4' 105 68 36 5
Paint $g '#D0C7D6' 107 69 32 2
Paint $g '#B89BC0' 83 56 8 9
Paint $g '#DFCDDD' 83 54 8 3
Paint $g '#B89BC0' 90 58 3 5
Paint $g '#ACA6B6' 113 78 22 14
Paint $g '#CAC3D1' 115 80 18 4
Paint $g '#948BA0' 122 92 4 8
Paint $g '#948BA0' 115 99 18 3
# Original plants, cabinet, and wall accent use only rectangles on the same grid.
Paint $g '#C5B199' 36 79 13 17
Paint $g '#E0C9AB' 34 77 17 4
Paint $g '#879F71' 40 56 4 23
Paint $g '#A4BA89' 31 59 12 7
Paint $g '#718D62' 43 67 12 7
Paint $g '#A4BA89' 38 49 9 10
Paint $g '#B9AB94' 184 74 22 24
Paint $g '#D0BEA1' 184 72 22 5
Paint $g '#948573' 187 81 16 2
Paint $g '#948573' 187 90 16 2
Paint $g '#AA98BA' 181 57 12 16
Paint $g '#8B9F77' 194 51 9 21
Paint $g '#D3BC97' 177 62 4 11
Paint $g '#A897B5' 42 28 22 17
Paint $g '#E9DECE' 44 30 18 13
Paint $g '#BCA4C6' 46 33 7 8
Paint $g '#94A87A' 54 36 6 5
$g.Dispose()
$large=[Drawing.Bitmap]::new(480,240);$g=New-Graphics $large
$g.DrawImage($scene,[Drawing.Rectangle]::new(0,0,480,240),0,0,240,120,[Drawing.GraphicsUnit]::Pixel)
Save-Png $large (Join-Path $images 'atelier-fallback.png')
$g.Dispose();$large.Dispose();$scene.Dispose()
Write-Output 'Generated original ACP SVG, 256px PNG, seven-size ICO, and 480x240 fallback.'
