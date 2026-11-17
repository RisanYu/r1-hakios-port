# edl-flash-uefi.ps1 - M3: write Renegade UEFI (boot-trident.img) and the verification-disabled
# vbmeta to the R1 through EDL, then read every partition back and compare. Optionally dry-run.
#
# The vbmeta is the one from the community QPST_TWRP_R1 package (AVB flags = 0x2 =
# VERIFICATION_DISABLED): ABL then skips boot verification and starts a custom boot image,
# which is how the 2019 TWRP package booted on locked devices.
#
# usage:
#   .\edl-flash-uefi.ps1 -Loader <firehose> -Yes            # real write
#   .\edl-flash-uefi.ps1 -DryRun                            # print the plan, touch nothing
#
# guards:
#   - backup/<latest>/ with boot_a.img, boot_b.img, vbmeta_a.img, vbmeta_b.img, devinfo.img
#   - boot image sha256 must be the Renegade boot-trident.img release value
#   - vbmeta must parse as AVB0 with VERIFICATION_DISABLED (flags bit 1)
#   - every write is read back and compared byte for byte; a mismatch stops everything
param(
    [string]$Loader = '',
    [string]$Image = '',
    [string]$Vbmeta = '',
    [switch]$Yes,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runEdl = Join-Path $PSScriptRoot 'run-edl.cmd'
$py = 'C:\Users\Risan-Yu\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$avbparse = Join-Path $PSScriptRoot 'avbparse.py'

if (-not $Loader) {
    $cand = @(
        (Join-Path $root 'lineflash\prog_firehose_ddr.elf'),
        (Join-Path $root 'edl-loaders\000460e100110022_0a1fd0c71592505d_fhprg_peek.bin')
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $cand) { throw "no loader; pass -Loader (lineflash\prog_firehose_ddr.elf)" }
    $Loader = $cand
}
if (-not $Image) { $Image = Join-Path $root '..\r1-trident\boot-trident.img' }
if (-not $Vbmeta) { $Vbmeta = Join-Path $root 'lineflash\vbmeta.img' }
foreach ($f in @($Loader, $Image, $Vbmeta)) {
    if (-not (Test-Path $f)) { throw "missing $f" }
}

# ---- guards ----
$backup = Get-ChildItem (Join-Path $root 'backup') -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $backup) { throw "no backup/ directory: run edl-session.ps1 -Mode backup first" }
foreach ($p in @('boot_a.img','boot_b.img','vbmeta_a.img','vbmeta_b.img','devinfo.img')) {
    if (-not (Test-Path (Join-Path $backup.FullName $p))) { throw "backup missing $p in $($backup.FullName)" }
}

$expected = 'B95C46AA9D3F43DF44745C92F824A86E01E381146F898E542431EB58F151305E'
$hash = (Get-FileHash $Image -Algorithm SHA256).Hash
Write-Host "image   : $Image"
Write-Host "sha256  : $hash"
if ($hash -ne $expected) { throw "boot image sha256 is not the Renegade boot-trident.img release value" }

Write-Host "vbmeta  : $Vbmeta"
& $py $avbparse $Vbmeta | Out-String
if ($LASTEXITCODE -ne 0) { throw "vbmeta parse failed" }

$steps = @(
    @{ part = 'boot_a';   file = $Image;  lun = 4 },
    @{ part = 'boot_b';   file = $Image;  lun = 4 },
    @{ part = 'vbmeta_a'; file = $Vbmeta; lun = 4 },
    @{ part = 'vbmeta_b'; file = $Vbmeta; lun = 4 }
)

if ($DryRun) {
    Write-Host "=== DRY RUN: the commands that would run ===" -ForegroundColor Yellow
    Write-Host "(loader: $Loader; backup: $($backup.FullName))"
    foreach ($s in $steps) {
        Write-Host "tools\run-edl.cmd w $($s.part) $($s.file) --lun $($s.lun) --loader $Loader"
        Write-Host "tools\run-edl.cmd r $($s.part) <readback> --lun $($s.lun) --loader $Loader   # compare first $((Get-Item $s.file).Length) bytes"
    }
    exit 0
}
if (-not $Yes) {
    Write-Host "This writes boot_a/boot_b and vbmeta_a/vbmeta_b. Re-run with -Yes when the backup exists and the unlock/verification state is understood." -ForegroundColor Yellow
    exit 1
}

$loaderArg = @('--loader', $Loader)
foreach ($s in $steps) {
    $part = $s.part; $file = $s.file
    Write-Host "=== write $part <- $file ==="
    & $runEdl w $part $file --lun $s.lun @loaderArg 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw "$part write failed" }
    $readback = Join-Path $env:TEMP "readback-$part.img"
    & $runEdl r $part $readback --lun $s.lun @loaderArg 2>&1 | Out-String
    if (-not (Test-Path $readback)) { throw "$part readback failed" }
    $a = [System.IO.File]::ReadAllBytes($file)
    $b = [System.IO.File]::ReadAllBytes($readback)
    if ($b.Length -lt $a.Length) { throw "$part readback shorter than the written file" }
    for ($i = 0; $i -lt $a.Length; $i++) { if ($a[$i] -ne $b[$i]) { throw "$part mismatch at byte 0x$($i.ToString('X'))" } }
    Write-Host "$part verified: first $($a.Length) bytes identical" -ForegroundColor Green
    Remove-Item $readback -Force
}
Write-Host ""
Write-Host "M3: UEFI + verification-disabled vbmeta written. Long-press power; Renegade UEFI should start." -ForegroundColor Green
Write-Host "If it does not: restore the backups with 'run-edl.cmd w <part> backup\<ts>\<part>.img --loader <firehose>'."
