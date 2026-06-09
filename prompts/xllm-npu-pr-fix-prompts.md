# xLLM NPU PR 修复中文 Prompts

## 场景 1：修复 PR 引入的精度回归

```text
请使用 xllm-npu-accuracy-debug、xllm-npu-incident-triage 和目标 xLLM 仓库的 git-workflow，分析并修复 PR <pr_number_or_branch>。

问题：
- 症状：<乱码 | CEval 掉分 | 单 prompt 异常 | GPU/NPU 不一致>
- 目标分支：<target_branch>
- 疑似 PR/commit：<bad_commit_or_pr>
- 已知正常版本：<good_commit_or_branch>
- 评测集：<dataset_and_tasks>
- artifact root：<run_root>

流程：
1. 确认当前 worktree、branch、author、git status。
2. 先用最小 deterministic prompt 复现，不要直接跑最贵的全量评测。
3. 同时看日志和代码逻辑，确认是否有异常分支、shape、position、KV cache 或 graph 参数。
4. 如果引入点不清楚，用 git bisect 定位 commit。
5. 只实现根因对应的最小修复。
6. 按精度阶梯验证：单 prompt -> 5-10 条 -> 数据集子集 -> 指定 task 全量。
7. 更新 PR 描述：不改会报什么错、为什么错、改了什么、如何验证。
8. 将定位经验沉淀到 accuracy-debug 或 model-pr-optimization-history。
```

## 场景 2：修复 crash / PagedAttention / graph 报错

```text
请使用 xllm-npu-incident-triage 分析 <crash_log_path> 中的 xLLM NPU 报错并修复。

输入：
- 报错日志：<crash_log_path>
- 启动脚本：<server_script>
- 请求样例：<request_json_or_script>
- 正常参考分支：<good_branch>
- 当前分支：<bad_branch>

要求：
1. 从日志中提取第一处 fatal/check failed 和关键变量。
2. 找一个最小请求复现，不要依赖大规模评测才能触发。
3. 对比正常参考分支的相关代码路径。
4. 分析是否与 graph capture、PagedAttention setup、KV len、position、padding 或 stream 同步有关。
5. 修复后本地编译，并用启动脚本和最小请求验证。
6. 如果问题与性能路径相关，补一个 smoke 性能数据说明没有明显回退。
```

## 场景 3：回复 PR review 意见

```text
请分析 PR <pr_number> 的 review 意见并给出代码修改和回复建议。

步骤：
1. 拉取最新 PR 分支，确认 git status 无非预期修改。
2. 阅读评论对应的代码和上下文，不要只看评论文字。
3. 判断意见类型：正确性、性能、风格、测试、文档、兼容性。
4. 如果需要改代码，先修改并运行对应验证。
5. 回复时说明：已改什么、为什么这样改、验证结果是什么。
6. push 后确认 fork 分支和 PR head 指向预期 commit。
```

## 场景 4：rebase main 并解除冲突

```text
请使用 xLLM git-workflow，把 PR 分支 <pr_branch> rebase 到最新 main。

要求：
1. 先确认当前 worktree 是否就是该 PR 的权威 worktree。
2. fetch 最新 main 和 PR 分支。
3. rebase 前记录当前 HEAD、远端 PR head、git status。
4. 解除冲突时保留 PR 原始意图，并确认相关 VLM/NPU/MTP 改动没有丢失。
5. rebase 后运行必要编译/UT：<test_command>
6. force push 必须使用 --force-with-lease。
7. 总结冲突原因、保留的逻辑、验证结果和新 commit。
```

## 场景 5：提交前本地编译和 UT 门禁

```text
请在 <xllm_repo> 中执行提交前门禁。

门禁要求：
1. git status --short 必须无非预期修改。
2. git submodule update --init --recursive 已执行。
3. 确认没有其他 setup.py/cmake/make/ninja/git submodule 进程在写同一 build 目录。
4. 执行 python setup.py build test --device npu。
5. 保存 build log、UT log、commit、submodule status 和环境摘要。
6. 只有编译和 UT 都通过后才能提交或 push。
```

## 场景 6：PR 描述重写

```text
请根据当前 diff 为 PR <pr_number_or_branch> 重写精简但可读的 PR 描述。

描述必须回答：
1. 不改会发生什么错误或性能问题？
2. 根因是什么？
3. 这次具体改了哪些逻辑？
4. 为什么这样改能解决问题？
5. 如何验证：编译、UT、精度、性能、profiling。
6. 风险和回滚方式是什么？

不要写空泛描述；每个结论都要能对应到 diff、日志或验证 artifact。
```
