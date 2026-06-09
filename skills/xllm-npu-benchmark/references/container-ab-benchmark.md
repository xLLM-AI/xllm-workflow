# 容器隔离框架 A/B Benchmark

当 xLLM 与 vLLM-Ascend / SGLang NPU 需要不同依赖环境时，不要在一个框架容器内直接安装或启动另一个框架。正式 A/B benchmark 应回到宿主机作为调度层。

```text
宿主机
  ├─ 记录 manifest、npu-smi、容器镜像、artifact root
  ├─ docker exec <xllm_container> ...        # 启动/停止 xLLM 服务
  └─ docker exec <baseline_container> ...    # 启动/停止 baseline 服务
```

## 容器策略

- 正式性能对比：使用 `docker run -dit --name ...` 创建可复查容器，确认日志和 artifacts 收齐后再清理。
- 快速 smoke：可以使用 `docker run --rm`，但必须把日志、evalscope 输出、metrics 和 manifest 全部挂载到宿主机目录。
- 不建议每次 benchmark 前重新 `docker build`，应固定镜像 tag 或 digest。
- 如果 evalscope 版本可能不同，优先在宿主机或第三个 client 容器中统一运行 evalscope；服务容器只负责 serving。

## 公平性要求

- 两个容器挂载同一份模型权重和同一宿主机 artifact 根目录。
- 宿主机统一采集 `npu-smi info`、进程表、CPU/memory/load 快照。
- 两边使用同一物理 NPU 型号、卡数、可见卡顺序、TP、tokenizer、dtype、采样参数、warmup、请求数、并发和 workload。
- 每个框架 run 前后独立启动/停止服务，确认目标卡没有其他残留 context。

## 典型目录

```text
<run_root>/
  env/
  containers/
    xllm.inspect.json
    baseline.inspect.json
  xllm/
    service/
    perf/
  baseline/
    service/
    perf/
  comparison/
```

## 报告必填

- 容器名。
- 镜像 tag/digest。
- 框架 commit 或 package 版本。
- 启动命令。
- 端口。
- 设备映射。
- evalscope 命令。
- 宿主机 artifact root。
