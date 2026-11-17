# build-loader-win.ps1 - build xnuloader/loader.efi on Windows with the LLVM toolchain
# (clang target aarch64-unknown-windows + lld-link), the same commands as xnuloader/build.sh.
#
# usage:
#   .\build-loader-win.ps1                 # placeholder identity (open kernel; what M4a needs)
#   .\build-loader-win.ps1 -Identity <h>   # use an identity.h already made (e.g. from an IPSW)
#
# Output: xnuloader/loader.efi (PE32+ EFI application), copied to hakios-trident/qemu-run/loader-trident.efi
param(
    [string]$LlvmDir = '',
    [string]$Identity = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot           # hakios-trident
$loaderDir = Join-Path (Split-Path -Parent $root) 'hakios-xnu-kernel-main\xnuloader'
$py = 'C:\Users\Risan-Yu\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'

# locate clang.exe / lld-link.exe
if (-not $LlvmDir) {
    $cand = @(
        (Join-Path $root 'tools\llvm\bin'),
        (Join-Path $root 'tools\llvm\clang\bin'),
        (Join-Path $root 'tools\llvm')
    ) | Where-Object { Test-Path (Join-Path $_ 'clang.exe') } | Select-Object -First 1
    if (-not $cand) {
        $found = Get-ChildItem (Join-Path $root 'tools') -Recurse -Filter 'clang.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { $cand = $found.DirectoryName }
    }
    if (-not $cand) { throw "clang.exe not found under $root\tools (download+extract LLVM first)" }
    $LlvmDir = $cand
}
$clang = Join-Path $LlvmDir 'clang.exe'
$lldLink = Join-Path $LlvmDir 'lld-link.exe'
foreach ($f in @($clang, $lldLink)) { if (-not (Test-Path $f)) { throw "missing $f" } }
Write-Host "clang   : $clang"
Write-Host "lld-link: $lldLink"

if (-not $Identity) {
    Write-Host "=== placeholder identity.h (no IPSW, open kernel) ==="
    Push-Location $loaderDir
    try {
        & $py 'mkidentity.py' --placeholder | Out-File -FilePath 'identity.h' -Encoding ascii
        if ($LASTEXITCODE -ne 0) { throw "mkidentity.py failed" }
    } finally { Pop-Location }
} else {
    Copy-Item $Identity (Join-Path $loaderDir 'identity.h') -Force
    Write-Host "identity.h <- $Identity"
}

Push-Location $loaderDir
try {
    Write-Host "=== compile loader.c ==="
    & $clang --target=aarch64-unknown-windows -ffreestanding -fno-builtin -fno-stack-protector -fshort-wchar `
        -mgeneral-regs-only -O1 -Wall -Wextra -Wno-unused-parameter -c loader.c -o loader.obj
    if ($LASTEXITCODE -ne 0) { throw "clang failed ($LASTEXITCODE)" }

    Write-Host "=== link loader.efi ==="
    & $lldLink /subsystem:efi_application /entry:efi_main /nodefaultlib /base:0xA1000000 /out:loader.efi loader.obj
    if ($LASTEXITCODE -ne 0) { throw "lld-link failed ($LASTEXITCODE)" }

    $out = Join-Path $loaderDir 'loader.efi'
    $b = [System.IO.File]::ReadAllBytes($out)
    Write-Host ("loader.efi: {0} bytes, first bytes {1} {2}, sha256 {3}" -f $b.Length, $b[0].ToString('x2'), $b[1].ToString('x2'),
        (Get-FileHash $out -Algorithm SHA256).Hash)
    $dest = Join-Path $root 'qemu-run\loader-trident.efi'
    Copy-Item $out $dest -Force
    Write-Host "copied to $dest"
} finally { Pop-Location }
