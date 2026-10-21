#Requires -RunAsAdministrator
# Add the laptop's public key to the Administrators key file used by sshd.
# wzy10 is a member of Administrators, so sshd reads administrators_authorized_keys,
# NOT %USERPROFILE%\.ssh\authorized_keys.
#
# Elevated usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\remote\add-laptop-key.ps1 `
#       -PublicKey "ssh-ed25519 AAAAC3... laptop"

param(
    [Parameter(Mandatory = $true)][string]$PublicKey,
    [string]$Path = 'C:\ProgramData\ssh\administrators_authorized_keys'
)

$ErrorActionPreference = 'Stop'
$key = $PublicKey.Trim()
if ($key -notmatch '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521))\s+[A-Za-z0-9+/=]+') {
    throw 'Input does not look like an SSH public key line.'
}

$dir = Split-Path -Parent $Path
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$lines = @()
if (Test-Path -LiteralPath $Path) { $lines = @(Get-Content -LiteralPath $Path) }
if ($lines -contains $key) {
    Write-Host '[skip] key already present'
} else {
    Add-Content -LiteralPath $Path -Value $key -Encoding ascii
    Write-Host '[ok] key appended'
}

# sshd refuses the file if anyone besides Administrators/SYSTEM can read it.
icacls $Path /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F' | Out-Null
Write-Host '[ok] ACL restricted to Administrators + SYSTEM'

& 'C:\Windows\System32\OpenSSH\ssh-keygen.exe' -lf $Path
Restart-Service sshd
Start-Sleep -Seconds 1
Get-Service sshd | Format-Table Status, StartType, Name -AutoSize
