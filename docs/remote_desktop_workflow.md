# 远程访问台式机（Tailscale + OpenSSH）

> 2026-10-19 建立并验证。适用场景：台式机在家中，笔记本通常在校园、偶尔带回家，需要在笔记本上通过 SSH 操作本仓库。
> 相关脚本在 `scripts/remote/`。安全边界：SSH 只在 Tailscale 虚拟网内可达，**不在路由器上对公网暴露 22**。

---

## 1. 拓扑与当前配置

```
笔记本（校园/家） ── Tailscale 虚拟网 100.64.0.0/10 ── 台式机（家）
        ssh wzy10@100.113.36.88
```

| 项目 | 值 |
|---|---|
| 台式机 | Windows 11 25H2（build 26200.9711），主机名 `WZY` |
| 台式机局域网 | `192.168.2.58/24`，网关 `192.168.2.1`（DHCP，仅在家有效） |
| Tailscale | 台式机 `100.113.36.88`（节点名 `wzy`，v1.104.1）；笔记本同账号 |
| SSH 服务 | OpenSSH_for_Windows_9.5p2（`sshd.exe` 9.5.6.4），服务 `sshd`，`Automatic` / `Running`，监听 `0.0.0.0:22` 与 `[::]:22` |
| 登录账户 | `wzy10`，**Microsoft 账户**，属于 `Administrators` |
| 认证方式 | 公钥（`C:\ProgramData\ssh\administrators_authorized_keys`）；密码登录仍为默认开启，建议关闭 |
| 主机密钥指纹 | ED25519 `SHA256:IjivWTa/N4HuK/aSiAa3rUXIUsPFlWBbaVNmRAvjxhU` |
| 防火墙规则 | `OpenSSH SSH Server (sshd)`，入站 TCP 22，`Profile=Any` |
| 电源 | 交流电不休眠（`STANDBYIDLE=0`） |

> 台式机局域网 IP 是 DHCP，可能变化；**远程访问一律用 Tailscale IP**，不要用 `192.168.2.58`。

---

## 2. 笔记本日常使用

`C:\Users\<你>\.ssh\config`：

```
Host desktop
    HostName 100.113.36.88
    User wzy10
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

之后：

```powershell
ssh desktop
```

首次连接会提示确认主机指纹，ED25519 应为 `SHA256:IjivWTa/N4HuK/aSiAa3rUXIUsPFlWBbaVNmRAvjxhU`。指纹变化时先核对，确属换机/换密钥再执行 `ssh-keygen -R 100.113.36.88`。

---

## 3. 一次性搭建（新机器或重装后）

### 3.1 安装 OpenSSH Server

管理员 PowerShell：

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-Service sshd -StartupType Automatic
Start-Service sshd
```

或直接运行 `scripts/remote/complete-sshd-setup.ps1`（已包含 3.2/3.3 的主机密钥与防火墙处理）。

### 3.2 修复主机密钥的 owner 与 ACL（关键坑）

`ssh-keygen -A` 由管理员账户执行时，私钥的所有者是该用户、ACL 里也带该用户的 ACE。`sshd` 以 **LOCAL SYSTEM** 运行，会把这条 ACE 视为 “accessible by others”，报：

```
WARNING: UNPROTECTED PRIVATE KEY FILE!
Permissions for '__PROGRAMDATA__\ssh/ssh_host_rsa_key' are too open.
sshd: no hostkeys available -- exiting.
```

服务随即以 `1067` 退出。即使只删掉多余 ACE，仍会因为**所有者不是 SYSTEM**而失败；两者都要修：

```powershell
$dir = 'C:\ProgramData\ssh'
Get-ChildItem $dir -Filter 'ssh_host_*_key' | ForEach-Object {
    icacls $_.FullName /setowner 'NT AUTHORITY\SYSTEM'
    icacls $_.FullName /inheritance:r
    icacls $_.FullName /grant:r 'SYSTEM:F' 'BUILTIN\Administrators:F'
}
Start-Service sshd
```

或运行 `scripts/remote/fix-sshd-hostkey-owner.ps1`：它会修 owner/ACL、尝试启动，失败时以 SYSTEM 身份重新生成主机密钥并打印 `sshd -d` 的 fatal 行。

验证：

