# 台式机「可连接状态」自检 Prompt（供台式机上的 DSH 使用）

> 用途：在**台式机**的 DSH 会话里粘贴执行，判断这台机器现在能否被笔记本通过 SSH 连上，
> 并输出笔记本侧配置所需的信息（主机名、IP、端口、登录用户、是否管理员、项目路径）。
>
> 配套脚本：`scripts/remote/check-readiness.ps1`（只读，输出 JSON）。
> 相关文档：`docs/remote_desktop_workflow.md`（完整搭建方案）。

---

## 0. 怎么用

在台式机的 DSH 里，任选一种：

1. 直接说：**「按 docs/prompts/desktop_link_readiness.md 执行台式机可连接自检」**
2. 或者把下面 §1 的整段提示词复制进去。

自检完成后，把 DSH 输出的「交给笔记本的信息」代码块发回笔记本即可。

---

## 1. 提示词正文（复制这一段）

```text
你是这台 Windows 台式机的运维助手。任务：只读检查本机当前是否处于「可被笔记本通过 SSH 连接」的状态，
并输出笔记本配置所需的信息。

【硬性规则】
1. 只读。不要启动/停止服务，不要改防火墙，不要改 sshd_config，不要增删密钥，不要重启。
2. 不要尝试提权（不要 Start-Process -Verb RunAs、不要 runas）。需要管理员的检查项，读不到就标 UNKNOWN 并给出管理员命令。
3. 绝不打印私钥内容。authorized_keys 只报行数与公钥指纹（ssh-keygen -lf）。
4. 每条检查都要有「实际执行的命令」和「原始输出摘要」，不要凭印象判断。
5. 中文汇报，命令保持原样。

【第 0 步：优先跑脚本】
如果仓库里有 scripts/remote/check-readiness.ps1，先执行：
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\remote\check-readiness.ps1
把输出的 JSON 保留下来作为证据。若脚本不存在或执行失败，走第 1 步的手工检查。

【第 1 步：手工检查（按顺序，记录命令与输出）】
A. 身份与网络
   A1. hostname
   A2. whoami
   A3. ipconfig | findstr /i "IPv4"
   A4. 是否管理员：([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
   A5. 网络位置：Get-NetConnectionProfile | Select Name,NetworkCategory
       （Public 会挡入站 SSH，需要改成 Private 或放行规则）
B. SSH 服务端
   B1. Get-WindowsCapability -Online -Name OpenSSH.Server*
   B2. Get-Service sshd | Select Status,StartType
   B3. Get-NetTCPConnection -LocalPort 22 -State Listen（读不到就用 netstat -ano | findstr :22）
   B4. Get-NetFirewallRule -Direction Inbound | Where DisplayName -like "*OpenSSH*" |
       Select DisplayName,Enabled,Profile
       再看端口：Get-NetFirewallPortFilter；来源：Get-NetFirewallAddressFilter
   B5. sshd_config 关键项：Get-Content C:\ProgramData\ssh\sshd_config |
       Select-String "^\s*(Port|PasswordAuthentication|PubkeyAuthentication|AllowUsers)"
   B6. 最近日志：Get-Content C:\ProgramData\ssh\logs\sshd.log -Tail 20
       （关注 accepted publickey / Failed password / Connection closed）
C. 密钥
   C1. 用户级：$env:USERPROFILE\.ssh\authorized_keys 是否存在、有效行数、指纹
       ssh-keygen -lf $env:USERPROFILE\.ssh\authorized_keys
   C2. 管理员级：C:\ProgramData\ssh\administrators_authorized_keys 是否存在、行数、指纹
       icacls C:\ProgramData\ssh\administrators_authorized_keys
       权限必须只含 Administrators 与 SYSTEM；出现 Everyone / Users / Authenticated Users 即失效。
   C3. 当前账户是否在 Administrators 组：whoami /groups | findstr /i "S-1-5-32-544"
D. 项目与运行时
   D1. L:\Code\bezier_opt_desktop 是否存在；顶层条目数
   D2. git -C L:\Code\bezier_opt_desktop status --short；git rev-parse --abbrev-ref HEAD；git rev-parse --short HEAD
   D3. build\src\Release\bezier_opt.exe 是否存在、大小
   D4. data_proxy\gravity_10deg.bin 字节数（应为 12288）；gravity_angles.json 的 format（应为 w_du_dv_v2）
   D5. python --version；python -c "import matplotlib,numpy;print(matplotlib.__version__,numpy.__version__)"
   D6. nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
   D7. ANSYS：C:\Program Files\ANSYS Inc 下的版本目录与 ANSYS*.exe；
       环境变量 ANSYSLMD_LICENSE_FILE / ANSYSLI_SERVERS；
       Get-Service | Where Name -like "*ansys*"
E. 数据面与长任务（可选）
   E1. Get-SmbShare -Name Code（或 net share）是否已开
   E2. 项目所在盘的剩余空间
   E3. schtasks /query /fo LIST 是否可读
   E4. 当前电源计划与待机超时：powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE
       （长任务期间不允许睡眠）

【第 2 步：汇报格式】
先给一张表：
| # | 检查项 | 期望 | 实测 | 结论 |
结论只用 PASS / FAIL / WARN / UNKNOWN。

再给判定：
- READY：sshd 已安装、Running、Automatic、22 端口在听、防火墙有入站规则、authorized_keys 至少 1 把有效公钥、项目目录存在。
- READY_WITH_WARNINGS：SSH 通道本身可用，但存在非阻断问题（如无 SMB、待机会休眠、密码登录未关、项目目录缺失）。
- NOT_READY：sshd 未装/未运行/未监听，或没有任何可用公钥。

最后输出「交给笔记本的信息」代码块，格式固定：
  hostname: <...>
  ipv4: <...>
  ssh_port: 22
  login_user: <...>
  in_admin_group: true/false
  project_path: L:\Code\bezier_opt_desktop

【第 3 步：失败项修复建议】
对每个 FAIL，给出「在管理员 PowerShell 里执行」的修复命令（不要自己执行），并在末尾引用
docs/remote_desktop_workflow.md 的对应小节。
```

