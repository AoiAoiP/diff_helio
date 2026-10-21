# check-readiness.ps1 — 台式机「可连接状态」自检（只读，不修改任何配置）
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\remote\check-readiness.ps1
#      可选：-ProjectPath "L:\Code\bezier_opt_desktop" -SshPort 22 -OutFile "$env:TEMP\readiness.json"
# 输出：stdout 为 JSON（供 DSH / 笔记本解析），同时写一份到 -OutFile（若指定）

[CmdletBinding()]
param(
    [string]$ProjectPath = "L:\Code\bezier_opt_desktop",
    [int]$SshPort = 22,
    [string]$OutFile = ""
)

$ErrorActionPreference = "SilentlyContinue"
$ProgressPreference = "SilentlyContinue"

function Try-Get {
    param([scriptblock]$Block)
    try { & $Block } catch { $null }
}

function Test-PathSafe {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    return (Test-Path -LiteralPath $Path -ErrorAction SilentlyContinue)
}

$r = [ordered]@{}
$r.generated_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
$r.script_version = "1.0"

# ---------- 1. 身份与系统 ----------
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$pr = New-Object Security.Principal.WindowsPrincipal($id)
$isAdmin = $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$groups = Try-Get { (whoami /groups) -join "`n" }
$isAdminGroup = $false
if ($groups) { $isAdminGroup = ($groups -match "S-1-5-32-544") }

$r.system = [ordered]@{
    hostname      = $env:COMPUTERNAME
    user          = whoami
    is_admin      = $isAdmin
    in_admin_group= $isAdminGroup
    os            = (Try-Get { (Get-CimInstance Win32_OperatingSystem).Caption })
    version       = (Try-Get { (Get-CimInstance Win32_OperatingSystem).Version })
    arch          = $env:PROCESSOR_ARCHITECTURE
    ps_version    = $PSVersionTable.PSVersion.ToString()
}

# ---------- 2. 网络 ----------
$ipv4 = @()
$ips = Try-Get { Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop | Where-Object { $_.IPAddress -notlike "127.*" } }
if ($ips) {
    $ipv4 = @($ips | ForEach-Object { [ordered]@{ iface = $_.InterfaceAlias; address = $_.IPAddress; prefix = $_.PrefixLength } })
} else {
    $raw = Try-Get { (ipconfig) -join "`n" }
    if ($raw) {
        $ipv4 = @([regex]::Matches($raw, "IPv4[^:]*:\s*([0-9\.]+)") | ForEach-Object { [ordered]@{ iface = "unknown"; address = $_.Groups[1].Value; prefix = $null } })
    }
}
$gw = Try-Get { (Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction Stop | Select-Object -First 1).NextHop }
if (-not $gw) {
    $raw = Try-Get { (ipconfig) -join "`n" }
    if ($raw) { $m = [regex]::Match($raw, "Default Gateway[^:]*:\s*([0-9\.]+)"); if ($m.Success) { $gw = $m.Groups[1].Value } }
}
$netProfile = Try-Get { (Get-NetConnectionProfile -ErrorAction Stop | Select-Object -First 1).NetworkCategory }
$r.network = [ordered]@{
    ipv4            = $ipv4
    default_gateway = $gw
    profile         = $netProfile   # Public 会挡 SSH，注意
}

# ---------- 3. SSH 服务端 ----------
$cap = Try-Get { Get-WindowsCapability -Online -Name "OpenSSH.Server*" -ErrorAction Stop | Select-Object -First 1 }
$svc = Try-Get { Get-Service sshd -ErrorAction Stop }
$listening = $false
$listenDetail = $null
$tcp = Try-Get { Get-NetTCPConnection -LocalPort $SshPort -State Listen -ErrorAction Stop | Select-Object -First 3 }
if ($tcp) {
    $listening = $true
    $listenDetail = @($tcp | ForEach-Object { [ordered]@{ local = "$($_.LocalAddress):$($_.LocalPort)"; pid = $_.OwningProcess } })
} else {
    $ns = Try-Get { (netstat -ano | Select-String -Pattern (":{0}\s" -f $SshPort)) -join "`n" }
    if ($ns -and $ns -match "LISTENING") { $listening = $true; $listenDetail = "netstat: LISTENING" }
}