```powershell
Get-Service sshd
Get-NetTCPConnection -LocalPort 22 -State Listen
Get-WinEvent -LogName 'OpenSSH/Operational' -MaxEvents 5
```

### 3.3 防火墙

安装 OpenSSH Server 时通常会自动创建 `OpenSSH SSH Server (sshd)` 规则，但默认只对 `Private` 生效。改成所有配置文件：

```powershell
Set-NetFirewallRule -DisplayName 'OpenSSH SSH Server (sshd)' -Enabled True -Profile Any
```

### 3.4 Tailscale

1. 两台机器安装 Tailscale（Windows 安装包或 `winget install --id Tailscale.Tailscale -e`），登录**同一账号**。
2. 台式机 `tailscale ip -4` 记下 `100.x.y.z`；`tailscale status` 确认两端 online。
3. 管理后台 **Machines → 台式机 → Disable key expiry**，避免节点密钥 180 天后过期。
4. 电源与更新：
   ```powershell
   powercfg /change standby-timeout-ac 0
   powercfg /change hibernate-timeout-ac 0
   Get-Service sshd, Tailscale | Format-Table Status,StartType,Name
   ```
   两个服务都是自启；重启后不需要登录桌面即可恢复 SSH。

### 3.5 写入笔记本公钥

笔记本：

```powershell
ssh-keygen -t ed25519 -C laptop
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

台式机管理员 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\remote\add-laptop-key.ps1 `
    -PublicKey "ssh-ed25519 AAAA... laptop"
```

脚本会写入 `C:\ProgramData\ssh\administrators_authorized_keys`（`wzy10` 在管理员组，sshd 读这个文件，**不读** `%USERPROFILE%\.ssh\authorized_keys`），把 ACL 收紧为仅 Administrators + SYSTEM，重启 sshd 并打印文件指纹。

### 3.6 验证

笔记本：

```powershell
Test-NetConnection 100.x.y.z -Port 22
ssh -v wzy10@100.x.y.z
```

`ssh -v` 中应出现 `Offering public key` 与 `Server accepts key`；若只看到 `Permission denied (publickey,password,keyboard-interactive)`，说明公钥未加载，检查 `administrators_authorized_keys` 的内容与 ACL。

---

## 4. 故障排查

### 4.1 sshd 启动失败：1067 / 事件 7034

先看日志：

```powershell
Get-WinEvent -LogName 'OpenSSH/Operational' -MaxEvents 20 |
    Format-List TimeCreated,Id,Message
