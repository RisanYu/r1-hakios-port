# edl-session.ps1 - read-only EDL session against the R1 (trident): print the GPT tables and
# back up the key partitions. Nothing is written to the phone by this script.
#
# LUN layout (from the official R1_user_V6.0.4 GPT images, lineflash/gpt_main*.bin, 4096-byte sectors):
#   LUN 0: persist, misc, keystore, frp, system_a, system_b, userdata, ...
#   LUN 1: xbl_a, xbl_config_a        LUN 2: xbl_b, xbl_config_b
#   LUN 3: ALIGN_TO_128K_1, cdt, ddr
#   LUN 4: aop/tz/hyp/modem/..._a, abl_a, dsp_a, boot_a, vendor_a, vbmeta_a, dtbo_a, ...
#          + all _b, devinfo, dip, ..., logdump
#   LUN 5: modemst1, modemst2, fsg, fsc
#
# usage:
#   .\edl-session.ps1 -Mode gpt
#   .\edl-session.ps1 -Mode backup
#   .\edl-session.ps1 -Mode devinfo
#   .\edl-session.ps1 -Mode backup -Loader "C:\path\to\prog_firehose_ddr.elf"
param(
    [ValidateSet('gpt','backup','devinfo')]
    [string]$Mode = 'gpt',
    [string]$Loader = '',
    [string]$BackupDir = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runEdl = Join-Path $PSScriptRoot 'run-edl.cmd'
$py = 'C:\Users\Risan-Yu\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$devinfoPy = Join-Path $PSScriptRoot 'devinfo.py'
$outBase = Join-Path $root 'backup'
if (-not $BackupDir) { $BackupDir = Join-Path $outBase (Get-Date -Format 'yyyyMMdd-HHmmss') }

if (-not $Loader) {
    $cand = @(
        (Join-Path $root 'lineflash\prog_firehose_ddr.elf'),
        (Join-Path $root 'edl-loaders\000460e100110022_0a1fd0c71592505d_fhprg_peek.bin'),
        (Join-Path $root 'edl-loaders\000460e100110022_032a43cc8d3e2d3b_fhprg_peek.bin')
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $cand) { throw "no loader found; pass -Loader (lineflash\prog_firehose_ddr.elf)" }
    $Loader = $cand
}
if (-not (Test-Path $Loader)) { throw "loader not found: $Loader" }
Write-Host "loader: $Loader"

# partition -> UFS LUN (the firehose needs the physical partition number)
$partLun = @{
    'misc' = 0; 'frp' = 0; 'persist' = 0; 'keystore' = 0
    'system_a' = 0; 'system_b' = 0; 'userdata' = 0
    'boot_a' = 4; 'boot_b' = 4; 'vbmeta_a' = 4; 'vbmeta_b' = 4
    'abl_a' = 4; 'abl_b' = 4; 'devinfo' = 4; 'logdump' = 4; 'dip' = 4
    'modem_a' = 4; 'modem_b' = 4; 'dtbo_a' = 4; 'dtbo_b' = 4
    'fsg' = 5; 'fsc' = 5; 'modemst1' = 5; 'modemst2' = 5
}

# check the 9008 device is there
$usb = (pnputil /enum-devices /connected 2>&1 | Select-String -Pattern 'VID_05C6|9008|QUSB|QDLoader' -SimpleMatch)
if (-not $usb) {
    Write-Host "No Qualcomm 9008 (EDL) device visible. Put the phone in EDL first:" -ForegroundColor Yellow
    Write-Host "  phone off -> EDL cable switch to 9008 -> hold the button, plug the phone in, release after ~3 s" -ForegroundColor Yellow
    Write-Host "(or use tools\r1-run.ps1 -Stage ... which does this check for you)" -ForegroundColor Yellow
    exit 2
}

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$loaderArg = @('--loader', $Loader)

switch ($Mode) {
    'gpt' {
        foreach ($lun in @(0, 4)) {
            Write-Host "=== printgpt (LUN $lun) ==="
            $log = Join-Path $BackupDir ("gpt-lun$lun.txt")
            & $runEdl printgpt --lun $lun @loaderArg 2>&1 | Tee-Object -FilePath $log
            if ($LASTEXITCODE -ne 0) { throw "printgpt LUN $lun failed (loader rejected / device not in EDL?)" }
            Write-Host "saved $log"
        }
    }
    'devinfo' {
        Write-Host "=== read devinfo (LUN 4) ==="
        $dev = Join-Path $BackupDir 'devinfo.img'
        & $runEdl r devinfo $dev --lun 4 @loaderArg 2>&1 | Out-String
        if (-not (Test-Path $dev)) { throw "devinfo read failed" }
        Write-Host "=== parse ==="
        & $py $devinfoPy info $dev
    }
    'backup' {
        $parts = @('devinfo','boot_a','boot_b','vbmeta_a','vbmeta_b','abl_a','abl_b','misc','frp')
        Write-Host "=== backup to $BackupDir ==="
        foreach ($part in $parts) {
            $dst = Join-Path $BackupDir "$part.img"
            $lun = if ($partLun.ContainsKey($part)) { $partLun[$part] } else { 4 }
            Write-Host "--- $part (LUN $lun)"
            & $runEdl r $part $dst --lun $lun @loaderArg 2>&1 | Out-String
            if (Test-Path $dst) {
                "  $part -> $((Get-Item $dst).Length) bytes  sha256=$((Get-FileHash $dst -Algorithm SHA256).Hash.Substring(0,16))..."
            } else {
                Write-Host "  WARNING: $part read failed" -ForegroundColor Yellow
            }
        }
        # parse devinfo if it came
        $dev = Join-Path $BackupDir 'devinfo.img'
        if (Test-Path $dev) {
            Write-Host "=== devinfo flags ==="
            & $py $devinfoPy info $dev
        }
        Write-Host "=== backup done; write manifest ==="
        Get-ChildItem $BackupDir -File | Select-Object Name, Length | Format-Table -AutoSize | Out-String | Tee-Object -FilePath (Join-Path $BackupDir 'manifest.txt')
    }
}
Write-Host "NOTE: this script only reads. Writing (devinfo unlock / boot partition) is done by explicit commands after reviewing the backup."
