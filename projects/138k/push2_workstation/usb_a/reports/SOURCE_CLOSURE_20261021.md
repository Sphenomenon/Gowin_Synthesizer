# 生产准备输入闭包验证

日期：2026-10-21。基础提交：`a97505c`，本轮实现尚未提交。范围是完整工作站 prepare 的可复现性与来源绑定，不是新的位流验收。

## 实施内容

- 新增 [`baselines/`](../baselines/README.md)：accepted full83、timing85、resource rework route0 三类锁定来源；原始输入清单保持原字节。
- 复用 Git 已跟踪的旧冻结 `Prj1` 和 vendor，缺少的内容按 SHA256 去重保存，共 266 个对象，约 3.3 MB；没有导入三套完整生成工程。
- 每个原始清单只排除 178 项 `docs/` 历史资料／捕获与 2 项 AE350 固件中间产物；排除原因显式记录，不改历史清单。
- 构建器改由通用解析器校验并生成新暂存，缺失／漂移即失败，不读私有历史目录，也不把“寻找最新目录”当恢复策略。
- 保留 accepted CNN、六项 timing85 和显式活动资源候选之间的边界；DDR 冻结常量移至公共来源模块，整机入口不再导入编号实验构建器取得常量。
- 输出元数据新增 `source_baselines`，记录实际来源描述清单及其哈希。活动 overlay 和最终 `workstation_inputs.json` 继续独立记录。

## 干净克隆发现的换行问题

第一次干净克隆验证暴露出旧冻结树的 27 个文件存在 Git LF 存储与历史原始 CRLF／混合换行的差异，其中 16 个是混合换行。它们在原工作区原样可用，但重新 checkout 后原始 SHA256 不同。

没有重写 vendor 文件或降低原始哈希门禁。清单显式绑定 Git-LF 表示的哈希，并记录 CRLF 或逐行还原规则；生成后再次核对历史原始 SHA256。另有四份无末尾换行输入使用带双重哈希的 base64 表示，避免补丁／Git 文本流程意外增加换行。新增测试覆盖 LF、CRLF、混合换行、末尾无换行和内容篡改拒绝。

## 验证结果

在迁移前先分别准备三个工程，保存逐文件哈希；迁移后在原工作区重新准备，并与迁移前剔除明确非生产项后的清单比较：

| prepare 配置 | 保留输入数 | 字节变化／新增 | 明确排除的非生产项 |
|---|---:|---:|---:|
| `--current-workstation` | 422 | 0／0 | 180 |
| `--current-workstation --cnn-timing85` | 422 | 0／0 | 180 |
| `--resource-rework --resource-timing` | 437 | 0／0 | 180 |

临时本地克隆中没有 full83、full85 或资源优化私有历史暂存。覆盖本轮源码改动后，三个 prepare 均通过，与原工作区各配置的全部生成输入逐字节一致。克隆中故意篡改一个锁定对象时，整机入口返回 2，且没有新建构建输出。

其余检查：

- 38 项单元测试通过：accepted 输入边界 10、USB 固件准备 6、基线重建 22；另有 1 项可选干净克隆集成测试通过。
- 干净克隆的诊断 CDC 仿真通过：1338 个时钟检查，覆盖全部 128 种 level pattern、异相采样、原 UART 位布局和复位。
- 干净克隆的生命周期 scoreboard 通过：36395 个接受事件、36235 个执行事件、160 个取消事件、404 次直达生命周期检查，包含三路来源、停顿和轮换。
- 额外 `--resource-rework --prepare-only` smoke 通过，生成 437 个输入；此项未另做迁移前的逐文件对照，不扩大前三条的等价性结论。
- 原始三份暂存输入清单未修改；T24 候选、工作站部署索引与 full83 验收记录没有改动。

机器可读结果、来源清单哈希与本轮实现文件哈希见 [`source_closure_20261021/verification.json`](source_closure_20261021/verification.json)。原始日志与迁移前／后临时工程留在本地 `usb_a/results/source_closure_20261021_002644/` 及各 prepare 输出，不作为新的生产输入。

## 复核命令与边界

```sh
python3 projects/138k/push2_workstation/usb_a/tools/workstation_baselines.py
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
python3 projects/138k/push2_workstation/usb_a/sim/test_stage_usb_firmware.py
GW138K_VERIFY_CLEAN_PREPARE=1 python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_baselines.py
```

集成验证需要 Git、Icarus Verilog 和原有 bare-metal RISC-V 工具链，不需要访问实体板卡。

本轮未重新运行综合／P&R、未生成新位流、未操作串口／调试器、未下载 SRAM、未写 Flash、未新增实体验收。结果只证明来源闭包和 prepare 输入保持，不证明工具版本变化后的位流相同，也不把 T24 离线候选升级为已部署。

统一构建配置、消除字符串业务补丁、门禁失败语义和公共控制状态归位仍待后续阶段；旧编号实验入口及早期默认构建路径也没有全部迁移或删除。
