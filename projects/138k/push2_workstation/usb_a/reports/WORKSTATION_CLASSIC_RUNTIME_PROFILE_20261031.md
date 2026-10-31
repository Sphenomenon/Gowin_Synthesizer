# 显式 AE350 Classic/HCI/PCM/ROM128 联合来源候选

日期：2026-10-31。此阶段交付可重建的 source/prepare 候选，不是整机、物理 CDC、持续播放或手机验收；没有调用 EDA、JTAG、SRAM 或 Flash。根任务另行负责物理与部署阶段。

## 来源与选择

独立工作副本位于 `/Users/sphenicidition/.cache/gw138k-task-20261030/classic-runtime-profile-v1/tree`，起点为 native HCI `d15ae75f6fcc021d1aaadefd1b120478771a53f9`。仅先接入实际版本化 runtime `01ed9c973993dc2daf4f7a51ef716a5673c44169` 和 PCM source `0652ce04d7720c3db185a4d91888ba1c2fb845b9`，随后增加此处显式组合。原 RTC、专用 CPU clock、metadata BSRAM、DDR owner8 和保留 BLE 业务路径均按原来源保持。没有修改 frozen baselines、vendor、历史 manifests/evidence 或 task.md。

新配置为 `custom138k-workstation-classic-runtime-v1` revision 1，复用现有 `build.py --prepare-custom-board`、固件 linker/builder 和 profile verifier。原 `--current-workstation`、pinned、resource、未指定 profile，以及旧 budget ROM128 路径的选择不变。新 wrapper 在同一宏域明确选择 native shared HCI、PCM 和 ROM128；不是完整工程复制，也不生成 runtime RTL/C 文本替身。

实际固件入口是版本化 UI startup/slice/poll/background → runtime → security/Classic/SBC → 实际 F8050200 HCI C adapter；F806 PCM C adapter 使用已有 F803 clock API。一个 UI pump 固定四次 transport pass，最多一次 SBC decode，随后保留 BLE pump。ILM/DLM 各64KiB，cache-on entry 被拒绝；新 profile 单独使用128KiB PL ROM，不放宽旧16/64KiB decoder。

GeneralBonding 的 durable backend 没有实现，因此 `firmware_runtime.enabled=0`，没有 RAM persistence 替身、bond 宣告或自动安全 grant。PCM PL caps 仍为 `0x67`，bit3 sustained、bit4 measured total delay 均为0；实际 C 在 bit3 gate 前不会 ARM、切 rate 或 source。选择了源码路径不表示可以通过公开能力入口开始持续蓝牙音乐。

## 真实 prepare 与身份

从仓库根目录重建（使用全新 output）：

```sh
python3 -B projects/138k/push2_workstation/usb_a/build.py \
  --prepare-custom-board \
  --workstation-profile custom138k-workstation-classic-runtime-v1 \
  --netlist-dir /Users/sphenicidition/.cache/gw138k-task-20261030/netlists \
  --custom-board-output /absolute/new/output \
  --riscv-prefix /Users/sphenicidition/.local/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf
```

最终外部证据根目录为 `/Users/sphenicidition/.cache/gw138k-task-20261030/classic-runtime-profile-v1`。`prepare-v6` 的 candidate 是 `custom138k-workstation-classic-runtime-v1-3961efe8f7b81db7`；548项 profile source locks、920项完整 source snapshot、636项 staged 文件、283项 enabled inputs。所有280项 enabled Verilog/SystemVerilog均经实际 `iverilog -E -g2012 -grelative-include -I.` 预处理，并在 verify 时重新执行、逐字比对；没有只检查 wrapper 字符串而跳过实际 nested include。PCM两个编译 owner、ROM128参数、真实HCI ready/epoch/generation→PCM ABI和scoped SDC也须匹配。

| 最终文件，相对 `prepare-v6` | SHA256 |
| --- | --- |
| `workstation_profile.json` | `d710d8d25682e3f4e60ff869e07910e6cf26138d58c7500dc73f474dcda9b05b` |
| `integration_inputs.json` | `f481d94b5d0b4a040e57c9d7f49a449f2d950f97067c3e95144955615ca355eb` |
| `ae350_firmware/firmware.elf` | `92eca5d392a472cdc2f570c039cc36f8c84001f7c0f6670568f5ee7aaf0fed11` |
| `ae350_firmware/firmware.bin` | `43e87f191099597e5357fa156f5f41b2deffcc1ccb1f851a84752b38a10478e0` |
| `ae350_firmware/boot.mem` | `535f56aa0efe6dd9862ebfaf1c6881448d01e7dc3070f5ef8164b954734af65e` |
| `ae350_firmware/runtime_callgraph_verification.json` | `7ca72929c18a4538e7723119454a474d7da85441643af6f4936e3a55b27ebcbc` |
| `classic_runtime_preprocessed.v` | `a62c2674fe5425adcfaf6544a960a2187d7ccf199018be8ffff44611c31b7504` |

ELF/BIN/ROM 与已冻结 runtime foundation 逐字一致：BIN94752 bytes、payload84752；upper cold29216/free36320、lower hot-load55536/free10000；ILM54928/usable remaining10604；DLMstatic7616、stack16384、unallocated41280，无heap。实际 xPack GCC15.2 链接没有GC/LTO/text overlay；实际可达171处JALR全部闭合，保守完整栈1904 bytes。四项实际audit负控也保持，不能将其视作CPU周期、物理栈水位或DDR服务预算。