$fw = [ordered]@{ found = $false; enabled = $null; remote_address = $null; port = $SshPort; detail = $null }
$fwRules = Try-Get { Get-NetFirewallRule -Direction Inbound -ErrorAction Stop | Where-Object { $_.DisplayName -like "*OpenSSH*" -or $_.Name -like "*OpenSSH*" } }
if ($fwRules) {
    foreach ($rule in $fwRules) {
        $pf = Try-Get { $rule | Get-NetFirewallPortFilter }
        $addr = Try-Get { $rule | Get-NetFirewallAddressFilter }
        $portOk = $true
        if ($pf -and $pf.LocalPort) {
            $portOk = (@($pf.LocalPort) -contains "$SshPort") -or (@($pf.LocalPort) -contains "Any")
        }
        if ($portOk) {
            $fw.found = $true
            $fw.enabled = [string]$rule.Enabled
            $fw.remote_address = if ($addr) { ($addr.RemoteAddress -join ",") } else { $null }
            $fw.detail = $rule.DisplayName
        }
    }
}
if (-not $fw.found) {
    $ns = Try-Get { (netsh advfirewall firewall show rule name=all) -join "`n" }
    if ($ns -and $ns -match "OpenSSH") { $fw.found = $true; $fw.detail = "netsh: OpenSSH rule present (details need admin)" }
}

$cfgPath = "C:\ProgramData\ssh\sshd_config"
$cfg = [ordered]@{ path = $cfgPath; readable = (Test-PathSafe $cfgPath); port = $null; password_auth = $null; pubkey_auth = $null; allow_users = $null }
if ($cfg.readable) {
    $txt = Try-Get { Get-Content -LiteralPath $cfgPath -ErrorAction Stop }
    if ($txt) {
        $joined = $txt -join "`n"
        if ($joined -match "(?m)^\s*Port\s+(\d+)") { $cfg.port = $Matches[1] }
        if ($joined -match "(?m)^\s*PasswordAuthentication\s+(\w+)") { $cfg.password_auth = $Matches[1] }
        if ($joined -match "(?m)^\s*PubkeyAuthentication\s+(\w+)") { $cfg.pubkey_auth = $Matches[1] }
        if ($joined -match "(?m)^\s*AllowUsers\s+(.+)$") { $cfg.allow_users = $Matches[1].Trim() }
    }
}

$capState = if ($cap) { [string]$cap.State } else { $null }
$svcStatus = if ($svc) { [string]$svc.Status } else { "not-installed" }
$svcStartType = if ($svc) { [string]$svc.StartType } else { $null }
$r.ssh = [ordered]@{
    capability_installed = $capState
    service_status       = $svcStatus
    service_start_type   = $svcStartType
    listening            = $listening
    listening_detail     = $listenDetail
    firewall             = $fw
    config               = $cfg
    log_path             = "C:\ProgramData\ssh\logs\sshd.log"
    log_tail             = (Try-Get { (Get-Content "C:\ProgramData\ssh\logs\sshd.log" -Tail 20 -ErrorAction Stop) -join "`n" })
}

# ---------- 4. 密钥 ----------
function Get-KeyInfo {
    param([string]$Path)
    $info = [ordered]@{ path = $Path; exists = (Test-PathSafe $Path); lines = 0; fingerprints = @(); acl_ok = $null; acl = $null }
    if ($info.exists) {
        $content = Try-Get { Get-Content -LiteralPath $Path -ErrorAction Stop | Where-Object { $_.Trim() -ne "" -and -not $_.TrimStart().StartsWith("#") } }
        if ($content) { $info.lines = @($content).Count }
        $fp = Try-Get { (ssh-keygen -lf $Path) -join "`n" }
        if ($fp) { $info.fingerprints = @($fp -split "`n" | Where-Object { $_ }) }
        $acl = Try-Get { (icacls $Path) -join "`n" }
        if ($acl) {
            $info.acl = $acl
            $info.acl_ok = -not ($acl -match "Everyone|BUILTIN\\Users|Authenticated Users|NT AUTHORITY\\INTERACTIVE")
        }
    }
    return $info
}
$userKeys = Get-KeyInfo (Join-Path $env:USERPROFILE ".ssh\authorized_keys")
$adminKeys = Get-KeyInfo "C:\ProgramData\ssh\administrators_authorized_keys"
$r.keys = [ordered]@{
    user_authorized_keys   = $userKeys
    admin_authorized_keys  = $adminKeys
    note = "Administrators 组账户登录时 sshd 读 administrators_authorized_keys；两处任一有公钥即可。"
}

