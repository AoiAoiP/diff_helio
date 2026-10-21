# 远程台式机工作方案（SSH + SMB，不依赖第三方远控）

日期：2026-10-19　｜　适用：笔记本 `LAPTOP-HCRHFPOQ` → Windows 台式机（ANSYS 许可证所在机）

---

## 0. 结论

可行，而且不需要装任何第三方远程控制软件。Windows 10/11 自带 **OpenSSH Server**，装上就是标准答案：

- **控制面**用 SSH：执行命令、跑 ANSYS 批处理、跑优化器、看日志；
- **数据面**用 SMB 共享：把台式机的 `L:\Code` 映射到笔记本的 `L:`，两端路径完全一致，大文件不用来回拷。

本机现状（已核实）：

| 项 | 状态 |
|---|---|
| `ssh.exe` / `scp.exe` / `sftp.exe` | 已装（OpenSSH_for_Windows_9.5p2） |
| `~/.ssh/id_rsa` + `~/.ssh/config` | 已有，且 `Feng3090`（10.76.0.64）实测免密可连 |
| 到实验网段的路由 | 通（10.76.0.64 的 22 端口可达） |
| 笔记本网段 | 10.196.221.23 |
| 台式机 SSH 服务 | 未知，需按 §3 开启 |

> 注：`Feng3090` 是 Linux 机（`hostname` 返回 `jq`），不是你这台 Windows 台式机。它可以当跳板或对照，但 Windows 侧仍需单独配置。

---

## 1. 目标形态

```
[笔记本 D:\Code\heliostat_optimize\bezier_opt]
      │
      │  ① 控制面：ssh desktop "命令"        （轻量、可脚本、可退出码）
      ▼
[台式机 sshd :22] ── 执行 ──> ANSYS MAPDL / bezier_opt.exe / python 脚本
      ▲
      │  ② 数据面：SMB \\desktop\Code 映射为 L:
      │
[笔记本 L:\Code\bezier_opt_desktop]  ←== 同一份文件 ==→  [台式机 L:\Code\bezier_opt_desktop]
```

两条链路分开的理由：SSH 适合"发命令、收退出码、看日志"，不适合反复传 100 MB 级数据；SMB 适合"两边看到同一份文件"，而且映射成同一个盘符后，脚本里的 `L:\Code\...` 在两端都成立。

---

## 2. 方案对比（为什么选 SSH）

| 方案 | 免 GUI | 传文件 | 长任务 | 需要装东西 | 适配本场景 |
|---|---|---|---|---|---|
| **SSH（推荐）** | ✅ | `scp`/`sftp`/SMB | ✅ 可 `schtasks` 托管 | 台式机开系统组件 | 最佳：脚本化、可版本化、和 git 工作流一致 |
| WinRM / PowerShell Remoting | ✅ | ❌ 需额外共享 | ✅ | 开服务 + 信任配置 | 备选：纯 PowerShell 环境顺手，但传文件麻烦 |
| RDP | ❌ 图形界面 | 剪贴板/驱动器重定向 | ✅ | Pro 版 + 开服务 | 仅用于偶尔开 ANSYS GUI，不算"自动化" |
| SMB + `schtasks` | ✅ | ✅ | ✅ | 只需共享 | 备选：不用开 SSH，但排错靠事件查看器，体验差 |
| 向日葵 / ToDesk | ❌ | 慢 | ❌ | 第三方 | 就是要摆脱的方案 |

---

## 3. 台式机侧一次性配置（管理员 PowerShell，约 10 分钟）

### 3.1 安装并启动 OpenSSH Server

```powershell
# 管理员 PowerShell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

Set-Service sshd -StartupType Automatic
Start-Service sshd

# 防火墙：只放行内网来源（按你的实际网段改，10.0.0.0/8 覆盖 10.x）
New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" `
  -DisplayName "OpenSSH Server (sshd)" -Enabled True `
  -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 `
  -RemoteAddress 10.0.0.0/8

Get-Service sshd          # 应为 Running
```

### 3.2 记下地址与账户

```powershell
hostname                  # 例如 DESKTOP-XXXX
ipconfig | findstr IPv4   # 例如 10.76.x.x
whoami                    # 例如 desktop-xxxx\wzy
```

建议在路由器/交换机上给台式机做 **DHCP 静态绑定**，否则 IP 一变，SSH 配置就要改。

### 3.3 配置密钥登录

笔记本上生成一把专用密钥（不要复用 GitHub 那把）：

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\id_ed25519_desktop" -C "laptop->desktop"
Get-Content "$env:USERPROFILE\.ssh\id_ed25519_desktop.pub"
```

把公钥内容追加到台式机：

```powershell
# 普通账户
$pub = "ssh-ed25519 AAAA... laptop->desktop"
Add-Content "$env:USERPROFILE\.ssh\authorized_keys" $pub
```

