# D-State Hang During Mmap Weight Loading

Use this case when an xLLM, vLLM-Ascend, or PyTorch NPU process stops responding,
keeps NPU memory allocated, and cannot be explained by normal Python exceptions,
OOM, or HCCL timeout logs.

The general lesson is to triage process state and kernel logs before changing
framework code. A hang during host-to-device copy can be caused by driver /
firmware handling of pinned user pages, especially when CPU tensors are backed by
memory-mapped checkpoint files.

## Symptom

| Signal | Typical observation |
|---|---|
| Process | still exists but does not respond |
| `ps` state | `D` or other uninterruptible sleep state |
| NPU memory | remains allocated |
| Python stack | often not enough, because the process is blocked in kernel / driver code |
| Trigger | checkpoint load or CPU-to-NPU tensor copy |

One risky pattern is:

```python
with safe_open(path, framework="pt") as f:
    cpu_tensor = f.get_tensor(name)      # may be mmap-backed
    npu_tensor = torch.empty_like(cpu_tensor, device="npu:0")
    npu_tensor.copy_(cpu_tensor)         # host-to-device DMA copy
```

## Evidence Collection

Collect these before killing the process when possible:

```bash
PID=<hung_pid>

ps -p "$PID" -o pid,ppid,user,stat,wchan,args
cat /proc/"$PID"/stack
dmesg -T | tail -200
npu-smi info
npu-smi info -t memory
```

Important stack patterns:

| Pattern | Meaning |
|---|---|
| `filemap_fault` / `__folio_lock*` | process is faulting or locking file-backed pages |
| `pin_user_pages_fast` / `get_user_pages_fast` | driver is pinning user memory for DMA |
| Ascend `devmm_*` functions | blocked inside Ascend host memory / device memory path |

Important `dmesg` patterns:

| Pattern | Meaning |
|---|---|
| `Get_user_pages_fast fail` | driver could not pin expected CPU pages |
| `ret=-14` / `EFAULT` | bad or unavailable user virtual address mapping |
| `drv_devmm_host` / `ascend_kernel_open_adapt` | failure is in the Ascend driver path, not ordinary Python code |

## Root-Cause Class

This belongs to the "mmap-backed CPU tensor cannot be safely pinned by the NPU
driver in this environment" class.

Potential contributors:

- safetensors or checkpoint loader returns mmap-backed CPU tensors;
- pages are not faulted in before host-to-device DMA;
- driver / firmware versions mishandle a page state;
- driver and firmware are not a compatible pair;
- the issue is exposed only for large checkpoints or particular file-system /
  memory-pressure conditions.

## Mitigation Options

Choose the least invasive mitigation that matches the evidence:

| Mitigation | When to use | Tradeoff |
|---|---|---|
| materialize CPU tensor before NPU copy | reproducible hang happens at weight H2D copy | increases host memory and copy cost |
| use non-mmap checkpoint loading | loader supports it and memory budget allows | higher CPU memory peak |
| upgrade or reinstall driver / firmware as a matched pair | kernel logs point to driver page pinning and environment is old or inconsistent | requires maintenance window and reboot |
| isolate with minimal reproducer | before blaming xLLM scheduler or kernels | extra setup time, but prevents wrong patches |

Materialization pattern:

```python
if tensor.device.type == "cpu" and target_device.type != "cpu":
    tensor = tensor.contiguous().clone()
target.copy_(tensor)
```

For C++ / ATen paths, use the equivalent explicit CPU materialization before
copying into an NPU tensor. Keep the helper narrow and document the memory
tradeoff.

## Validation

After mitigation:

1. Re-run the minimal weight-copy reproducer.
2. Start the target service and confirm the model loads fully.
3. Check `dmesg` for new `get_user_pages_fast` or `devmm` errors.
4. Confirm NPU memory is released after normal shutdown.
5. Run a short inference smoke test.

Do not claim a framework performance win from this change. This is reliability
or environment compatibility work unless followed by separate benchmark evidence.

## Incident Report Fields

Record:

- process state and `wchan`;
- relevant `/proc/<pid>/stack` frames;
- relevant `dmesg` lines;
- driver, firmware, CANN, torch_npu versions;
- checkpoint loader mode;
- mitigation used;
- validation command and result.

