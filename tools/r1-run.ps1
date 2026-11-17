# r1-run.ps1 - the R1/HakiOS EDL session in stages. Every stage checks that the phone is in
# EDL (9008) first and refuses to run (instead of hanging on a missing device).
#
# usage (from hakios-trident/):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\r1-run.ps1 -Stage gpt
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\r1-run.ps1 -Stage backup
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\r1-run.ps1 -Stage logdump
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\r1-run.ps1 -Stage uefi -Yes     # M3 (writes boot+vbmeta)
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\r1-run.ps1 -Stage esp  -Yes     # M4a (writes system_b, 3 GB)
param(
    [ValidateSet('status','gpt','backup','devinfo','logdump','unlock','uefi','esp','all-read')]
    [string]$Stage = 'status',
    [switch]$Yes,
    [string]$Loader = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$ps = 'powershell.exe'
if (-not $Loader) { $Loader = Join-Path $root 'lineflash\prog_firehose_ddr.elf' }
if (-not (Test-Path $Loader)) { throw "loader not found: $Loader (lineflash\prog_firehose_ddr.elf)" }

function Get-EdlDevice {
    $out = & pnputil /enum-devices /connected 2>&1
    $hit = $out | Select-String -Pattern 'VID_05C6&PID_9008|QDLoader|9008' -SimpleMatch
    return [bool]$hit
}
function Require-Edl {
    if (-not (Get-EdlDevice)) {
        Write-Host "No Qualcomm 9008 (EDL) device visible." -ForegroundColor Yellow
        Write-Host "Put the phone in EDL first:" -ForegroundColor Yellow
        Write-Host "  1. phone fully off" -ForegroundColor Yellow
        Write-Host "  2. EDL cable: switch to 9008, plug the PC end in" -ForegroundColor Yellow
        Write-Host "  3. hold the cable button and plug the phone end in; release about 3 s after" -ForegroundColor Yellow
        Write-Host "  4. Device Manager shows 'Qualcomm HS-USB QDLoader 9008'" -ForegroundColor Yellow
        Write-Host "(alternative after unlocking: hold Volume Down + Power for Fastboot Mode)" -ForegroundColor Yellow
        exit 2
    }
    Write-Host "EDL device: present" -ForegroundColor Green
}
function Run-Ps([string]$file, [string[]]$args) {
    & $ps -NoProfile -ExecutionPolicy Bypass -File $file @args
    if ($LASTEXITCODE -ne 0) { throw "$([System.IO.Path]::GetFileName($file)) failed ($LASTEXITCODE)" }
}

Write-Host "=== r1-run: stage $Stage ==="
Write-Host "loader: $Loader"

switch ($Stage) {
    'status' {
        Write-Host ("EDL device: {0}" -f (Get-EdlDevice))
        $adb = Join-Path (Split-Path -Parent $root) 'platform-tools\adb.exe'
        $fb = Join-Path (Split-Path -Parent $root) 'platform-tools\fastboot.exe'
        if (Test-Path $adb) { Write-Host ("adb devices: " + (& $adb devices 2>&1 | Out-String).Trim()) }
        if (Test-Path $fb) { Write-Host ("fastboot devices: " + (& $fb devices 2>&1 | Out-String).Trim()) }
        $bk = Get-ChildItem (Join-Path $root 'backup') -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        Write-Host ("last backup: " + ($(if ($bk) { $bk.FullName } else { "(none)" })))
    }
    'gpt' {
        Require-Edl
        Run-Ps (Join-Path $root 'tools\edl-session.ps1') @('-Mode', 'gpt', '-Loader', $Loader)
    }
    'backup' {
        Require-Edl
        Run-Ps (Join-Path $root 'tools\edl-session.ps1') @('-Mode', 'backup', '-Loader', $Loader)
    }
    'devinfo' {
        Require-Edl
        Run-Ps (Join-Path $root 'tools\edl-session.ps1') @('-Mode', 'devinfo', '-Loader', $Loader)
    }
    'logdump' {
        Require-Edl
        Run-Ps (Join-Path $root 'tools\read-logdump.ps1') @('-Loader', $Loader)
    }
    'unlock' {
        Require-Edl
        if (-not $Yes) { Write-Host "unlock writes devinfo: re-run with -Yes" -ForegroundColor Yellow; exit 1 }
        Run-Ps (Join-Path $root 'tools\edl-apply-devinfo.ps1') @('-Loader', $Loader, '-Yes')
    }
    'uefi' {
        Require-Edl
        if (-not $Yes) { Write-Host "uefi writes boot_a/boot_b + vbmeta_a/vbmeta_b: re-run with -Yes" -ForegroundColor Yellow; exit 1 }
        Run-Ps (Join-Path $root 'tools\edl-flash-uefi.ps1') @('-Loader', $Loader, '-Yes')
    }
    'esp' {
        Require-Edl
        if (-not $Yes) { Write-Host "esp writes system_b (3 GB): re-run with -Yes" -ForegroundColor Yellow; exit 1 }
        $img = Join-Path $root 'qemu-run\system_b-esp.img'
        if (-not (Test-Path $img)) { throw "missing $img (build it with tools/mkespimg2.py)" }
        Write-Host ("ESP image: {0} ({1} MB, sha256 {2})" -f $img, [math]::Round((Get-Item $img).Length/1MB,1),
            (Get-FileHash $img -Algorithm SHA256).Hash)
        Write-Host "=== write system_b (about 3 GB) ==="
        & (Join-Path $root 'tools\run-edl.cmd') w system_b $img --lun 0 --loader $Loader
        if ($LASTEXITCODE -ne 0) { throw "write failed" }
        Write-Host "=== read back system_b and compare ==="
        $rb = Join-Path $root ('backup\system_b-readback-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.img')
        New-Item -ItemType Directory -Force -Path (Split-Path $rb -Parent) | Out-Null
        & (Join-Path $root 'tools\run-edl.cmd') r system_b $rb --lun 0 --loader $Loader
        if (-not (Test-Path $rb)) { throw "readback failed" }
        $a = [System.IO.File]::ReadAllBytes($img)
        $b = [System.IO.File]::ReadAllBytes($rb)
        if ($b.Length -lt $a.Length) { throw "readback shorter than the image" }
        $bad = -1
        for ($i = 0; $i -lt $a.Length; $i++) { if ($a[$i] -ne $b[$i]) { $bad = $i; break } }
        if ($bad -ge 0) { throw "system_b readback mismatch at byte 0x$($bad.ToString('X'))" }
        Write-Host "system_b verified: first $($a.Length) bytes identical" -ForegroundColor Green
    }
    'all-read' {
        Require-Edl
        Run-Ps (Join-Path $root 'tools\edl-session.ps1') @('-Mode', 'gpt', '-Loader', $Loader)
        Run-Ps (Join-Path $root 'tools\edl-session.ps1') @('-Mode', 'backup', '-Loader', $Loader)
        Run-Ps (Join-Path $root 'tools\read-logdump.ps1') @('-Loader', $Loader)
    }
}
Write-Host "=== r1-run: done ($Stage) ===" -ForegroundColor Green