**关键坑：管理员账户走的是另一个文件。** 若登录账户属于 `Administrators` 组，Windows OpenSSH 读的是
`C:\ProgramData\ssh\administrators_authorized_keys`，而且权限必须收紧，否则 sshd 直接忽略：

```powershell
# 管理员 PowerShell
$pub = "ssh-ed25519 AAAA... laptop->desktop"
Add-Content "C:\ProgramData\ssh\administrators_authorized_keys" $pub
icacls "C:\ProgramData\ssh\administrators_authorized_keys" /inheritance:r `
  /grant "Administrators:F" /grant "SYSTEM:F"
Restart-Service sshd
```

### 3.4 可选但建议

```powershell
# 默认 shell 用 PowerShell 而不是 cmd
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell `
  -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" `
  -PropertyType String -Force

# 密钥通了以后禁用密码登录（改 C:\ProgramData\ssh\sshd_config）
#   PasswordAuthentication no
Restart-Service sshd
```

### 3.5 可选：远程唤醒

台式机不常开时，配 BIOS + 网卡 Wake-on-LAN，笔记本侧发魔术包即可开机（需要台式机网卡在关机时保持供电）。不做也能用，只是要有人在现场开机。

---

## 4. 笔记本侧配置

`~/.ssh/config` 追加（保留现有 `Feng3090` 与 `github.com` 条目）：

```
Host desktop
    HostName 10.76.x.x
    User wzy
    Port 22
    IdentityFile ~/.ssh/id_ed25519_desktop
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 4
```

首次连接确认指纹，然后测试：

```powershell
ssh desktop "hostname; whoami; Get-Location"
```

能返回台式机主机名即成功。之后所有命令都写成一行：

```powershell
ssh desktop "cd L:\Code\bezier_opt_desktop; .\build\src\Release\bezier_opt.exe configs\archive\_eval_lsq_c1_36.json"
```

---

## 5. 数据面：把台式机 `L:\Code` 映射成笔记本的 `L:`

### 5.1 台式机开共享（管理员）

```powershell
New-SmbShare -Name Code -Path "L:\Code" -FullAccess "desktop-xxxx\wzy"
```

### 5.2 笔记本映射

```powershell
# 首次需要凭据；之后 persistent 会自动重连
cmdkey /add:10.76.x.x /user:desktop-xxxx\wzy /pass
net use L: \\10.76.x.x\Code /persistent:yes
dir L:\Code\bezier_opt_desktop
```

映射成功后，两端路径**完全一致**：

| 两端都成立 | 内容 |
|---|---|
| `L:\Code\bezier_opt_desktop` | 台式机上的仓库 |
| `L:\Code\_archive_bezier_paper_prep` | 外置归档（9 个 tar.gz） |

### 5.3 不想开 SMB 的两个备选

- **SSHFS-Win**（WinFsp + sshfs）：`sshfs desktop:L:/Code L:`，纯走 SSH，不用开 445 端口；
- **scp/robocopy**：`robocopy L:\Code\... \\10.76.x.x\Code\...` 或 `scp -r`，只在作业前后同步，不做常驻盘符。

---

## 6. 作业约定（把远程跑变成可复现）

**原则**：每次远程运行仍然登记到 `experiments/INDEX.md`，输出落到 `experiments/runs/<ID>/`，两端同路径。

### 6.1 三个包装脚本（建议放 `scripts/remote/`）

| 脚本 | 作用 |
|---|---|
| `push-inputs.ps1` | `robocopy` 把本机 `configs/`、`data/`、改过的脚本推到台式机仓库 |
| `invoke-remote.ps1 -Id <ID> -Config <json>` | `ssh desktop` 执行优化器/ANSYS，日志写到 `experiments/runs/<ID>/run.log` |
| `pull-results.ps1 -Id <ID>` | `robocopy` 把该 run 目录拉回本机 |

### 6.2 短任务（几分钟）

```powershell
ssh desktop "cd L:\Code\bezier_opt_desktop; .\build\src\Release\bezier_opt.exe experiments\_smoke.json; exit $LASTEXITCODE"
$LASTEXITCODE   # 本机拿到远端退出码
```

### 6.3 长任务（ANSYS 30–60 min，SSH 断开也不能死）

用任务计划程序托管，SSH 只负责"提交"和"查询"：

```powershell
# 提交
ssh desktop "schtasks /create /tn bezier_E20261020 /tr `"powershell -NoProfile -File L:\Code\bezier_opt_desktop\scripts\remote\run-job.ps1 -Id E20261020`" /sc once /st 00:00 /f; schtasks /run /tn bezier_E20261020"

# 查询（本机执行，返回 State / LastRunTime / LastTaskResult）
ssh desktop "powershell -Command `"Get-ScheduledTaskInfo -TaskName bezier_E20261020 | Format-List`""

