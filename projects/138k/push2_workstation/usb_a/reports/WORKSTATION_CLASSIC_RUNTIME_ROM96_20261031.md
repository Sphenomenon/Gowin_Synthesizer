# 显式 ROM96 联合候选：同 ELF/BIN，严格物理范围

日期：2026-10-31。此阶段从已冻结128K联合来源 `e0688427d517632cc61eae16300efa15500eb0e0` 建立新的独立clone和identity，交付source、固件、实际RTL模型及prepare。没有EDA、JTAG、SRAM、Flash或手机操作；物理资源、CDC、时序和硬件验收均未升级。

## 选择与合同

新增显式 `--workstation-profile custom138k-workstation-classic-runtime-rom96-v1` revision1，使用原入口、原runtime构建函数、原实际UI/Classic/SBC/HCI/PCM业务实现。旧128K profile的configuration逐字段不变；default16K、HCI64K、accepted/pinned及旧budget ROM128保持各自来源选择，没有添加编号builder或复制业务工程。

实际ROM为98304 bytes：下64KiB容纳startup及ILM/DLM加载镜像，上32KiB容纳cold代码。代码仍从 `0x80000000` 启动，cold从 `0x80010000` 开始，实际cold结束于 `0x80017220`，物理上限 `0x80018000`，cold剩余3552 bytes。ILM/DLM仍各64KiB，cache仍关闭；没有把ROM缩减解释为本地memory或cache扩容。

原linker的历史 `__boot_rom_bytes=131072` 和128KiB布局不改，以保留完整ELF及其全部符号。它在本variant仅是linked address envelope，不能用作实际容量事实。新增 `physical96_report` 在真实ELF重建BIN之后另行逐PT_LOAD核对ROM存储LMA/file-end、ROM运行范围、ILM64/DLM64运行memspan、保留stack边界、hot-load64K及cold-end96K。DLM的NOLOAD尾部消耗DLM，不虚构为ROM文件字节；错误memspan也拒绝。版本化 `tools/ae350_rom96_reference.json` 继续锁定冻结128K候选的完整ELF/BIN/NM；未来改代码或compiler不能未经review继承same-code身份。

实际 `boot.mem` 只含24576个word，并逐字等于原128K image前缀；删掉的8192个word必须全部为零。原32768-word image保留为独立 `link_layout128_boot.mem` 证据。capacity/cold_boot记录的物理值是98304，`physical_storage`单列linked128K和physical96K，verify重算这些事实，不信任手写metadata。原16/64KiB decoder和旧budget split_memory_report继续拒绝96K；只有新显式联合profile可选。

原native ROM的power-of-two mask不能用于96K，会误拒绝中间32K。新98304分支使用完整32-bit严格range，保留已有word索引、AHB传输、diagnostic、8KiB scratch RAM及idle响应语义。超范围读返回原EBREAK字 `0x00100073`，没有添加新的总线error接口；16/64/128分支保留原mask选择。

GeneralBonding仍关闭，没有durable bond backend或自动session-only开放。PCM caps仍0x67，持续能力bit3、实测总延迟bit4仍为0；cache-on entry仍拒绝。same-code不表示上述功能或真实持续音乐已接受。

## 真实prepare与来源

独立外部目录：`/Users/sphenicidition/.cache/gw138k-task-20261030/classic-runtime-rom96-v1`，仓库在其 `tree/`。仓库根目录重建命令：

```sh
python3 -B projects/138k/push2_workstation/usb_a/build.py \
  --prepare-custom-board \
  --workstation-profile custom138k-workstation-classic-runtime-rom96-v1 \
  --netlist-dir /Users/sphenicidition/.cache/gw138k-task-20261030/netlists \
  --custom-board-output /absolute/new/output \
  --riscv-prefix /Users/sphenicidition/.local/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf
```

最终 `prepare-v3` candidate为 `custom138k-workstation-classic-runtime-rom96-v1-f4163f936e41e1e4`，923项完整source snapshot、637项staged、283项enabled，其中280项HDL实际执行relative-include预处理并在verify重放。源码/实际provider/ROM96参数/PCM owner/HCI tuple ABI/约束和固件回调闭包都独立绑定。

