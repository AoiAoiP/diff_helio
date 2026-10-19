#Requires -RunAsAdministrator
# Complete the OpenSSH Server setup after Add-WindowsCapability.
# Idempotent: safe to run more than once. Read the console output at the end.
# Run in an elevated PowerShell:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\remote\complete-sshd-setup.ps1

$ErrorActionPreference = 'Stop'
$sshDir = 'C:\ProgramData\ssh'
$sshd   = 'C:\Windows\System32\OpenSSH\sshd.exe'
$keygen = 'C:\Windows\System32\OpenSSH\ssh-keygen.exe'

Write-Host '== 1. config =='
New-Item -ItemType Directory -Force -Path $sshDir | Out-Null
$cfg = Join-Path $sshDir 'sshd_config'
if (-not (Test-Path -LiteralPath $cfg)) {
    Copy-Item 'C:\Windows\System32\OpenSSH\sshd_config_default' $cfg
    Write-Host "[ok] created $cfg from sshd_config_default"
} else {
    Write-Host "[skip] $cfg already exists"
}

Write-Host '== 2. host keys =='
& $keygen -A
if ($LASTEXITCODE -ne 0) { throw "ssh-keygen -A failed with exit code $LASTEXITCODE" }

# Critical: ssh-keygen -A runs as the admin user, so the private keys are owned by
# that user and carry an ACE for them. sshd runs as LOCAL SYSTEM and rejects such
# keys with "UNPROTECTED PRIVATE KEY FILE ... too open", then exits with
# "no hostkeys available -- exiting" (service error 1067).
# Owner and DACL must be SYSTEM + Administrators only.
Write-Host '== 2b. host key owner/ACL =='
foreach ($k in @(Get-ChildItem $sshDir -Filter 'ssh_host_*_key')) {
    & icacls $k.FullName /setowner 'NT AUTHORITY\SYSTEM' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & takeown /f $k.FullName /a | Out-Null
    }
    $acl = New-Object System.Security.AccessControl.FileSecurity
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule(
        'NT AUTHORITY\SYSTEM', 'FullControl', 'Allow')))
    $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule(
        'BUILTIN\Administrators', 'FullControl', 'Allow')))
    Set-Acl -LiteralPath $k.FullName -AclObject $acl
    Write-Host "[ok] $($k.Name)"
}
Get-ChildItem $sshDir -Filter 'ssh_host_*_key' | Select-Object Name, Length | Format-Table -AutoSize

Write-Host '== 3. service =='
Set-Service -Name sshd -StartupType Automatic
if ((Get-Service sshd).Status -ne 'Running') { Start-Service sshd }
Start-Sleep -Seconds 2

Write-Host '== 4. firewall =='
$ruleName = 'OpenSSH SSH Server (sshd)'
if (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue) {
    Set-NetFirewallRule -DisplayName $ruleName -Enabled True -Profile Any
    Write-Host "[ok] existing rule enabled for all profiles: $ruleName"
} else {
    New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName $ruleName `
        -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
    Write-Host "[ok] created inbound rule for TCP 22"
}

Write-Host '== 5. result =='
Get-Service sshd | Format-Table Status, StartType, Name -AutoSize
Get-NetTCPConnection -LocalPort 22 -State Listen |
    Format-Table LocalAddress, LocalPort, OwningProcess -AutoSize
Get-NetConnectionProfile | Select-Object Name, NetworkCategory | Format-Table -AutoSize

Write-Host ''
Write-Host 'Done. Next:'
Write-Host '  1) add the laptop public key: scripts/remote/add-laptop-key.ps1 -PublicKey "ssh-ed25519 ..."'
Write-Host '  2) on the laptop: ssh wzy10@<LAN IP or Tailscale IP>'
Write-Host '  See docs/remote_desktop_workflow.md for the full runbook.'
