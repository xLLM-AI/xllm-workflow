# SSH 远程执行约束

通过 SSH 远程调度容器时，必须遵守以下规范，避免命令解析错误导致误判。

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

## 密码认证方式

- 优先使用 SSH key 认证，不要在 prompt 或脚本中写密码。
- 若必须使用密码认证，通过 `sshpass` 或环境变量传入，不要硬编码。

## 常见陷阱

- 嵌套引号超过两层时，改用 heredoc 或将命令写入临时脚本再执行。
- `docker exec` 的 `-e` 环境变量在 SSH 层不会自动展开，需显式传值。
- 远程命令中的路径必须使用绝对路径，避免 `~` 或相对路径在不同 shell 下行为不一致。