## 校验与兼容性

| 检查 | 证据 | 结果 |
| --- | --- | --- |
| 联合source/config/实际prepare篡改 | `joint-tests-v3.log` | 12 tests PASS；含实际缺nested provider、ROM/PCM宏丢失、漏编PCM、固件/回调review篡改、伪造三类验收和旧review完整input identity |
| 默认profile实际prepare回归 | `default-profile-tests-v2.log` | 22 tests运行，21通过，1项未配置的legacy入口跳过；candidate `custom138k-workstation-v1-99abccce9685f880`，原16KiB来源保持 |
| 旧HCI64KiB实际prepare/verify | `hci-legacy-prepare-v3.log`、`hci-legacy-verify-v2.log` | PASS；candidate `custom138k-workstation-hci-owner-v1-25aa00137b17b088` |
| 8个profile完整source locks | `all-profile-source-locks.json` | 全部PASS |
| runtime source / accepted boundary | `runtime-source-tests-v1.log`、`accepted-source-tests-v1.log` | 12 / 17 tests PASS |
| 维护固件 / local memory / legacy storage | `stage-tests-v1.log`、`local-memory-tests-v1.log`、`boot-storage-tests-v1.log` | 10 / 13 / 4 tests PASS |
| 原budget ROM128/RV32模型 | `budget-rom128-tests-v1.log` | 12 tests PASS，仍为旧budget而非实际UI runtime替身 |
| 实际C↔native HCI | `hci-native-v1/verification.json` | 3316 checks、1712 clocks、max APB wait3；外层H5同步RAM fixture，非该测试的UART/H5或硬件 |
| 实际PCM owner / CDC与serial边界 | `pcm-owner-tests-v1.log`、`pcm-boundary-tests-v1.log` | 8 / 2 tests PASS；包括数字ppm长跑，物理sustained capability仍关闭 |
| PCM→真实DSP/chorus→唯一volume→完整I2S | `pcm-i2s-v1/result.json` | 1454物理序列模型帧，其中1436正常、18个预期fence/error静音；119 full PCM、37 half master、446 wet帧、9次history clear；双率、MIDI保留、CPU/APB在途reset、session generation和TF均覆盖 |
| 最终stage绑定 | `pcm-final-stage-binding.json` | 上述fixture全部82项消费文件逐字相同，明确绑定prepare-v6；不重新解释未消费的来源或物理验收 |

旧business/HCI间接调用review最初因源身份变化正确失败。逐项核对后，只有 `ui_main.c` 的static background wrappers与 `ui_runtime.c` 的runtime-only memcmp两项源hash需要更新。实际非runtime完整disassembly仍严格同SHA `4b75454ea9517d560d1c0efef744d5d974965e5060bcffe77ae60318620d8f1c`；73个site、instruction和target集合原样保留，没有重写接受机器码或放宽review格式。证据为 `legacy-business-machine-identity.json`。独立reviewer另用真实ci/su/dis重算得到原1344B栈，旧input manifest和unknown-target负控都拒绝；其证据在独立review目录的 `legacy-64k-review-independent.json`。

PCM候选SDC只约束实际APB held request/response、initializer boot_id与flow generation/active/is_le数据源到session capture、具体toggle首级和具体异步close/CLEAR pin。没有整域false path、异步clock-group切断或放宽音频时钟。候选metadata仍明确 `physical_endpoint_resolution_verified=False` 和 `physical_timing_verified=False`。10ns保持数据与2ns同步级间上界必须在真实综合端点、mux位覆盖和布线时序中验证；ready异步关闭/恢复、switch inhibit、serial hold传播及完整recovery/removal尚未接受。

## 保留失败与下一门禁

`prepare-v1` 保留导入PCM/ROM composition后共享top lineage hash不匹配；维护reference只更新为经review的新top，原effects provenance/adaptation/FIFO字节和两个存储selector均保持。`prepare-v2` 保留预处理参数顺序错误。旧HCI `hci-legacy-prepare-v1/v2` 保留两项source identity尚未全部更新时的拒绝；只有最终v3通过。中间identity、旧source snapshot变化后的失配，以及误用仅供default profile的测试/错误CLI调用的日志均保留，不改标PASS。

下一阶段须独立完成实际C↔PCM RTL联合fixture审阅、实际CPU/DDR周期与服务期限、完整综合网表CDC/复位/PLL、资源、routed setup/hold/recovery/removal、总延迟、物理栈水位及手机认证/加密/重连/播放。GeneralBonding durable backend与显式session-only策略是分开的后续工作；均没有在此阶段自动开启。持续PCM位与delay位不能因离线模型通过而置位。

回滚通过停止选择新profile并恢复前一维护source commit完成；默认/accepted/pinned入口保持各自来源策略。此阶段没有bitstream identity、SRAM部署、Flash写入或板上状态改变；不得继承旧综合/物理/硬件接受。128KiB容量保持明确，96KiB等容量实验须另立identity和越界/等价证据，不能静默改写本候选。
