# AE350 工作站固件维护入口

这里维护 AE350 的 UI／服务固件，USB Host 的 VexRiscv 固件仍由 `stage_usb_firmware.py` 单独编译。实时合成、效果、分析与绘图不迁入此目录；这里保留现有 AE350 的辅助页面和请求语义，后续业务迁移另立任务。

`provenance.json` 记录从 `resource_rework_route0` 锁定基线导出的九项 C／头文件／启动汇编／链接脚本及其原始 SHA256。原始 `ui_main.c` 和 `ui_model.h` 实际来自基线对象，不能直接使用早期 `results/.../firmware` 中同名文件替代。旧 `projects/138k/ae350/scripts/build_workstation.py` 引用缺失的历史目录和 Linux 编译器绝对路径，不作为这里的构建依赖。冻结基线、原始清单和旧 ROM 保留原字节。

首次导入后，`ui_render.c` 中两个已停止调用的旧键盘绘制 helper 改为 `static inline`，使其在当前 GCC 的 `-Werror=unused-function` 下可编译；原有调用路径和界面行为不变。每次构建报告 `changed_from_import`，之后的维护修改直接落在本目录，不改基线对象。

从仓库根目录执行，输出目录必须不存在：

```sh
python3 projects/138k/push2_workstation/usb_a/tools/stage_ae350_firmware.py \
  --output /tmp/ae350-new-candidate \
  --riscv-prefix /opt/homebrew/bin/riscv64-elf
python3 projects/138k/push2_workstation/usb_a/sim/test_stage_ae350_firmware.py
```

GNU bare-metal RISC-V 工具前缀也可由 `GW138K_RISCV_PREFIX` 或通用工具发现机制提供，需要 `gcc`、`objcopy`、`size`、`nm`。目标 ISA 为 `rv32im_zicsr`，ABI 为 `ilp32`，保持原固件的 `-O2`、freestanding 和不使用 small-data 假设。原四份编译输入 `start.S`、`ui_main.c`、`ui_render.c`、`ui_runtime.c` 保留，并链接 first-party 的 `audio_clock_service.c`。原九项导入描述保留在 `provenance.json.files`；新增 C／头文件单列于 `first_party_files`，注明仓库路径、维护来源和当前 SHA256，编译前核对。维护这些文件时须同步其 first-party 描述；构建元数据分别记录 imported／first-party 输入哈希。头文件和 `boot.ld` 全部复制进独立输出，编译前后检查身份。

输出包含 ELF、原始 binary、4096 个小端 32-bit 字的 `boot.mem`、linker map、section size、符号表、编译日志、逐函数 `.su` 栈报告及 `build_metadata.json`。元数据登记工具版本、命令、所有维护输入 SHA256、ELF／binary／ROM SHA256，以及与锁定历史 ROM 的逐字比较。不同工具链或维护源码生成的 ROM 可以不同；只有真实字节相同才报告复现，不复用历史验收身份。

ROM 位于 `0x80000000`，容量 16 KiB；物理工作 RAM 为 8 KiB，前 512 bytes 留给启动诊断，globals 从 `0x200` 开始，栈顶 `0x2000`。链接与独立符号检查都要求 globals 不越过 `0x1000`，至少保留 4 KiB 栈；报告包含对齐／空洞在内的静态 RAM 占用和实际剩余容量。编译器逐函数栈值只用于检查单帧容量，不等于完整调用链上界或实板水位，后两项仍需 C04 验证。

调用接口为 `stage_ae350_firmware(root, output, riscv_prefix=None, *, reference_mem=None)`，其中 `root` 为 `usb_a`。函数仅生成候选固件和证据，不修改任何准备工程，也不操作板卡；显式选择此入口的配置须把新 `boot.mem` 安装到自己的 `stage/firmware/boot.mem` 并纳入整机 manifest。accepted／pinned／resource 的原锁定来源不会因为新增维护入口自动改变。`--reference-mem` 仅更换比较对象，不能借此变更输入来源或硬件验收结论。

## 有限时钟请求 C API

`audio_clock_service.h/.c` 为原生 runtime 的 `0xf8030000` 时钟 APB 页提供独立调用入口。创建 `a138_clock_mmio_bus(A138_CLOCK_BASE)` 只返回适配器；当前四份启动／UI 源码没有调用它，没有新增启动请求或自动切率。未来页面可复用此接口：由一个 owner 串行处理显式请求，调用一次 `a138_clock_submit` 保存 ticket，再在每轮服务中调用一次 `a138_clock_poll`。probe／submit／poll 最多完成 2／9／11 次总线访问，均无重试或等待音频的循环。

