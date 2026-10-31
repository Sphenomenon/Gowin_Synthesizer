# AE350 联合来源接回主线

日期：2026-10-31。源码检查点 `ed1441d`，导入实际 cooperative Classic/SBC runtime、原生共享 HCI、PCM→现有效果／I2S，以及显式 ROM128 profile；没有将新配置设为默认。此阶段是源码和离线验证，不包含综合、P&R 或硬件接受。

## 主工作区复验

沿用既有 `build.py --prepare-custom-board`，使用 xPack GCC 15.2 和已锁定的三份网表，分别重新准备以下四个候选；全部通过实际 profile verifier。

| 配置 | 新候选后缀 | staged / enabled |
| --- | --- | --- |
| Classic runtime / ROM128 | `3855490f159913c6` | 636 / 283 |
| 原 HCI / ROM64 | `0755fc0c376408b8` | 627 / 281 |
| 原 business / ROM64 | `422ec8c8f42513fb` | 614 / 272 |
| 默认 workstation | `9318c94899286ff9` | 581 / 261 |

联合候选实际预处理 280 份 HDL，完整来源快照 920 项。8 个 profile 的来源锁全部通过；accepted 边界 17 项、联合来源／prepare／篡改 12 项、原 business 8 项、维护固件 10 项通过；默认 profile 运行 22 项，其中 1 项未配置的 legacy 入口跳过。原 business 首次未指定 prepare 的三项跳过已由最终真实 prepare 的 8 项完整回归补齐。

主工作区独立重跑真实 C→APB/CDC→PCM→DSP→唯一最终音量→I2S：1,644 个引脚解码帧、24 块／3,072 个实际 RAM word、711 reads／3,395 writes，最大 APB wait 7；181 个直接双声道、37 个半音量、150 个 mono、8 次效果历史清理和 360 个 chorus 结果通过。测试用读包装仅在测试中注入 sustained 位，实际 PL 能力仍为 `0x67`。三个负控由已重新验封的独立交付保留，本次不重复计作根端执行。

## 存储、身份与兼容范围

实际 ELF／BIN／ROM 与作者冻结版本逐字相同：ELF `92eca5d392a472cdc2f570c039cc36f8c84001f7c0f6670568f5ee7aaf0fed11`，BIN `43e87f191099597e5357fa156f5f41b2deffcc1ccb1f851a84752b38a10478e0`，ROM `535f56aa0efe6dd9862ebfaf1c6881448d01e7dc3070f5ef8164b954734af65e`。

ILM 使用 54,928 / 65,536 bytes；DLM 静态跨度 7,616 bytes，预留 16,384 bytes 栈，未分配 41,280 bytes。171 个实际可达间接调用点闭合，保守调用链栈 1,904 bytes。I/D Cache 各 32 KiB 的硬件能力没有计入普通 RAM 容量，当前仍关闭；PMA、Cache 维护、实际 CPU 周期和硬件水位须另验。BSRAM 扩容与 96 KiB ROM 变体按独立候选测量，不改变本候选身份。

原 business/HCI 的完整反汇编均保持 `4b75454ea9517d560d1c0efef744d5d974965e5060bcffe77ae60318620d8f1c`，未放宽原 73 站点 review。默认 staged 与上一检查点有六项明确变化：top 的两份暂存副本、runtime controlled/audio、serializer 及 provenance helper；新增入口由默认关闭的参数／宏控制。默认回归通过，不声称 staged 字节不变，也不转移旧综合或物理接受。accepted/pinned 来源策略保持。

## 封存与后续

外部目录 `/Users/sphenicidition/.cache/gw138k-task-20261030/classic-runtime-main-parent-v1` 保存 1,041 份源码快照及 2,920 份外部文件身份，`verify.py` 可独立重新验封。seal SHA256 为 `24915a186207d1289829edde5368f446f2b7068234bf861aeb3dc1332750ed89`。精确配置、容量、默认差异和结果见[机器记录](workstation_task_20261030/classic_runtime_main.json)。作者联合及独立桥接 seal 均重新核验通过；早期 verifier 路径／Python bytecode 附件误差的失败日志保留，最终未修改冻结交付内容。

GeneralBonding 缺持久后端，实际 runtime 仍禁用；持续 PCM 位3与实测总延迟位4仍关闭。完整资源、CDC／PLL／routed STA、Cache／PMA、服务期限、长期频差及真实手机音频仍未接受。没有 SRAM／Flash 操作；板上状态不由此报告推断。源码回滚可停止选择新 profile 并恢复此前维护提交；现有 Flash 回退身份保持独立证据。
