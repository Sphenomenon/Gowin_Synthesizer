# AE350 显式 ILM／DLM 冷启动变体

`stage_ae350_firmware.py --memory-profile ilm64k_dlm64k` 选择维护的
`start.S` 分支及 `boot_ilm_dlm.ld`，不会修改或安装任何工程 ROM。
默认 `pl16k_8k`、accepted 和 pinned 的选择策略保持原样。
这是 C06 的可验证源码检查点，尚不是整机接入或硬件接受。

## 冷启动与容量

当前参考平台从 FPGA 配置初始化的 `firmware/boot.mem` 启动：
`gw138k_boot_memory.sv` 为 4096×32-bit ROM，复位入口 `0x80000000`。
装载器、ILM 代码／常量初值、DLM 数据初值按 LMA 连续放入该 ROM，
ELF 的 VMA 则为实际运行地址。构建从 ELF 的 PT_LOAD 重新构造
`firmware.bin`，再核对完整 4096-word `boot.mem`；超 16 KiB 直接失败。
**64 KiB 是运行窗口，不是现有冷镜像容量。**
本变体不增加 Flash 驱动或镜像分区，不依赖 GDB／调试器预装载。
以后固件超过 16 KiB 时，需要显式扩展真实冷存储及装载互连，重做资源、
时序和部署验证；不能只放大链接器的 ROM 长度。

| 位置 | 范围／分配 |
|---|---|
| ROM | `0x80000000..0x80003fff`，装载器和全部初值 |
| ILM | `0xa0000000..0xa000ffff`；代码／常量；最后一字保留启动访问测试 |
| DLM 前缀 | `0xa0200000..0xa02000ff`；启动访问测试，不放业务全局 |
| DLM 数据 | 从 `0xa0200100` 开始；`.data`、`.bss`，必须在栈底之前结束 |
| 栈 | `0xa020c000..0xa020ffff`，16 KiB，向下增长 |
| 堆 | 0 字节，无隐式分配器；余下空闲空间不宣称已分配给解码任务 |

启动先禁用机器中断、把异常入口设为 ROM 中无栈处理程序，再检查
I／D Cache 均关闭、MICM／MDCM 存在局部存储且 LMSZ 为 64 KiB。
仅置位 MILMB.IEN／MDLMB.DEN，保留其余位并要求完整读回相等。
随后写入并读回两个 64 KiB 窗口的每一字，验证 DLM 字节通道和窗口末字，
复制／逐字比较 ILM 与 `.data`，显式清零并读回 `.bss`，填充栈标记，
设置 SP，执行 `fence iorw,iorw` 与 `fence.i`，再跳往 ILM。
ILM 中继续验证真实 `.data`／`.bss` 探针及一次 16-byte 栈访问，才报告
PASS 并进入原 `services_main`。所有失败停止在 ROM，不调用业务。

诊断沿用 `0xf8000000`：`+4` 为 PASS／FAIL，`+8` 为本变体失败阶段，
`+12/+16` 为异常 `mcause/mepc`。阶段 1=Cache 状态，2=容量，
3=使能读回，4=RAM 访问，5=ILM 复制，6=数据／清零，7=ILM 入口，
`0x80`=机器异常。未支持的 CSR 访问会通过机器异常失败。
该诊断值是本变体启动语义，不改其他配置的诊断或业务 MMIO 协议。

复位会重新装载、清零和初始化栈，不依赖此前 RAM 内容。
此前调试会话若仍开启 Cache，启动明确拒绝；不能把此路径当成通用
Cache-enabled warm restart。机器异常处理不恢复业务或重新播放命令。

## 资料和实际 IP 边界

官方文件均为仓库 `docs/ae350/manuals/` 中冻结的原 PDF：

- MUG1031-1.3.1，PDF 第 15 页／正文第 7 页：ILM、DLM 基址及各 64 KiB；
  第 51 页说明 fabric 可经 Extended AHB Master 访问局部存储。
- MUG1029-1.3，PDF 第 42 页／正文第 9 页：CPU 内存映射；
  第 47 页／正文第 14 页：`BUILD_BURN ae350_rpu_ilm_dlm.sag`，镜像在 ROM，
  代码运行 ILM、数据运行 DLM；第 301 页／正文第 268 页为 CPU 复制至
  局部存储的 slave-port 示例，公布 `MICM_CFG/MDCM_CFG=0x439ada` 和 64 KiB。