# ---------- 5. 项目目录 ----------
$proj = [ordered]@{
    path             = $ProjectPath
    exists           = (Test-PathSafe $ProjectPath)
    top_entries      = 0
    git_branch       = $null
    git_head         = $null
    git_dirty_files  = $null
    exe_exists       = $false
    exe_size_kb      = $null
    gravity_bin_bytes= $null
    gravity_format   = $null
}
if ($proj.exists) {
    $top = Try-Get { Get-ChildItem -LiteralPath $ProjectPath -Force -ErrorAction Stop }
    if ($top) { $proj.top_entries = @($top).Count }
    $proj.git_branch = Try-Get { (git -C $ProjectPath rev-parse --abbrev-ref HEAD 2>$null) }
    $proj.git_head = Try-Get { (git -C $ProjectPath rev-parse --short HEAD 2>$null) }
    $dirty = Try-Get { (git -C $ProjectPath status --porcelain 2>$null) }
    if ($dirty) { $proj.git_dirty_files = @($dirty).Count } else { $proj.git_dirty_files = 0 }
    $exe = Join-Path $ProjectPath "build\src\Release\bezier_opt.exe"
    if (Test-PathSafe $exe) {
        $proj.exe_exists = $true
        $proj.exe_size_kb = [math]::Round((Get-Item -LiteralPath $exe).Length / 1KB, 1)
    }
    $gb = Join-Path $ProjectPath "data_proxy\gravity_10deg.bin"
    if (Test-PathSafe $gb) { $proj.gravity_bin_bytes = (Get-Item -LiteralPath $gb).Length }
    $ga = Join-Path $ProjectPath "data_proxy\gravity_angles.json"
    if (Test-PathSafe $ga) {
        $j = Try-Get { Get-Content -LiteralPath $ga -Raw -ErrorAction Stop | ConvertFrom-Json }
        if ($j -and $j.format) { $proj.gravity_format = $j.format }
    }
}
$r.project = $proj

# ---------- 6. 运行时（Python / GPU / Vulkan / ANSYS） ----------
$py = Try-Get { (python --version 2>&1) -join " " }
$mpl = Try-Get { (python -c "import matplotlib; print(matplotlib.__version__)" 2>&1) -join " " }
$numpy = Try-Get { (python -c "import numpy; print(numpy.__version__)" 2>&1) -join " " }
$gpu = Try-Get { (nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>&1) -join "; " }
if (-not $gpu) {
    $gpu = Try-Get { ((Get-CimInstance Win32_VideoController | Select-Object -First 2 | ForEach-Object { $_.Name }) -join "; ") }
}
$vulkanDir = Try-Get { (Get-ChildItem "C:\VulkanSDK" -Directory -ErrorAction Stop | Select-Object -ExpandProperty Name) -join "," }

$ansys = [ordered]@{ found = $false; exe = $null; version = $null; license_env = @{}; services = @() }
$ansysRoot = "C:\Program Files\ANSYS Inc"
if (Test-PathSafe $ansysRoot) {
    $verDirs = Try-Get { Get-ChildItem $ansysRoot -Directory -ErrorAction Stop | Sort-Object Name -Descending }
    foreach ($v in $verDirs) {
        $cand = Try-Get { Get-ChildItem (Join-Path $v.FullName "ansys\bin\winx64") -Filter "ANSYS*.exe" -ErrorAction Stop | Select-Object -First 1 }
        if ($cand) {
            $ansys.found = $true
            $ansys.exe = $cand.FullName
            $ansys.version = $v.Name
            break
        }
    }
}
foreach ($n in @("ANSYSLMD_LICENSE_FILE", "ANSYSLI_SERVERS", "AWP_ROOT241", "ANSYS_ROOT")) {
    $val = [Environment]::GetEnvironmentVariable($n, "Machine")
    if (-not $val) { $val = [Environment]::GetEnvironmentVariable($n, "User") }
    if ($val) { $ansys.license_env[$n] = $val }
}
$ansys.services = @(Try-Get { Get-Service -ErrorAction Stop | Where-Object { $_.Name -like "*ansys*" -or $_.DisplayName -like "*ANSYS*" } | Select-Object -First 5 | ForEach-Object { "$($_.Name):$($_.Status)" } })

$r.runtime = [ordered]@{
    python        = $py
    matplotlib    = $mpl
    numpy         = $numpy
    gpu           = $gpu
    vulkan_sdk    = $vulkanDir
    ansys         = $ansys
}

