# C02：有界行绘制原语

本阶段把维护 AE350 renderer 的全页／补丁绘制拆成物理行范围接口，为随后逐步服务调度提供基础。`ui_render_rows`／`ui_patch_rows` 仅写指定的 1080 行页面范围，每行 960 个 32-bit 字；空范围不写，超出范围截断，先减后加避免 `UINT_MAX` 溢出。旧全页接口仍调用同一实现。

一次绘制任务须固定 model／touch，独占 back page，最后一片之后 fence，再等待真实发布 ACK 才交换页面。当前 `ui_main` 仍调用完整绘制，本阶段不宣称主循环已实现有界调度，也没有 CPU 周期或实时期限实测。

## 验证

- 固定历史 `94fd199757e1da92367c6ac15555993d0e1d4ff5` renderer（SHA256 `5188d9777768e6ec6951982f3d2776fb49d20a8d0384aa31b0d742c1653c4c91`）对照：12 个 model、15 种边界范围，每次 78 次完整页面比较；native 与 ASan／UBSan 均通过，独立复验通过。
- 维护固件 10 项、profile source lock 8 项、真实 runtime source 12 项、accepted boundary 17 项通过；revision 5 profile 21 项中 20 项通过，1 项历史 unprofiled prepare 按原规则跳过。
- 真实 GCC recording API 固件 14,520 bytes，保持 16 KiB 冷 ROM 上限；BSS 60 bytes，现有 PL RAM 可用栈容量 7,620 bytes。未证明整条调用链上界或板上栈水位。
- xPack 实际 no-local-panel prepare：`custom138k-workstation-r00-no-local-panel-v1-fefd8b6a628de64c`，599 staged／269 enabled；固件 14,408 bytes，ROM SHA256 `1b2e8fac6677508c6f070baa6a4486b372ce79d0a40b9b81a1a8546c47f90766`。另以 base prepare `custom138k-workstation-v1-e178208c35f07859` 验证 revision 5 门禁。

最初 renderer 内联导致的 ROM 超限、Homebrew USB 缺少 vendor `string.h` 的 prepare 失败以及误用 no-panel 输入运行 base profile 检查的失败均保留在 cache。通过共享 `noinline` rect／text 控制代码体积，完整 prepare 使用已验证 xPack 工具链；没有放宽容量或更改 vendor。

四份 profile 仅更新 renderer／header 的来源哈希，没有更改 source policy、时钟或冻结输入。16／8 KiB 仅为旧 profile 的兼容容量，C06 的 ILM／DLM 及后续 BSRAM 扩容另行实施。

## 来源与交付状态

机器记录：[ae350_ui_rows_parent.json](workstation_task_20261030/ae350_ui_rows_parent.json)。父级 cache：`/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-ui-row-parent-v1`，含 9 份源快照及 52 项外部证据绑定；`verify.py` 可只读复核。receipt SHA256 `ef5b72929cc1c522412ac25d3efd64221580e28e8099813e83fa94899bfc6b5d`，seal SHA256 `bcf3402306feb2141ee96a1b0faa7b1bb20d49f49c3414ac70dd3d7241a75226`。

没有新综合、P&R、板卡操作、SRAM 或 Flash。固定 `222fb761`／C2103102 不含本次修改，其证据不转移。下一阶段接入真实逐步调度及发布 ACK 生命周期；回退可从 `d44b5fe` 恢复 renderer／header 和四份 owning hash，以新身份构建。