# 看日志
ssh desktop "Get-Content L:\Code\bezier_opt_desktop\experiments\runs\E20261020\run.log -Tail 30"
```

断网、关笔记本都不影响：进程归任务计划程序，重连后照常查。

---

## 7. ANSYS 专项

- 批处理命令（按你的安装路径与版本调整）：

  ```powershell
  & "C:\Program Files\ANSYS Inc\v241\ansys\bin\winx64\ANSYS241.exe" -b -p ansys -i job.mac -o job.out
  ```

- **许可证是 node-locked 到台式机**：只在台式机上执行 MAPDL，不要把 `ansys.exe` 从笔记本远程调起来（会抢不到 license 或直接失败）。
- 现有入口：`python scripts/generate_proxy_model.py all-ansys`，在台式机仓库根目录执行即可。
- 产物：`data_proxy/ansys_csv/node_dump_*.csv`、`data_proxy/gravity_*.bin`。
- 拉回后按 AGENTS.md §5 校验：**每个重力 bin 12,288 B**、日志出现 `(3-plane, ...)`、`gravity_angles.json` 的 `format = w_du_dv_v2`。
- 大 CSV（单角度 ~325 KB × 21 ≈ 6.8 MB）走 SMB 映射盘，比反复 `scp` 快且不易中断。

---

> 2026-10-21 更新：笔记本 ↔ 台式机已通过 **Tailscale** 打通（即下方情形 C 的第三种做法）。后续按 §3–§6 配 SSH 与 SMB 即可。

## 8. 网络分支

| 情形 | 做法 |
|---|---|
| **A. 笔记本能路由到台式机**（像 10.76.0.64 那样） | 直接用 IP/主机名，按 §3–§4 配完即可 |
| **B. 台式机在另一个内网，但有跳板**（如 `Feng3090`） | `~/.ssh/config` 里加 `ProxyJump Feng3090`，一条命令穿透 |
| **C. 台式机在 NAT 后、无公网 IP** | 三选一：① 校园/公司 VPN；② 路由器端口转发 22 且改端口 + 仅密钥 + 限源 IP；③ **Tailscale**（WireGuard 覆盖网，第三方但只是网络层，不是远控）——最省事 |
| **D. 完全隔离** | 退回"人工拷贝 + 台式机上跑"，或申请固定公网映射 |

`ProxyJump` 写法：

```
Host desktop
    HostName 192.168.1.50      # 台式机在跳板内网的地址
    User wzy
    ProxyJump Feng3090
```

---

## 9. 安全清单

1. 密钥登录，禁用密码（`PasswordAuthentication no`）。
2. 防火墙 `-RemoteAddress` 只放行实验网段，不要 `Any`。
3. 暴露公网必须：改端口 + 仅密钥 + 限源 IP + 失败日志监控。
4. SMB 只给指定账户，共享目录里不要放许可证文件。
5. 定期看 `C:\ProgramData\ssh\logs\sshd.log`（失败登录会留下记录）。
6. 密钥文件权限：笔记本侧 `icacls` 只给本人读。

---

## 10. 验收清单

- [ ] `ssh desktop "hostname"` 返回台式机名
- [ ] `ssh desktop "Get-ChildItem L:\Code\bezier_opt_desktop | Select-Object -First 3"` 能看到仓库
- [ ] `net use L:` 后，本机 `dir L:\Code\bezier_opt_desktop` 与台式机一致
- [ ] 远程跑一次 1-iter 评估，本机在 `L:\Code\bezier_opt_desktop\experiments\runs\lsq_eval_c1_36\` 看到 `optimization_summary.csv` 更新
- [ ] ANSYS 冒烟：一条 `-b -i test.mac` 能出 `job.out`
- [ ] 长任务：提交 `schtasks` 后关掉笔记本 WiFi 再连，任务仍在跑（查 `LastTaskResult`）
- [ ] 拉回的重力 bin 通过 12,288 B 与 `(3-plane)` 校验

---

## 11. 需要你确认的四件事

1. **台式机的实际地址**：主机名或 IP，和笔记本是否在同一可达网段（能否 `Test-NetConnection <ip> -Port 22` 通）。
2. **Windows 版本与权限**：Pro 还是 Home（只影响 RDP，不影响 SSH），你有没有管理员权限。
3. **登录账户**：用户名，以及是否在 `Administrators` 组（决定用哪个 `authorized_keys` 文件）。
4. **是否愿意开 SMB**：愿意就映射 `L:`；不愿意就走 SSHFS 或 scp 同步。

---

## 12. 和现有仓库的衔接

配置完成后建议做三件事：

1. `AGENTS.md` 增加一节「远程执行」：台式机地址、作业 ID 约定、`ssh desktop` 常用命令、验收检查。
2. 新建 `scripts/remote/`：`push-inputs.ps1`、`run-job.ps1`（跑在台式机）、`pull-results.ps1`。
3. 每次远程作业在 `experiments/INDEX.md` 记一行，输出路径写 `experiments/runs/<ID>`（两端同名）。