# ---------- 7. 数据面（SMB / 磁盘） ----------
$smb = [ordered]@{ share_found = $false; path = $null; access = @(); note = "开共享需管理员；不开可走 SSHFS 或 scp" }
$sh = Try-Get { Get-SmbShare -Name "Code" -ErrorAction Stop }
if ($sh) {
    $smb.share_found = $true
    $smb.path = $sh.Path
    $smb.access = @(Try-Get { Get-SmbShareAccess -Name "Code" -ErrorAction Stop | ForEach-Object { "$($_.AccountName):$($_.AccessRight)" } })
} else {
    $ns = Try-Get { (net share 2>$null) -join "`n" }
    if ($ns -and $ns -match "(?m)^Code\s") { $smb.share_found = $true; $smb.path = "net share: Code" }
}
$driveLetter = ([System.IO.Path]::GetPathRoot($ProjectPath) -replace '[:\\]', '')
$disk = Try-Get {
    $d = Get-PSDrive -Name $driveLetter -ErrorAction Stop
    [ordered]@{ drive = $d.Name; used_gb = [math]::Round($d.Used / 1GB, 1); free_gb = [math]::Round($d.Free / 1GB, 1) }
}
if (-not $disk) {
    $root = [System.IO.Path]::GetPathRoot($ProjectPath)
    $di = Try-Get { New-Object System.IO.DriveInfo($root) }
    if ($di) { $disk = [ordered]@{ drive = $root; used_gb = [math]::Round(($di.TotalSize - $di.AvailableFreeSpace) / 1GB, 1); free_gb = [math]::Round($di.AvailableFreeSpace / 1GB, 1) } }
}
$r.data_plane = [ordered]@{ smb = $smb; disk = $disk }

# ---------- 8. 长任务能力 ----------
$sched = [ordered]@{ schtasks_present = [bool](Get-Command schtasks.exe -ErrorAction SilentlyContinue); can_query = $false }
$q = Try-Get { (schtasks /query /fo LIST 2>$null | Select-Object -First 3) -join "`n" }
if ($q) { $sched.can_query = $true }
$power = [ordered]@{ active_scheme = (Try-Get { (powercfg /getactivescheme) -join " " }); standby_ac_seconds = $null }
$pq = Try-Get { (powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 2>$null) -join "`n" }
if ($pq -match "当前交流电源设置索引:\s*0x([0-9a-fA-F]+)") {
    $power.standby_ac_seconds = [Convert]::ToInt32($Matches[1], 16)
} elseif ($pq -match "Current AC Power Setting Index:\s*0x([0-9a-fA-F]+)") {
    $power.standby_ac_seconds = [Convert]::ToInt32($Matches[1], 16)
}
$r.long_jobs = [ordered]@{ scheduled_tasks = $sched; power = $power }

# ---------- 9. 判定 ----------
$checks = [ordered]@{}
$checks["ssh_installed"]  = ($r.ssh.capability_installed -eq "Installed") -or ($r.ssh.service_status -ne "not-installed")
$checks["ssh_running"]    = ($r.ssh.service_status -eq "Running")
$checks["ssh_listening"]  = [bool]$r.ssh.listening
$checks["ssh_autostart"]  = ($r.ssh.service_start_type -eq "Automatic")
$checks["firewall_rule"]  = [bool]$r.ssh.firewall.found
$checks["key_present"]    = (($r.keys.user_authorized_keys.lines -gt 0) -or ($r.keys.admin_authorized_keys.lines -gt 0))
$checks["admin_key_acl"]  = if ($r.keys.admin_authorized_keys.lines -gt 0) { [bool]$r.keys.admin_authorized_keys.acl_ok } else { $true }
$checks["project_present"]= [bool]$r.project.exists
$checks["gravity_ok"]     = ($r.project.gravity_bin_bytes -eq 12288)

$failed = @($checks.Keys | Where-Object { -not $checks[$_] })
$unknown = @()
if ($null -eq $r.ssh.firewall.found) { $unknown += "firewall_rule" }

$verdict = "READY"
if ($failed.Count -gt 0) {
    if ($failed -contains "ssh_installed" -or $failed -contains "ssh_running" -or $failed -contains "ssh_listening" -or $failed -contains "key_present") {
        $verdict = "NOT_READY"
    } else {
        $verdict = "READY_WITH_WARNINGS"
    }
}

$r.checks = $checks
$r.failed = $failed
$r.verdict = $verdict
$r.handoff = [ordered]@{
    hostname        = $env:COMPUTERNAME
    ipv4            = @($ipv4 | ForEach-Object { $_.address })
    ssh_port        = $SshPort
    login_user      = (whoami).Split("\")[-1]
    in_admin_group  = $isAdminGroup
    project_path    = $ProjectPath
    note            = "把这 6 项发给笔记本侧，写入 ~/.ssh/config 的 Host desktop 段"
}

$json = $r | ConvertTo-Json -Depth 8
if ($OutFile) {
    try { $json | Set-Content -LiteralPath $OutFile -Encoding UTF8 } catch { }
}
$json
