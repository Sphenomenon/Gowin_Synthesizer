# BSRAM 快照探针接回主线

日期：2026-10-31。主线导入 `079e92f`、`6f36177`、`3c2148e`、`72959b1`，保留旧 full64／banked4 模式，新增显式 bsram4。实现与原始场景见[源码记录](WORKSTATION_AE350_BSRAM_SNAPSHOT_SOURCE_20261031.md)，CF 失败和 D0 窄约束修复见[实际结构记录](WORKSTATION_AE350_BSRAM_CF_STRUCTURE_D0_CDC_20261031.md)。

## 根端验证

重新执行新 RTL 9 项、严格网表结构 3 项、accepted 来源 17 项、旧 banked 9 项、旧 probe 9 项、旧 full64 5 项，全部通过。实际 CF、D0 综合 VG 也由主线当前审计器各自重新解析通过：704 位 GAO、8 个 native16 SDPB、1,858 位 held payload 实际到 RAM DI，128 位 RAM DO 同时到 GAO 与 UART cache，reference FF 1,292，保留 512／384／32 位有界缓存，没有原冗余宽快照。

作者独立真实网表附件重新验封／重放通过：269 文件、两个真实 VG、10 个实际网表负控；其中断开 held→RAM 或 RAM→UART 的负控即使保留寄存器／GAO 也被拒绝。该附件 manifest SHA256 为 `fe0911fbb7c019a075b56549d9679f3bec08403fa1ad23dc7622d1861eab9829`。

主线新 prepare 使用独立身份 `C21031D1`，44 项输入／9 个编译源、36,368-byte BIN／64 KiB ROM 校验通过。D1 只做 prepare，不排队物理实现。当前实际运行的 D0 仍严格使用作者 `b3b4877` 的冻结 44 项输入；此后审计代码没有改入 D0 实际构建。

8 个整机 profile 只刷新 `build.py` 新增 CLI 模式这一项 hash，保留联合 runtime／PCM／RTC／metadata 的既有锁。新联合整机 prepare 为 `custom138k-workstation-classic-runtime-v1-647217d6dfc7b7b9`，636 staged／283 enabled 与此前 `3855490f159913c6` 逐字一致；因此本次探针接入不改变该整机的编译字节，也不转移任何综合或物理接受。

## 证据及状态

根端目录 `/Users/sphenicidition/.cache/gw138k-task-20261030/bsram-snapshot-main-parent-v1` 保存 22 份源码快照、1,176 份外部文件身份及独立 `verify.py`。seal SHA256 为 `6406f1566d010c218acfa9816b031e5d0f055e3de6c28bb070f9d9aa0a7c127c`。详细字段见[机器记录](workstation_task_20261030/ae350_bsram_snapshot_main.json)。

CF 真实综合通过，但 SDC 报 TA2003，未进入布局；D0 只修正实际 generated RAM 的约束对象拼写，保留 20 ns 与 hold 预算，独立物理实现仍在运行。以上 VG 检查不证明物理 BSRAM 数、routed CDC／STA、真实 UART 接收、SRAM Verify 或硬件功能接受。此源码阶段没有操作板卡或写 Flash；原 Flash 回退不变。
