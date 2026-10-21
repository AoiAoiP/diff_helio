#Requires -RunAsAdministrator
# Second-stage fix for: sshd 1067, "no hostkeys available -- exiting".
#
# Stage 1 (fix-sshd-hostkeys.ps1) removed the extra WZY\wzy10 ACE from each host
# private key, but the key files are still OWNED by wzy10. sshd runs as SYSTEM and
# its host-key permission check also rejects keys whose owner is a non-service user.
#
# This script:
#   1. sets the owner of each ssh_host_*_key to NT AUTHORITY\SYSTEM
#      (fallback: takeown /a -> BUILTIN\Administrators) and re-applies the
#      SYSTEM + Administrators DACL;
#   2. tries to start sshd;
#   3. if it still fails, backs up the current host keys, regenerates them as
#      SYSTEM (so owner and ACL match a normal install), and tries again;
#   4. if it still fails, runs sshd -d as SYSTEM and prints the fatal error.

$ErrorActionPreference = 'Continue'
$dir    = 'C:\ProgramData\ssh'
$sshd   = 'C:\Windows\System32\OpenSSH\sshd.exe'
$keygen = 'C:\Windows\System32\OpenSSH\ssh-keygen.exe'

function Show-Keys {
    foreach ($k in @(Get-ChildItem -LiteralPath $dir -Filter 'ssh_host_*_key')) {
        Write-Host "--- $($k.Name)"
        icacls $k.FullName
        Write-Host ("owner: " + (Get-Acl -LiteralPath $k.FullName).Owner)
    }
}

function Set-KeyAcl([string]$path) {
    $acl = New-Object System.Security.AccessControl.FileSecurity
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule(
        'NT AUTHORITY\SYSTEM', 'FullControl', 'Allow')))
    $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule(
        'BUILTIN\Administrators', 'FullControl', 'Allow')))
    Set-Acl -LiteralPath $path -AclObject $acl
}

function Start-And-Report {
    Start-Service sshd
    Start-Sleep -Seconds 2
    Get-Service sshd | Format-Table Status, StartType, Name -AutoSize
    Get-NetTCPConnection -LocalPort 22 -State Listen -ErrorAction SilentlyContinue |
        Format-Table LocalAddress, LocalPort, OwningProcess -AutoSize
}

Write-Host '== 1. current keys =='
Show-Keys

Write-Host ''
Write-Host '== 2. owner -> SYSTEM =='
foreach ($k in @(Get-ChildItem -LiteralPath $dir -Filter 'ssh_host_*_key')) {
    & icacls $k.FullName /setowner 'NT AUTHORITY\SYSTEM' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[fallback] takeown /a : $($k.Name)"
        & takeown /f $k.FullName /a | Out-Null
    }
    Set-KeyAcl $k.FullName
}
Show-Keys

Write-Host ''
Write-Host '== 3. start =='
Start-And-Report
if ((Get-Service sshd).Status -eq 'Running') {
    Write-Host 'sshd is running. Stop here.'
    return
}

Write-Host ''
Write-Host '== 4. regenerate host keys as SYSTEM =='
$backup = Join-Path $dir ("hostkeys_backup_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -Path (Join-Path $dir 'ssh_host_*') -Destination $backup -Force
Remove-Item -Path (Join-Path $dir 'ssh_host_*') -Force
Write-Host "backup: $backup"

$cmd = 'C:\Windows\Temp\sshkeygen.cmd'
Set-Content -LiteralPath $cmd -Encoding ascii -Value @(
    '@echo off',
    '"C:\Windows\System32\OpenSSH\ssh-keygen.exe" -A'
)
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c $cmd"
Register-ScheduledTask -TaskName 'ssh-keygen-A' -Action $action -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName 'ssh-keygen-A'
Start-Sleep -Seconds 4
Unregister-ScheduledTask -TaskName 'ssh-keygen-A' -Confirm:$false
Remove-Item -LiteralPath $cmd -ErrorAction SilentlyContinue

Show-Keys
Start-And-Report
if ((Get-Service sshd).Status -eq 'Running') {
    Write-Host 'sshd is running after key regeneration. Stop here.'
    return
}

Write-Host ''
Write-Host '== 5. sshd -d as SYSTEM =='
$cmdPath = 'C:\Windows\Temp\sshd_diag.cmd'
$outPath = 'C:\Windows\Temp\sshd_diag.txt'
Set-Content -LiteralPath $cmdPath -Encoding ascii -Value @(
    '@echo off',
    '"C:\Windows\System32\OpenSSH\sshd.exe" -d -p 2223 > "C:\Windows\Temp\sshd_diag.txt" 2>&1'
)
Remove-Item -LiteralPath $outPath -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c $cmdPath"
Register-ScheduledTask -TaskName 'sshd-diag' -Action $action -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName 'sshd-diag'
Start-Sleep -Seconds 5
Get-Content -LiteralPath $outPath -ErrorAction SilentlyContinue | Select-Object -Last 40
Unregister-ScheduledTask -TaskName 'sshd-diag' -Confirm:$false
Get-Process sshd -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item -LiteralPath $cmdPath -ErrorAction SilentlyContinue