| 文件，相对 `prepare-v3` | SHA256 |
| --- | --- |
| `workstation_profile.json` | `c5e9c69434dc46abbcfadcc3f98a40db149122c09345d780de649e7e0024bc1e` |
| `integration_inputs.json` | `44f65b481b99c89ef9ba136e8fc8cc50c9a7edb10100a579b70d23720bb9951c` |
| `ae350_firmware/firmware.elf` | `92eca5d392a472cdc2f570c039cc36f8c84001f7c0f6670568f5ee7aaf0fed11` |
| `ae350_firmware/firmware.bin` | `43e87f191099597e5357fa156f5f41b2deffcc1ccb1f851a84752b38a10478e0` |
| `ae350_firmware/boot.mem` | `82c8daab98745ff61636691d7e8e786e3ca159c88c3ea0023546d5361aac9294` |
| `ae350_firmware/runtime_callgraph_verification.json` | `48236bc66fd31d7df5a4d04b97edd6932d6ecd0006df31eedf87cc49fa3a52b8` |

`rom96_same_machine_comparison.json`对新96K、新128K复验和原冻结128K三份实际构建比较：完整ELF、BIN、NM、disassembly均逐字相同。BIN94752/payload84752；ILM54928/usable remaining10604；DLMstatic7616/stack16384/unallocated41280；实际171处可达JALR闭合，保守stack1904 bytes，原四项audit负控保持。这里只改变零padding和物理ROM译码/容量，不改变代码地址、业务ABI、cache/ILM/DLM配置或已有audio实现。

## 通过的验证

| 验证 | 最终证据 | 结果 |
| --- | --- | --- |
| 新96K来源/真实prepare/越界/模型 | `prepared-tests-v3.log` | 11 tests PASS |
| 全部native ROM字与原128K前缀 | 同上 | 24576字逐字比对；64K/96K/128K边界、非对齐低位、非法高地址、wrap alias、idle和diagnostic保持 |
| 两个实际RTL负控 | 同上 | 误用power2 mask、删除上界均在range/alias断言处失败 |
| 实际128K链接成功但96K溢出 | 同上 | 新4096-byte cold对象成功链接于128K，实际BIN超过96K后被新物理gate拒绝；不是只改一个metadata数值 |
| 实际ELF ROM/DLM memspan负控 | 同上 | PT_LOAD越界均拒绝；ROM padding或物理容量证据篡改也拒绝 |
| 实际RV32 cold-loader/ABI | 同上 | 96K可读image与128K的ILM、DLM、寄存器、diagnostic一致；cold区所有word可取；上界外拒绝；I/Dcache-on三组均halt且不进入ILM。严格instruction模型不代表真实CPU周期或加密hard-IP接受 |
| 原128K联合profile实际prepare | `rom128-profile-tests-v2.log` | 12 tests PASS；candidate `custom138k-workstation-classic-runtime-v1-2e25419c6a5927f9` |
| 默认16K实际prepare | `default-profile-tests-v1.log` | 22 tests运行，21通过，1项未配置legacy入口跳过；candidate `custom138k-workstation-v1-c743dd86fc866e64` |
| 原budget ROM128 / 原16/64存储 | `budget-rom128-tests-v2.log`、`boot-storage-tests-v1.log` | 12 / 4 tests PASS；含原32768字native ROM128、旧budget/RV32/SBC和原容量拒绝 |
| accepted / runtime来源 | `accepted-source-tests-v1.log`、`runtime-source-tests-v1.log` | 17 / 12 tests PASS |
| 全部9个profile来源 | `all-profile-source-locks.json` | 全部PASS；旧business来源回归也通过 |

所有失败和中间身份原样保留。`budget-rom128-tests-v1.log`是未指定xPack前缀、默认 `riscv64-elf-gcc` 不在路径的工具调用失败；v2显式同compiler后全过。`rom128-profile-tests-v1.log`保留最终source/docs收敛前旧snapshot被严格拒绝，v2用全新prepare后全过。没有把旧source identity改名为新接受。

## 资源和采用条件

原始ROM声明范围减少32768 bytes，相当于16个512×32逻辑存储bank；metadata不宣称少16块物理BSRAM。Gowin可能已裁掉128K中的不可达或常量零padding，逻辑bank不保证与物理BSRAM一一对应，推断/打包/优化也可能改变结果。此阶段没有真实综合、P&R或净资源收益，`actual_resource_savings_verified=False`；需要由根任务在相同业务、tool/source/约束下对128K和96K做实际综合/物理对照后决定选择。

已冻结128K目录及其seal保持不变；新96K不会自动替换128K或accepted。退出新variant即可恢复128K profile选择；物理容量/DDR/PLL/CDC/时序和真实音频/手机仍按独立门禁验收。本阶段无位流、SRAM或Flash状态改变。
