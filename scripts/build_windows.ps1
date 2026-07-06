<#
.SYNOPSIS
    Build the Whisper-Free Windows onedir bundle with PyInstaller, then wrap
    it in a per-user Inno Setup installer.

.DESCRIPTION
    Mirrors scripts/build_macos.sh for Windows. Produces dist/Whisper-Free/,
    a onedir bundle (not onefile -- see packaging/windows/Whisper-Free.spec
    and ADR-0001 for why), then compiles
    dist/installer/Whisper-Free-Setup-<version>.exe from
    packaging/windows/installer.iss via Inno Setup's ISCC.exe (skipped with a
    warning if Inno Setup isn't installed -- the bundle itself still builds).

.PREREQUISITES
    One-time setup:
        py -3.11 -m venv venv
        venv\Scripts\Activate.ps1
        pip install -r requirements-windows.txt

    For the GPU path to be bundled, requirements-windows.txt's
    nvidia-cublas-cu12 / nvidia-cudnn-cu12 packages must be installed in the
    venv (they are CPU-machine-safe to install; the app still auto-detects
    CPU vs GPU at runtime).

    ffmpeg.exe must be placed at packaging/windows/ffmpeg.exe before building
    (download a Windows static build from https://www.gyan.dev/ffmpeg/builds/
    or via `winget install ffmpeg` and copy ffmpeg.exe out). Without it, the
    bundle is still produced but MP3/M4A/WebM file transcription will need a
    system FFmpeg on PATH.

    Inno Setup (https://jrsoftware.org/isinfo.php) must be installed for the
    installer-compile step; if `iscc` isn't found on PATH or at its default
    install location, that step is skipped with a warning and only the
    onedir bundle is produced.

.USAGE
    ./scripts/build_windows.ps1
    VERSION=1.0.1 ./scripts/build_windows.ps1   (or: $env:VERSION = '1.0.1')

.OUTPUTS
    dist/Whisper-Free/Whisper-Free.exe            (onedir bundle)
    dist/installer/Whisper-Free-Setup-<ver>.exe   (per-user installer)
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $Root

# --- Sanity checks -----------------------------------------------------------

if (-not (Test-Path "venv")) {
    Write-Error @"
venv not found. Set it up first:
  py -3.11 -m venv venv
  venv\Scripts\Activate.ps1
  pip install -r requirements-windows.txt
"@
}

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    $VenvPyinstaller = Join-Path $Root "venv\Scripts\pyinstaller.exe"
    if (-not (Test-Path $VenvPyinstaller)) {
        Write-Error "pyinstaller not found. Activate venv and `pip install -r requirements-windows.txt`."
    }
}

$FfmpegAsset = Join-Path $Root "packaging\windows\ffmpeg.exe"
if (-not (Test-Path $FfmpegAsset)) {
    Write-Warning "packaging\windows\ffmpeg.exe not found -- the bundle will NOT include ffmpeg.exe."
    Write-Warning "MP3/M4A/WebM file transcription will require a system FFmpeg on PATH."
    Write-Warning "Download a Windows static build and copy ffmpeg.exe to that path to include it."
}

# --- Resolve version ---------------------------------------------------------

if (-not $env:VERSION) {
    $Match = Select-String -Path "app\ui\main_window.py" -Pattern "Version \d+\.\d+\.\d+" | Select-Object -First 1
    if ($Match) {
        $env:VERSION = ($Match.Matches[0].Value -replace "Version ", "")
    } else {
        $env:VERSION = "0.0.0-dev"
    }
}
Write-Host "==> Building Whisper-Free v$($env:VERSION) for Windows..."

# --- Generate .ico if missing or stale ---------------------------------------

$Icns = "assets\app-icon.ico"
$SrcPng = "assets\app-icon-512.png"

$NeedsIcon = (-not (Test-Path $Icns)) -or ((Get-Item $SrcPng).LastWriteTime -gt (Get-Item $Icns -ErrorAction SilentlyContinue).LastWriteTime)
if ($NeedsIcon) {
    Write-Host "==> Generating $Icns from $SrcPng"
    python -c @"
from PySide6.QtGui import QImage
img = QImage('$SrcPng')
if img.isNull():
    raise SystemExit('failed to load $SrcPng')
img.scaled(256, 256).save('$Icns', 'ICO')
"@
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Icon generation failed."
    }
}

# --- Clean previous build -----------------------------------------------------

Write-Host "==> Cleaning build/ and dist/"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist

# --- Run PyInstaller -----------------------------------------------------------

Write-Host "==> Running PyInstaller (this takes a few minutes)..."
pyinstaller --noconfirm --clean --log-level WARN packaging\windows\Whisper-Free.spec
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed."
}

$Bundle = "dist\Whisper-Free"
$Exe = "$Bundle\Whisper-Free.exe"
if (-not (Test-Path $Exe)) {
    Write-Error "Build failed; $Exe not found."
}

# --- Bundle checks -------------------------------------------------------------

$BundleSize = "{0:N0} MB" -f ((Get-ChildItem $Bundle -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB)
Write-Host "==> Built $Bundle ($BundleSize)"

if (Test-Path "$Bundle\ffmpeg.exe") {
    Write-Host "  [OK] ffmpeg.exe bundled"
} else {
    Write-Warning "  ffmpeg.exe NOT bundled -- MP3/M4A/WebM needs a system FFmpeg on PATH"
}

$CudaDlls = Get-ChildItem $Bundle -Filter "cublas*.dll" -ErrorAction SilentlyContinue
if ($CudaDlls) {
    Write-Host "  [OK] CUDA runtime DLLs bundled ($($CudaDlls.Count) found)"
} else {
    Write-Warning "  No CUDA runtime DLLs found -- bundle is CPU-only (install nvidia-cublas-cu12/nvidia-cudnn-cu12 in venv to include GPU support)"
}

if (Get-ChildItem $Bundle -Recurse -Filter "torch*" -ErrorAction SilentlyContinue) {
    Write-Warning "  torch detected in bundle -- excludes in the spec may be off"
}

Write-Host ""
Write-Host "Done."
Write-Host "  Bundle: $Bundle ($BundleSize)"
Write-Host ""
Write-Host "Smoke test the bundle:"
Write-Host "  & '$Exe'"

# --- Compile the Inno Setup installer ------------------------------------------

$Iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $Iscc) {
    $DefaultIscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $DefaultIscc) {
        $Iscc = Get-Item $DefaultIscc
    }
}

if (-not $Iscc) {
    Write-Warning ""
    Write-Warning "Inno Setup's ISCC.exe was not found on PATH -- skipping installer build."
    Write-Warning "Install Inno Setup (https://jrsoftware.org/isinfo.php) and re-run to produce"
    Write-Warning "dist\installer\Whisper-Free-Setup-$($env:VERSION).exe, or compile manually:"
    Write-Warning "  iscc packaging\windows\installer.iss /DMyAppVersion=$($env:VERSION)"
} else {
    Write-Host ""
    Write-Host "==> Compiling installer with Inno Setup..."
    & $Iscc.Source "packaging\windows\installer.iss" "/DMyAppVersion=$($env:VERSION)"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Inno Setup compilation failed."
    }
    $InstallerExe = "dist\installer\Whisper-Free-Setup-$($env:VERSION).exe"
    if (Test-Path $InstallerExe) {
        Write-Host "  [OK] Installer built: $InstallerExe"
    } else {
        Write-Error "Inno Setup reported success but $InstallerExe was not found."
    }
}

Write-Host ""
