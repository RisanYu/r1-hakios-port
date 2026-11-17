# run-qemu-open.ps1 - M2 on Windows (no WSL): boot the HakiOS open kernel in QEMU.
#
# Replicates HakiOS `make qemu-open`:
#   payload.bin  = prebuilt/hakios-kernel + prebuilt/userland/hello + cmdline "cpus=1"
#   ESP          = prebuilt/loader.efi as \EFI\BOOT\BOOTAA64.EFI (+ payload.bin for -EspMode)
#   QEMU         = virt/gic-version=3, cortex-a76, AAVMF aarch64 firmware, TCG
#
# usage:
#   .\run-qemu-open.ps1                  # loader device puts the payload at 0xF0000000 (default path)
#   .\run-qemu-open.ps1 -EspMode        # UEFI-native: loader reads \EFI\hakios\payload.bin from the ESP
#   .\run-qemu-open.ps1 -Seconds 120
param(
    [int]$Seconds = 90,
    [switch]$EspMode,
    [int]$MemoryMB = 3072,
    [string]$EspImage = '',
    [int]$Smp = 1,
    [string]$Payload = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$run = Join-Path $root 'qemu-run'

# find qemu-system-aarch64.exe
$candidates = @(
    (Join-Path $root 'tools\qemu\qemu-system-aarch64.exe'),
    (Join-Path $root 'tools\qemu\qemu\qemu-system-aarch64.exe'),
    (Join-Path $root 'tools\qemu\bin\qemu-system-aarch64.exe')
)
$qemuExe = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $qemuExe) {
    $found = Get-ChildItem (Join-Path $root 'tools\qemu') -Recurse -Filter 'qemu-system-aarch64.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $qemuExe = $found.FullName }
}
if (-not $qemuExe) { throw "qemu-system-aarch64.exe not found under $root\tools\qemu" }

$code = Join-Path $run 'AAVMF_CODE.fd'
$vars = Join-Path $run 'vars.fd'
$payload = if ($Payload) { $Payload } else { Join-Path $run 'payload.bin' }
$espDir = Join-Path $run 'esp'
foreach ($f in @($code, $vars, $payload)) {
    if (-not (Test-Path $f)) { throw "missing $f" }
}
$log = Join-Path $run 'qemu-open.log'
$errlog = Join-Path $run 'qemu-open.err.log'
# QEMU's vvfat driver writes a temporary file; give it a writable temp dir (the
# sandboxed host temp is not writable) for the child process.
$tmpDir = Join-Path $run 'tmp'
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
$env:TMP = $tmpDir
$env:TEMP = $tmpDir
if (Test-Path $log) { Remove-Item $log -Force }
if (Test-Path $errlog) { Remove-Item $errlog -Force }

$qemuArgs = @(
    '-M', 'virt,gic-version=3',
    '-cpu', 'cortex-a76',
    '-smp', "$Smp",
    '-m', "$MemoryMB",
    '-accel', 'tcg,tb-size=384',
    '-drive', "if=pflash,format=raw,readonly=on,file=$code",
    '-drive', "if=pflash,format=raw,file=$vars",
    '-display', 'none',
    '-serial', 'stdio',
    '-monitor', 'none',
    '-no-reboot'
)
if ($EspMode) {
    Write-Host "UEFI-native mode: the loader reads /EFI/hakios/payload.bin from the ESP"
} else {
    $qemuArgs += @('-device', "loader,file=$payload,addr=0xF0000000,force-raw=on")
}
# the FAT volume: a real FAT32 image (built by mkespimg.py) or a directory via vvfat
if ($EspImage) {
    if (-not (Test-Path $EspImage)) { throw "missing ESP image: $EspImage" }
    Write-Host "ESP image: $EspImage"
    $qemuArgs += @('-drive', "file=$EspImage,format=raw,if=virtio")
} else {
    $qemuArgs += @('-drive', "file=fat:rw:$espDir,format=raw,if=virtio")
}

Write-Host "QEMU: $qemuExe"
Write-Host "log : $log"
Write-Host "running for $Seconds s ..."
$p = Start-Process -FilePath $qemuExe -ArgumentList $qemuArgs -WorkingDirectory $run -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -WindowStyle Hidden
$closed = $p.WaitForExit($Seconds * 1000)
if (-not $closed) {
    Write-Host "stopping QEMU (pid $($p.Id))"
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "QEMU exited by itself, code $($p.ExitCode)"
}
Start-Sleep -Milliseconds 500
Write-Host "=== serial output ($log) ==="
if (Test-Path $log) { Get-Content $log -ErrorAction SilentlyContinue | Select-Object -Last 250 | Out-String }
Write-Host "=== stderr tail ==="
if (Test-Path $errlog) { Get-Content $errlog -ErrorAction SilentlyContinue | Select-Object -Last 40 | Out-String }
