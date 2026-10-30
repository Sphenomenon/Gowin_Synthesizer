# C06：显式 ILM／DLM 冷启动源码检查点

维护固件入口新增 `--memory-profile ilm64k_dlm64k`：从实际 16 KiB PL ROM 自装载，代码／常量运行于 `0xa0000000` 的 64 KiB ILM，数据／BSS／16 KiB 栈位于 `0xa0200000` 的 64 KiB DLM。没有使用 GDB 预装载，没有放大旧 ROM 的容量检查。启动异常入口保留于 ROM，先查容量和 Cache 状态，再使能／读回、访问两窗、复制／核对、清 BSS、初始化栈、执行 fence.i 后进入 ILM 自检与服务入口；错误停在 ROM 并报告阶段。

本阶段只增加明确的固件变体，四个既有整机 profile 仍选原 `pl16k_8k`。四份来源锁更新 start／provenance／stage helper，并补锁新增构建依赖，没有修改冻结基线、vendor、时钟或 DDR 分配。首批实现精确导入 `2791428c2f6d84b1085534d8fe53119511e9cca9` 的九份 blob，再在当前 C02 行绘制源码上独立构建与验证。详见 [LOCAL_MEMORY.md](../firmware/ae350/LOCAL_MEMORY.md) 的地址、CSR 资料、冷启动和失败契约。

## 父级验证

- 实际 RV32 镜像驱动的启动／故障回归 12 项通过。包含局部存储容量、Cache 已开、CSR 不支持、使能读回失败、总线异常、复制末字破坏、BSS 污染、缺指令屏障、非法跳转和栈越界；未知指令直接拒绝。该解释器是公开内存约定模型，不是加密硬核的硬件仿真。
- 当前 renderer＋recording API 的真实 GCC 镜像：冷镜像 15,040 bytes，ILM 占 14,432 bytes；DLM 初值 16／BSS 64 bytes，栈保留 16 KiB，堆为零。实际指令执行 205,245 步到 `services_main`，启动自检 PASS。
- ELF SHA256 `19296528bf2443850ba5ca11a854690c5ba06a9a1c8fe9fc095fce7b3968c9e9`；binary `704073135799abdd7ce356443f9d839d4332b87f6ec9a84ec2494a4a7b185d10`；ROM `705fd4ddd41eaaa0652ef9b6fd01380d7f9dcd96c314dcc91286724335561eb1`。ELF 的 PT_LOAD 物理地址可重建 binary，VMA／ROM 字节及链接边界一致。
- 当前可达 `services_main` 调用图加静态帧保守上界 544 bytes；未知调用、动态帧、递归及遗漏机器调用边拒绝。导出但尚不可达的服务 API 单列，接入它们后须重算；没有板上栈水位或任务周期接受。
- AE350 固件 10 项、USB 固件 7 项、accepted source 17 项、profile source 6 项、runtime source 12 项通过，四个 profile 来源全部加载通过。最初 profile 命令误写测试类名，未运行有效测试；失败日志保留，随后使用真实 `ProfileSources` 执行通过。
- `GW138K_VERIFY_CLEAN_PREPARE=1` 的 baseline 23 项全部通过，包含无私有 staging 的三条完整 prepare 对照、trace CDC／lifecycle 和坏来源拒绝。
- 实际默认 no-panel prepare `custom138k-workstation-r00-no-local-panel-v1-1aadab2e4380af85`：599 staged／269 enabled，runtime audit 266 编译单元／298 modules／2 packages。默认 ROM 与 C02 的 `1b2e8fac…` 完全相同，没有悄然在该候选切入 ILM。

## 未完成项与回退

I／D Cache 保持关闭；已有 Cache 开启前态明确失败，不声明 Cache 维护、DMA 一致性或 ECC 已完成。官方手册与公开 BSP 镜像的出处分列于 LOCAL_MEMORY，真实 CSR、CPU 写 ILM／取指、复位行为仍须同候选硬件探针。运行窗口 64 KiB 不等于冷存储已扩容；后续显式 BSRAM boot64 装配将同时绑定真实 ROM 模块、容量／地址窗、固件和输入清单，并重新测资源与物理时序。

机器记录：[ae350_local_memory_parent.json](workstation_task_20261030/ae350_local_memory_parent.json)。父级包 `/Users/sphenicidition/.cache/gw138k-task-20261030/c06-main-parent-v1` 含 13 份源快照、105 项外部证据，`verify.py` 只读复核；seal SHA256 `869ccef542ee6d23da9edbcabcb5772840d745d3f977bf1c6a942546c5204279`，receipt `011adc101d3a37cfb83b19db33563d291679846b592e5927ea4b280ba2d9896f`。

没有新综合、P&R、板卡操作、SRAM 或 Flash，也没有 CLS／BSRAM 净收益结论。需回退时从 `92bf6c4` 恢复三个默认构建／启动输入及四份依赖锁，以新身份重建；固定旧候选和本阶段证据保留。
