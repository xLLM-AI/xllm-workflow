---
name: ssh-remote-exec
description: SSH 远程执行能力。通过 SSH 连接远程 NPU 服务器，支持 ProxyJump 跳板机、SSH_ASKPASS 密码认证、docker exec 容器内执行、后台任务与日志轮询。所有需要远程执行命令的 skill 应引用本 skill。
---

# SSH 远程执行

在 Windows 环境下通过 SSH 连接远程 NPU 服务器，支持跳板机、密码认证和容器内命令执行。

## 前提条件

- 本地已安装 OpenSSH（Windows 自带 `C:\Windows\System32\OpenSSH\ssh.exe`）
- `~/.ssh/config` 中已配置目标主机（含 ProxyJump 跳板机）
- 用户提供 SSH 密码（用于 SSH_ASKPASS 认证）或已配置 SSH key

## SSH 配置

`~/.ssh/config` 中的典型配置：

```
Host ea-notebook
    HostName localhost
    User ext.xxx
    ProxyCommand C:\Users\xxx\software\wsCli -a lfga-cluster.easyalgo.jd.com -t <token>

Host 103
    HostName 11.87.191.103
    User weinan5
    ProxyJump ea-notebook
```

## 连接方式

### Step 1: 创建 SSH_ASKPASS 脚本

Windows 下 SSH 不支持交互式密码输入，需要通过 `SSH_ASKPASS` 环境变量指定一个脚本自动提供密码：

```powershell
Set-Content -Path "C:\Users\ext.gaopengju1\AppData\Local\Temp\opencode\askpass.bat" -Value "@echo off`necho <password>"
```

**注意**：密码不要硬编码到 skill 或脚本中，仅在运行时从用户 prompt 获取并写入临时文件。

### Step 2: 设置环境变量

每次执行 SSH 命令前，必须设置以下三个环境变量：

```powershell
$env:SSH_ASKPASS = "C:\Users\ext.gaopengju1\AppData\Local\Temp\opencode\askpass.bat"
$env:SSH_ASKPASS_REQUIRE = "force"
$env:DISPLAY = "dummy:0"
```

- `SSH_ASKPASS`：指向 askpass 脚本路径
- `SSH_ASKPASS_REQUIRE = "force"`：强制使用 SSH_ASKPASS（即使没有 TTY）
- `DISPLAY`：必须设置非空值，否则 SSH_ASKPASS 不生效

如果 SSH key 认证可用（`ssh -o BatchMode=yes <host> echo ok` 成功），则无需设置 SSH_ASKPASS。

### Step 3: 执行 SSH 命令

```powershell
ssh -o StrictHostKeyChecking=no <host_alias> "<command>"
```

### Step 4: 文件传输（SCP）

```powershell
scp -o StrictHostKeyChecking=no <local_file> <host_alias>:<remote_path>
```

## 引号规范

SSH 层必须使用双引号包裹，内部 `bash -c` 使用单引号：

```bash
ssh <host> "docker exec -u root <container> bash -c '<command>'"
```

**禁止**使用单引号包裹 SSH 命令：

```bash
# 错误：单引号会导致变量展开和转义异常
ssh <host> 'docker exec -u root <container> bash -c "<command>"'
```

嵌套引号超过两层时，改用 heredoc 或将命令写入临时脚本再执行。

## 远程容器执行

当目标服务运行在 Docker 容器中时，通过 `ssh` + `docker exec` 组合执行：

```bash
# 在容器内执行命令
ssh <host> "docker exec -u root <container> bash -c '<command>'"

# 在容器内后台执行（-d 参数）
ssh <host> "docker exec -u root -d <container> bash -c '<command>'"
```

**注意**：`docker exec` 的 `-e` 环境变量在 SSH 层不会自动展开，需显式传值。远程命令中的路径必须使用绝对路径，避免 `~` 或相对路径在不同 shell 下行为不一致。

## 容器管理

```bash
# 查看容器状态
ssh <host> "docker ps -a --format '{{.Names}} {{.Status}}' | grep -i <keyword>"

# 启动容器
ssh <host> "docker start <container_name>"

# 重启容器（用于释放 NPU 显存）
ssh <host> "docker restart <container_name>"
```

## NPU 状态检查

```bash
# 查看 NPU 设备状态
ssh <host> "docker exec -u root <container> npu-smi info"

# 检查空闲卡（解析进程列表）
ssh <host> "docker exec -u root <container> bash -c 'npu-smi info 2>/dev/null | tail -30'"
```

## 后台执行与日志轮询

对于长时间运行的任务（如批量评测），使用后台执行 + 日志轮询模式：

```bash
# 后台启动
ssh <host> "nohup bash /path/to/script.sh > /path/to/script.log 2>&1 &"

# 轮询日志
ssh <host> "tail -30 /path/to/script.log"

# 检查进程是否存活
ssh <host> "ps aux | grep script.sh | grep -v grep"
```

## 故障处理

| 问题 | 原因 | 解决 |
|---|---|---|
| `Permission denied` | SSH key 认证失败且 SSH_ASKPASS 未设置 | 确认 SSH_ASKPASS 三个环境变量已设置 |
| 命令超时 | 远程命令执行时间过长 | 使用 `nohup ... &` 后台执行，轮询日志 |
| `Container is not running` | 容器未启动 | 先 `docker start <container>` |
| NPU 显存未释放 | 前次进程崩溃未清理 | `docker restart <container>` 重启容器 |
| `bash: syntax error` | 嵌套引号解析错误 | 减少嵌套层数，或写入临时脚本再执行 |