probe 要求 ID `0x434c4b01`、ABI major 1、能力 bits0/1/2 和 media-policy bit4。COMMAND 0／1／2 分别请求 48k／44.1k／恢复；具体 admission、先封录音并停止 TF、同率 no-op 和实际切换由 PL owner 决定。API 记录硬件的 expected epoch／rate；提交失败不修改调用者 ticket。checked transport 回调可返回 I/O／APB 错误；错误发生在写入之后时命令可能已接受，调用者须观察状态并按自己的错误策略处理，不能盲目重发。

poll 对 command_id／result_id 作前后检查，读取 ACTUAL `+0x2c` 后才读取该次访问捕获的 snapshot_epoch `+0x30`。ID 变化或 I/O 错误不会发布混合 status。只有匹配的完成结果、idle phase、有效且不忙、无 fault 的实际 rate／epoch 才返回 APPLIED；结果成功但实际上下文已变返回 CONTEXT_LOST。status 带回 command_id／result_id，结果字段须结合返回状态和匹配 ID 使用。CPU observer reset 后必须丢弃 ticket；32-bit ID 重用和 wrap 不能充当持久 session fence。

media-policy ABI 保留 `+0x60` bits0 hold／1 pending／2 completed／3 failed／4 enabled／5 backend_ready，`+0x64` timeout 和 `+0x68` failure reason。BUS14 表示 media backend 尚未准备好；RESULT8／9／10 分别为媒体失败、等待超时和停止后 gate 复查失败。failure reason 1..8 保留 TF 原因，9 为普通录音 seal 失败，10 为 BLE 正常 seal 失败，11 为组合器观察 ready 后到实际请求间后端就绪丢失；BLE 底层细节由其观察 owner 另行提供。C API 原样提供结果 detail／media flags／reason。backend_ready 用于 PL 防止旧 done 关联，不是 C 侧可以绕开的权限。失败11也不允许自动重试。

raw MMIO 适配器沿用 `audio_services.h` 的 uncached volatile 访问和前后 `fence iorw,iorw`。物理总线 fault 仍需要平台 trap handler；回调返回错误只能覆盖有错误通道且自身有超时的 checked transport，不能让普通 load/store 自动恢复 APB fault。

## 分步辅助页面绘制

`ui_render_rows` 和 `ui_patch_rows` 仅修改指定的 1080 行物理页面范围，每行
960 个 RGB565 双像素字；空范围不写，末行截断在页内，超大 count 以剩余行数
截断，避免 unsigned 加法回卷。原 `ui_render`／`ui_patch` 通过完整行范围调用，
输出像素保持相同。glyph／矩形代码共享以控制既有 16 KiB 启动镜像容量。

分步服务必须独占 back page，并为整个 job 固定 model／touch 快照；绘制期间
到来的新提交值留给后续 job，不能让同一页混用两个状态。最后一个 slice 完成并
执行原 fence 后才请求发布，实际发布确认后才交换 front／back。这些 API 本身
不持有参数真值、不分配队列或发布页面；当前 `ui_main.c` 尚使用原完整绘制调用，
实际调度、发布等待和录音采集等待分步在 C02 后续阶段接入。CPU 周期和最长
无服务间隔仍须实测，不以行数上界代替物理总线等待保证。

`sim/run_ae350_ui_slices.py --output <新目录>` 将维护源码与固定 Git 历史
renderer 逐像素比较，并用 ASan／UBSan 检查页边界。此处只绘制辅助文字／控件，
实时分析和动态绘图仍由 FPGA owning 路径完成。

执行 checked-MMIO host 模型、ASan／UBSan 和两次完整 RV32 构建：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/run_ae350_clock_service_api.py \
  --output /tmp/ae350-clock-client-new \
  --riscv-prefix /Users/sphenicidition/.local/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf
```

runner 另需同一工具链的 `objdump`，检查实际 RV32 MMIO adapter 两侧 fence、四个 API 符号确实链接、ELF／binary／ROM 确定性、容量和输入身份。host 模型不代替 APB CDC、媒体协议、ROM 实板启动或完整调用链栈验证。
