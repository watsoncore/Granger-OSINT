[CmdletBinding()]
param(
    [switch]$SkipTests,
    [string]$Python = "py"
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Executable $($Arguments -join ' ')"
    }
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    $createArgs = if ($Python -eq "py") { @("-3.14", "-m", "venv", ".venv") } else { @("-m", "venv", ".venv") }
    Invoke-Checked -Executable $Python -Arguments $createArgs
}
Invoke-Checked -Executable $venvPython -Arguments @("-m", "ensurepip", "--upgrade")
Invoke-Checked -Executable $venvPython -Arguments @("-m", "pip", "install", "-r", "requirements-dev.txt")
Invoke-Checked -Executable $venvPython -Arguments @("scripts/verify_assets.py")
if (-not $SkipTests) {
    Invoke-Checked -Executable $venvPython -Arguments @("-m", "pytest", "-q")
}
Invoke-Checked -Executable $venvPython -Arguments @("-m", "PyInstaller", "--noconfirm", "--clean", "GrangerPet.spec")
$binary = Join-Path $PSScriptRoot "dist\GrangerPet.exe"
if (-not (Test-Path -LiteralPath $binary)) {
    throw "Build did not produce dist\GrangerPet.exe"
}
Invoke-Checked -Executable $venvPython -Arguments @("scripts/smoke_exe.py", "--exe", $binary, "--output", "dist/binarysmoke.json")
Get-FileHash -LiteralPath $binary -Algorithm SHA256 | Format-List
Write-Host "Built: $binary"