- MUG1029 第 50–52 页描述 Cache 开关和维护命令，未完整列出局部存储 CSR。

CSR 常量另从两个公开的 Gowin 作者 BSP 副本核对，**并非本轮直接向厂商
取得的 SDK**；二者一致不构成对实际硬核行为的独立证明：

| 副本 | 固定 commit／目录 |
|---|---|
| [muzhiyun/TangMega-138KPro-AE350](https://github.com/muzhiyun/TangMega-138KPro-AE350) | `019f87ff9c6f77ca467fd15b29694c753eaddbe2`，`firmware/ae350_demo/src/` |
| [Aniline47/GOWIN-138K-AE350](https://github.com/Aniline47/GOWIN-138K-AE350) | `a29323ceb72647bb37c59f1ddd51b4ab07062134`，`RISC-V_design/ae350_demo/src/` |

`bsp/ae350/csr.h`：MICM_CFG=`0xfc0`，MDCM_CFG=`0xfc1`，
MILMB=`0x7c0`，MDLMB=`0x7c1`，MCACHE_CTL=`0x7ca`。
两个文件 SHA256 同为
`a9692c329706895a512e06ff58be89c75c51e19982ae1b780f772fb4e9d02755`。
`core_v5.h` 定义 IEN／DEN 为 bit 0；demo 的容量判定为
`(cfg>>12)&7` 存在、`1<<(9+((cfg>>15)&31))` 字节。
第一副本 `demo/idlm/demo_idlm.c` SHA256
`96e298d71e6cf91cd6dca5c0f665a416b8bd2d15ae34fb2319c71ac9bffc86e0`；
第二副本 `demo/slaveport/demo_slaveport.c` SHA256
`5282639d50294199bf8f83dcdf56037204e6d4b7e6a672cf1f2b95fa2f42b90e`。
这里只记录事实和来源，未复制这些 vendor 实现到活动固件。

构建元数据绑定 `resource_rework_route0` 参考平台的两份 config、wrapper
及 boot-memory 哈希。参考配置只开启 EXT_I、EXT_D、EXT_APB_SLAVE、SMU；
`AE350_EXT_AHB_MASTER_EN` 未开启。CPU 内部访问与 fabric 装载端口不同，
本方案采用 CPU 经内存映射自装载，不要求 fabric 装载端口。
调用者仍须核对**实际 staged** 配置、ROM 容量及互连；参考哈希不能证明
另一个候选已经装入本固件。加密 IP 的 CSR 可读写、CPU 写 ILM、指令取回、
真实复位入口仍须硬件探针和同一候选验收，本次没有操作板卡。

## Cache、共享数据和资源

本变体要求冷入口 I／D Cache 关闭，保留关闭状态；新增 ISA 要求
`rv32im_zicsr_zifencei`，不默认为实际硬核已验证支持该指令。
ILM 装载后有指令屏障；APB／已有共享队列没有改地址、所有权或 Cache 属性。
没有新增 DMA，不能据此宣称 Cache clean／invalidate 或 DMA 一致性已实现。
今后开启 Cache 或引入缓存共享 DDR 时，必须在各所属接口实现并验证维护契约。
RAM 循环读回也不能作为 ECC 使能、异常配置或纠错覆盖证明。

默认 profile 保留原 PL ROM／RAM；下述显式变体替换 ROM 存储但保留 RAM 行为，
没有新的综合、物理 CLS／BSRAM 净收益或 CPU 周期结论。C04/C07 应按整合后的同功能
候选另测。64 KiB 空间、编译代码占用和 CPU 使用率是不同指标。

## 显式 64 KiB 冷存储装配

`custom138k-workstation-r00-no-local-panel-ilm64k-boot64k-v1` 继承无本地
LCD／触摸、无 CNN、保留录音及 BLE raw DDR 的运行组合，显式选择
`ilm64k_dlm64k` 与 `ae350_boot_rom_bytes=65536`。它不替代现有 profile。
`rtl/memory/workstation_ae350_boot_memory.sv` 替换冻结工程中编译的
`src/ae350/gw138k_boot_memory.sv`，保留原模块 ABI 和 8 KiB scratch RAM
的延迟、写掩码、pending-write bypass 与复位行为。ROM 地址窗口是
`0x80000000..0x8000FFFF`，窗口外仍返回 EBREAK；镜像必须恰为 16384 个
32 位文本字。新增 48 KiB 是原始 ROM 存储差额，不是物理 BSRAM 颗数结论。

装配校验绑定生成镜像容量、实际编译的唯一 ROM owner、两份硬核配置和 wrapper
的冻结哈希。地址端口原本就是 32 位，因此不改 vendor 端口或时钟。
链接器与 ELF 校验同时使用选定的物理容量；ILM 代码／常量与 DLM 数据／栈
仍各自受 64 KiB 上限约束，不能由更大的冷存储绕过。

`sim/test_ae350_boot_storage.py` 比较新模块的 16 KiB 参数与原冻结实现，
覆盖全部 4096 ROM 字及 4000 个 RAM 事务；64 KiB 参数覆盖全部 16384 字和
窗口边界。它还真实编译含额外 32 KiB 常量的固件：旧 16 KiB 物理容量必须
链接失败，新容量必须通过 ELF／BIN／ROM 重建并实际执行复制至 ILM。
再次增加 32 KiB 常量须因运行窗口／镜像越界而失败。缓存和硬件验收状态不变。

## 离线验证

```sh
python3 projects/138k/push2_workstation/usb_a/tools/stage_ae350_firmware.py \
  --memory-profile ilm64k_dlm64k --recording-api --output <新目录>
python3 projects/138k/push2_workstation/usb_a/sim/test_ae350_local_memory.py
python3 projects/138k/push2_workstation/usb_a/sim/test_stage_ae350_firmware.py
```

新回归以 ELF／二进制／ROM 的实际指令驱动严格 RV32 启动解释器，未知指令
直接报错。覆盖容量／Cache／CSR／使能读回、ROM 读取／RAM 写入异常、复制末字
损坏、迟到 `.bss` 污染、复位、指令屏障、ILM 跳转目标及栈访问边界。
解释器的总线／CSR 是公开约定的模型，不能替代真实硬核的对应测量。

栈报告由 GCC `.ci` 调用图和 `.su` 静态帧相加，根为当前真实
`services_main`；内联／尾调用按编译器图保守计入，递归、动态帧、未解析调用、
可达机器间接调用和容量不足均拒绝。ROM 装载器无栈，ILM 自检使用 16 字节后
恢复 SP，中断关闭。未从该入口调用的导出 API 单列，不能把它们的未来调用者
当成已审计；接入新服务、回调或中断后必须重算完整链。
硬件栈水位、任务周期、最长服务间隔、吞吐和 ECC／Cache 验收仍未完成。

## 显式回调闭包审计

`call_chain_report(..., reviewed_indirect_calls=review, input_sha256=identities)`
接受单独审阅的 points-to 闭包。默认没有此参数，任何可达未知间接调用仍失败。
review 必须精确包含 `schema=1`、完整实际编译输入的 `input_sha256`、整份真实
反汇编的 `disassembly_sha256`、人工源码闭包说明 `source_target_review` 和 `sites`。
每条 site 指明 `caller`、八位十六进制 `address`（带 `0x`）、32 位
`instruction` 和完整 `targets` 集合。它是源码目标集合的显式审阅记录，
不是对任意 C 函数指针的自动别名分析。

helper 将每个已审间接调用的全部目标加入 GCC 图，并计算所有可能分支的最大栈。
目标必须具有唯一 GCC 节点、实际机器函数体和静态帧；递归、未知或动态帧、
缺失／重复／不可达 site、caller／地址／指令变化、源码或反汇编漂移均拒绝。
已审 site 只替换相应 caller 的 GCC `__indirect_call` 占位边，不能豁免该 caller
中的新增机器间接指令。内部 jump table 没有回调占位边，不能套用本接口绕过；
其目标表需要另行证明，或在显式编译策略中使用 `-fno-jump-tables`。

`sim/test_ae350_callback_stack.py` 用真实 GCC 生成两个独立的 JALR，验证默认拒绝、
全部目标纳入 128 字节栈界、缺 site、完整输入／机器漂移、递归及目标帧负例。
接入业务 owner 时必须为该份实际固件重新审阅并绑定 review，不能沿用旧源码的记录。