---

## 2. 判定标准（与脚本一致）

| 检查 | 期望 | 不满足时影响 |
|---|---|---|
| `ssh_installed` | OpenSSH Server 已安装 | 完全无法连接 |
| `ssh_running` | 服务 `Running` | 完全无法连接 |
| `ssh_autostart` | `Automatic` | 台式机重启后失联 |
| `ssh_listening` | 22 端口在听 | 连不上（被别的进程占用或不监听） |
| `firewall_rule` | 入站规则存在且启用 | 端口通但连接被丢 |
| `key_present` | 用户级或管理员级至少 1 把公钥 | 只能密码登录（或拒绝） |
| `admin_key_acl` | 管理员密钥文件权限收紧 | 密钥被忽略、一直要密码 |
| `project_present` | `L:\Code\bezier_opt_desktop` 存在 | 能连上但没东西可跑 |
| `gravity_ok` | 重力 bin = 12,288 B | 跑出来的结果不可信（幻影重力） |

---

## 3. 失败项修复命令（台式机，管理员 PowerShell）

```powershell
# ssh_installed
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# ssh_running / ssh_autostart
Set-Service sshd -StartupType Automatic
Start-Service sshd

# firewall_rule（按实际网段改）
New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" `
  -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 `
  -RemoteAddress 10.0.0.0/8

# key_present（普通账户）
$pub = "ssh-ed25519 AAAA... laptop->desktop"
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh" | Out-Null
Add-Content "$env:USERPROFILE\.ssh\authorized_keys" $pub

# key_present（Administrators 组账户走这个文件）
Add-Content "C:\ProgramData\ssh\administrators_authorized_keys" $pub
icacls "C:\ProgramData\ssh\administrators_authorized_keys" /inheritance:r `
  /grant "Administrators:F" /grant "SYSTEM:F"

# 改完重启服务
Restart-Service sshd

# 关密码登录（密钥验证通过后再做）
notepad C:\ProgramData\ssh\sshd_config   # PasswordAuthentication no
Restart-Service sshd
```

---

## 4. 笔记本侧配套（10 秒）

拿到「交给笔记本的信息」后，在笔记本执行：

```powershell
# 1) 连通性
Test-NetConnection <台式机IP> -Port 22

# 2) 免密登录
ssh -o BatchMode=yes -o ConnectTimeout=6 <用户名>@<台式机IP> "hostname"

# 3) 写入 ~/.ssh/config（Host 名 desktop）
```

```
Host desktop
    HostName <台式机IP>
    User <用户名>
    Port 22
    IdentityFile ~/.ssh/id_ed25519_desktop
    IdentitiesOnly yes
    ServerAliveInterval 30
```

---

## 5. 常见误判

1. **防火墙规则在、但网络位置是 Public**：Windows 的入站规则按 profile 生效，Public 下可能不匹配；把网络改成 Private 或显式给规则加 Public profile。
2. **密钥文件权限过宽**：`administrators_authorized_keys` 只要对 `Users`/`Everyone` 可读，sshd 会静默忽略，表现为"一直要密码"，日志里是 `Authentication refused`。
3. **服务是 Manual**：`Start-Service` 后能连，重启就没了，必须 `Automatic`。
4. **IP 变了**：家用路由器 DHCP 续租会换地址，建议做静态绑定。
5. **同一台机器两个 sshd 或端口占用**：`netstat -ano | findstr :22` 看 PID 是否对应 sshd。
6. **笔记本与台式机不在同一可达网段**：先 `Test-NetConnection`，不通再谈跳板/VPN（见 `docs/remote_desktop_workflow.md` §8）。

---

## 6. 安全约束

- 自检全程只读；修复命令由人来执行。
- 不打印私钥；只报公钥指纹。
- 防火墙来源限制在实验网段，不要 `Any`。
- 密码登录在密钥验证通过后关闭。