```

- `Permissions for ... are too open` → 3.2 的 owner/ACL 修复；
- `no hostkeys available -- exiting` → 主机密钥缺失或权限/所有者不对；
- 需要 SYSTEM 上下文的完整报错 → 运行 `scripts/remote/diagnose-sshd-start.ps1`。

### 4.2 密码始终 `Permission denied`

本机 `wzy10` 是 **Microsoft 账户**，且注册表 `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device\DevicePasswordLessBuildVersion = 2`（仅允许 Windows Hello 登录）时，sshd 的密码认证会被系统拒绝。两个坑：

- 锁屏用的是 **Windows Hello PIN**，sshd 只接受微软账户的**在线密码**，PIN 永远不行；
- 即使输入在线密码，Hello-only 策略下也会失败（sshd 日志 `windows authentication failed. error 1326`）。

处理方式：**改用公钥登录**（推荐，不受影响）；或关闭“设置 → 账户 → 登录选项 → 仅允许 Microsoft 账户使用 Windows Hello 登录”，锁屏解锁后 `Restart-Service sshd`，再用在线密码。

### 4.3 笔记本连不上 / ping 不通

先确认是不是网络层问题：

```powershell
tailscale status
tailscale ping <台式机节点或 100.x.y.z>
Test-NetConnection 100.x.y.z -Port 22
```

- 笔记本在校园、台式机在家时，`192.168.2.58` 一定不可达（不同网段）；必须走 Tailscale IP。
- 若 Tailscale 显示 offline：检查两端客户端是否登录、台式机是否开机联网。
- 若 Tailscale 通但 22 不通：检查台式机防火墙规则是否为 `Profile=Any`、`sshd` 是否 Running。

### 4.4 主机指纹变化

更换主机密钥或重装后会出现 `REMOTE HOST IDENTIFICATION HAS CHANGED`。核对新指纹后：

```powershell
ssh-keygen -R 100.113.36.88
```

---

## 5. 安全与运维

- **只保留公钥登录**：调通后把 `C:\ProgramData\ssh\sshd_config` 的 `PasswordAuthentication` 改为 `no`，`Restart-Service sshd`。当前该行仍是默认注释状态（= yes）。
- **不要把 22 映射到公网**。远程访问只走 Tailscale；如需更严，可在 Tailscale ACL 中限制只有笔记本能访问台式机的 22 端口。
- **Tailscale 节点密钥**：在管理后台对台式机禁用 key expiry，否则半年后失效。
- **BitLocker**：若系统盘启用 BitLocker，重启后需要人工解锁，SSH 不会自动恢复；远程重启前要考虑这一点。
- **Windows 更新**：重启后 `sshd` 与 `Tailscale` 均为自启，不需要登录桌面；建议设置活动时间或暂停更新，避免半夜重启。
- **电源**：交流电已设为不休眠；不要手动关机，否则远程不可达。

---

## 6. 脚本清单（`scripts/remote/`）

| 脚本 | 用途 | 备注 |
|---|---|---|
| `check-readiness.ps1` | 只读自检：身份、网络、sshd、防火墙、密钥、项目目录、GPU/Python/ANSYS、电源 | 换机/交接前先跑，输出 JSON |
| `complete-sshd-setup.ps1` | 安装后的完整配置：生成 `sshd_config`、主机密钥并修 owner/ACL、启动服务、防火墙 `Profile=Any` | 幂等，可重复执行 |
| `fix-sshd-hostkey-owner.ps1` | 1067 修复：改 owner 为 SYSTEM、重设 DACL；仍失败则以 SYSTEM 重新生成主机密钥并抓 `sshd -d` 输出 | 已在 2026-10-19 的故障机上验证 |
| `add-laptop-key.ps1` | 把笔记本公钥写入 `administrators_authorized_keys`，收紧 ACL，重启 sshd | 每次新增客户端时使用 |
| `diagnose-sshd-start.ps1` | 打印 ACL、重试启动、以 SYSTEM 身份跑 `sshd -d -p 2223` 并抓 fatal 行 | 排查 1067 的通用入口 |

---

## 7. 2026-10-19 排障时间线（存档）

| 时间 | 事件 |
|---|---|
| 15:14 | 安装 OpenSSH Server（`sshd.exe` 9.5.6.4） |
| 15:24 | 首次 `Start-Service sshd` → 1067；`sshd -d` 报三把主机密钥 “too open” / `no hostkeys` |
| 15:33 | 去掉私钥上 `WZY\wzy10` 的 ACE → 仍 1067（所有者仍是 wzy10） |
| 15:48 | 把私钥 owner 改为 `NT AUTHORITY\SYSTEM` → 服务 Running，15:49:38 开始监听 22 |
| 21:04 | 笔记本经 Tailscale（来源 `100.103.35.43`）连接，密码认证两次 `Failed password`；账户是 Microsoft 账户 + Hello-only |
| 21:08 | 写入 `administrators_authorized_keys`（89 B，1 把 ed25519 公钥），公钥登录成功 |

根因归纳：**主机密钥必须同时满足 owner=SYSTEM/Administrators 与 DACL 仅 SYSTEM+Administrators**；**Microsoft 账户的 sshd 密码认证受 Hello-only 策略限制，应直接用公钥**。

---

## 8. 参考

- [OpenSSH 服务 1053/1067/7034 与 `C:\ProgramData\ssh` 权限（Microsoft Learn）](https://learn.microsoft.com/zh-cn/troubleshoot/windows-server/system-management-components/error-1053-1067-7034-after-update-openssh-doesnt-start)
- [Microsoft 账户无法用密码登录 SSH（Microsoft Q&A）](https://learn.microsoft.com/en-us/answers/questions/1332375/unable-to-log-into-ssh-server-using-microsoft-acco)
- [Tailscale Windows 安装与 CLI](https://tailscale.com/kb/1022/install-windows)
- [OpenSSH for Windows 密钥管理](https://learn.microsoft.com/zh-cn/windows-server/administration/openssh/openssh_keymanagement)
