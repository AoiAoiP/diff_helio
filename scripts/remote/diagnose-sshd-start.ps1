#Requires -RunAsAdministrator
# Diagnose why the sshd service exits with 1067.
# 1) prints ACLs, 2) retries the service, 3) if it still fails, runs sshd -d as SYSTEM
#    on port 2223 and captures the fatal error. Cleans up the temp task afterwards.
#
# Elevated usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\remote\diagnose-sshd-start.ps1

$ErrorActionPreference = 'Continue'
$ssh = 'C:\ProgramData\ssh'

Write-Host '== 1. ACL =='
foreach ($p in @($ssh, "$ssh\logs", "$ssh\sshd_config")) {
    Write-Host "--- $p"
    if (Test-Path -LiteralPath $p) {
        (Get-Acl -LiteralPath $p).AccessToString
    } else {
        Write-Host '(missing)'
    }
}

Write-Host ''
Write-Host '== 2. retry service =='
try {
    Start-Service sshd -ErrorAction Stop
    Write-Host 'Start-Service: OK'
} catch {
    Write-Host "Start-Service: FAILED - $($_.Exception.Message)"
}
Start-Sleep -Seconds 3
Get-Service sshd | Format-Table Status, StartType, Name -AutoSize
sc.exe queryex sshd

if ((Get-Service sshd).Status -eq 'Running') {
    Write-Host ''
    Write-Host 'Service is running. Stop here.'
    return
}

Write-Host ''
Write-Host '== 3. sshd -d as SYSTEM on port 2223 =='
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

Write-Host '--- sshd output (SYSTEM context) ---'
Get-Content -LiteralPath $outPath -ErrorAction SilentlyContinue | Select-Object -Last 50
Write-Host '--- task state ---'
(Get-ScheduledTask -TaskName 'sshd-diag').State

Unregister-ScheduledTask -TaskName 'sshd-diag' -Confirm:$false
Get-Process sshd -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item -LiteralPath $cmdPath -ErrorAction SilentlyContinue
Write-Host ''
Write-Host 'done.'
