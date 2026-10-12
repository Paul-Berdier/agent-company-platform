[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Archive,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '../resources/atelier-local')
)
# Windows uniquement, sans dépendance téléchargée ni exécution des générateurs de l’archive.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.Drawing
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$sourceArchive = [IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $Archive).Path)
$script:opened = [Collections.Generic.List[object]]::new()
$script:usedEntries = [Collections.Generic.List[string]]::new()

function Open-Pack([string]$name) {
    $entry = $sourceArchive.Entries | Where-Object { $_.Name -eq $name } | Select-Object -First 1
    if ($null -eq $entry) { throw "Pack imbriqué absent : $name" }
    $memory = [IO.MemoryStream]::new()
    $stream = $entry.Open()
    try { $stream.CopyTo($memory) } finally { $stream.Dispose() }
    $memory.Position = 0
    $zip = [IO.Compression.ZipArchive]::new($memory, [IO.Compression.ZipArchiveMode]::Read)
    $script:opened.Add($memory); $script:opened.Add($zip)
    return $zip
}
function Read-Image($zip, [string]$path) {
    $entry = $zip.GetEntry($path)
    if ($null -eq $entry) { throw "Sprite absent : $path" }
    $script:usedEntries.Add($path)
    $stream = $entry.Open()
    try {
        $original = [Drawing.Image]::FromStream($stream)
        try { return [Drawing.Bitmap]::new($original) } finally { $original.Dispose() }
    } finally { $stream.Dispose() }
}
function Crop-Image($bitmap, [int]$x, [int]$y, [int]$w, [int]$h) {
    return $bitmap.Clone([Drawing.Rectangle]::new($x,$y,$w,$h), [Drawing.Imaging.PixelFormat]::Format32bppArgb)
}
function Trim-Image($bitmap) {
    $left=$bitmap.Width; $top=$bitmap.Height; $right=-1; $bottom=-1
    for($y=0;$y -lt $bitmap.Height;$y++) { for($x=0;$x -lt $bitmap.Width;$x++) {
        if($bitmap.GetPixel($x,$y).A -gt 0) {
            $left=[Math]::Min($left,$x);$top=[Math]::Min($top,$y)
            $right=[Math]::Max($right,$x);$bottom=[Math]::Max($bottom,$y)
        }
    }}
    if($right -lt 0) { throw 'Sprite vide' }
    return Crop-Image $bitmap $left $top ($right-$left+1) ($bottom-$top+1)
}
function Write-Png($bitmap, [string]$name) {
    $bitmap.Save((Join-Path $OutputDirectory $name), [Drawing.Imaging.ImageFormat]::Png)
}
function New-Graphics($bitmap) {
    $graphics=[Drawing.Graphics]::FromImage($bitmap)
    $graphics.InterpolationMode=[Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
    $graphics.PixelOffsetMode=[Drawing.Drawing2D.PixelOffsetMode]::Half
    $graphics.SmoothingMode=[Drawing.Drawing2D.SmoothingMode]::None
    return $graphics
}
function Paint($graphics, [string]$hex, [int]$x,[int]$y,[int]$w,[int]$h) {
    $brush=[Drawing.SolidBrush]::new([Drawing.ColorTranslator]::FromHtml($hex))
    try { $graphics.FillRectangle($brush,$x,$y,$w,$h) } finally { $brush.Dispose() }
}
function Place($graphics,$bitmap,[int]$x,[int]$y,[int]$scale=1) {
    $graphics.DrawImage($bitmap,[Drawing.Rectangle]::new($x,$y,($bitmap.Width*$scale),($bitmap.Height*$scale)),0,0,$bitmap.Width,$bitmap.Height,[Drawing.GraphicsUnit]::Pixel)
}

try {
    $office=Open-Pack 'Modern_Office_Revamped_v1.2.zip'
    $interiors=Open-Pack 'moderninteriors-win.zip'
    foreach($record in @(@($office,'office-license.txt'),@($interiors,'interiors-license.txt'))) {
        $reader=[IO.StreamReader]::new($record[0].GetEntry('LICENSE.txt').Open())
        try { [IO.File]::WriteAllText((Join-Path $OutputDirectory $record[1]),$reader.ReadToEnd()) } finally { $reader.Dispose() }
    }
    $people=@{}
    foreach($name in @('Adam','Alex','Amelia','Bob')) {
        $sheet=Read-Image $interiors "2_Characters/Old/Single_Characters_Legacy/32x32/${name}_idle_32x32.png"
        try {
            if($sheet.Width -ne 128 -or $sheet.Height -ne 64) { throw "Unexpected portrait sheet dimensions: $name" }
            $portrait=Crop-Image $sheet 96 0 32 64
            Write-Png $portrait ('agent-'+$name.ToLowerInvariant()+'.png')
            $people[$name]=$portrait
        } finally { $sheet.Dispose() }
    }
    $props=@{}
    foreach($number in @(98,100,101,120,130,164,170,191,200,317,337)) {
        $sheet=Read-Image $office "4_Modern_Office_singles/16x16/Modern_Office_Singles_${number}.png"
        try { $props[$number]=Trim-Image $sheet } finally { $sheet.Dispose() }
    }
    # Purely decorative studio: no runtime status is inferred from this illustration.
    $scene=[Drawing.Bitmap]::new(240,120)
    $graphics=New-Graphics $scene
    Paint $graphics '#CFD1C0' 14 111 214 6
    Paint $graphics '#87997F' 9 10 222 34
    Paint $graphics '#BDCCAE' 11 12 218 30
    Paint $graphics '#E5DDC9' 9 44 222 68
    Paint $graphics '#9BAB8F' 9 42 222 3
    for($y=62;$y -le 112;$y+=16) { Paint $graphics '#D5CCB7' 10 $y 220 1 }
    for($x=26;$x -lt 231;$x+=32) { Paint $graphics '#DAD2BD' $x 45 1 66 }
    Paint $graphics '#A7B598' 41 73 112 32
    Paint $graphics '#BDCAAB' 43 75 108 28
    Place $graphics $props[164] 62 16
    Place $graphics $props[170] 115 16
    Place $graphics $props[98] 19 26
    Place $graphics $props[317] 183 48
    Place $graphics $props[100] 212 38
    foreach($x in @(49,117)) {
        Place $graphics $props[191] $x 64
        Place $graphics $props[130] ($x+3) 53
        Place $graphics $props[120] ($x+3) 69
        Place $graphics $props[101] ($x+3) 82
    }
    Place $graphics $props[337] 22 93
    Place $graphics $props[200] 190 85
    $graphics.DrawImage($people['Amelia'],[Drawing.Rectangle]::new(84,76,16,32),0,0,32,64,[Drawing.GraphicsUnit]::Pixel)
    $graphics.DrawImage($people['Adam'],[Drawing.Rectangle]::new(163,78,16,32),0,0,32,64,[Drawing.GraphicsUnit]::Pixel)
    $graphics.Dispose()
    $large=[Drawing.Bitmap]::new(480,240);$graphics=New-Graphics $large
    Place $graphics $scene 0 0 2
    Write-Png $large 'atelier-scene.png'
    $graphics.Dispose();$large.Dispose();$scene.Dispose()
    foreach($bitmap in $props.Values) { $bitmap.Dispose() }
    foreach($bitmap in $people.Values) { $bitmap.Dispose() }
    $manifest=[ordered]@{
        version=1; sourceArchive=[IO.Path]::GetFileName($Archive); credit='LimeZu - https://limezu.itch.io/'
        purpose='Local decorative illustration and agent avatars; not live workspace state.'
        outputs=@('atelier-scene.png','agent-adam.png','agent-alex.png','agent-amelia.png','agent-bob.png')
        sourceEntries=@($script:usedEntries | Sort-Object -Unique)
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'provenance.json') -Encoding utf8
    Write-Output "Generated 480x240 scene and four 32x64 portraits in $OutputDirectory"
} finally {
    for($i=$script:opened.Count-1;$i -ge 0;$i--) { $script:opened[$i].Dispose() }
    $sourceArchive.Dispose()
}
