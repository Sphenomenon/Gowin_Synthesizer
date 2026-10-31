# 双 138K DEMO 原生邮箱局部 CDC 验证，2026-10-31

本阶段复用 `workstation_runtime_profile.py::protocol_constraints`，补显示邮箱的 98 位注册 RAM 输出路径及 `loss_meta_0`。RAM 路径保留 20 ns 最大飞行界限，仅免除这些异步数据路径的 hold 检查；目标逐位限定为 `destination_data[202:105]`。源选择器覆盖综合时 3×36 位及布线时拆出的 6×18 位 SDPX9B。其余同步级、第三请求级及故障锁存级保留 setup/hold 检查；没有新增整时钟例外。

新增 `tools/workstation_native_protocol_audit.py`，复用现有 Graph、BDD 和网表解析器，逐位证明四个原生邮箱的 req 三级、ACK 两级、首级只驱动第二级、capture/ACK 同使能、busy 时不覆盖，以及所有数据的唯一驱动。显示低位普通 FF 为 M=73、W=41，98 位物理 PCM/身份信息均来自注册 RAM 读输出，且 RAM 的 CLKB、CEB、READ_MODE、输出物理位及全部目标连接均受检查。两个丢帧源均证明为 `sticky | nonzero-counter`，保留“最后一次 drop 后立即停 compute”旁路。

| 实际输入 | 局部结构闭包 | 实际已安装 SDC | 网表 SHA256 前缀 |
|---|---|---|---|
| M5 VG | 通过，3×36 RAM | 本阶段未验证 | `d3906d766d5f` |
| W5 VG | 通过，3×36 RAM；TF 已退出 | 本阶段未验证 | `4647aa544a7b` |
| M5 routed VO | 通过，6×18 RAM，98 位逐位闭包 | 本阶段未验证 | `8e3001016a38` |
| M7 新 VG | 通过，3×36 RAM | `custom_138k.sdc` 局部检查通过 | `4e77d5b5ae1f` |
| M7 新 routed VO | 通过，6×18 RAM，98 位逐位闭包 | `physical.sdc` 局部检查通过 | 见配套 JSON 完整身份 |

实际 M5/W5 VG 各 11 项网表破坏控制拒绝；M5 routed 最终 17 项测试通过，包含 13 项网表破坏控制、11 个 SDC 删除/后级 setup/hold 例外拒绝场景及两个策略/模型测试。随后用最终代码重跑后级 setup/hold 拒绝和 W RAM 额外消费者检查，均通过。没有把 M5 VO 与 M7 SDC 的兼容性检查记作 M5 的实际安装证据。

真实 Gowin GW5A 库模型同时验证 18/36 位 READ_MODE=0：1024 次 busy 写入和其中 512 次停止读时钟期间，注册 DO 保持不变，下一次接受才更新。模型文件 SHA256 为 `2ec53fec48601d2d491299bc3a28b4b199d3a79708f1dd38f72555a5c688ebd5`。现有真实 FIFO/邮箱 final-drop fixture 同样通过：physical/display 各一次最终丢帧、两次源停止、四次 reset、counter wrap，均无需后续帧。

最终 CLI 对审计代码及 Graph/parser/协议依赖、维护契约、网表和可选 SDC 做 before/after 稳定性检查，输出 `source_seal`。它证明本次审计读取稳定，不能代替整机编译输入封存。完整证据路径、散列和检查范围见 `DUL138K_NATIVE_CDC_20261031.json`。

**限制：**这是局部结构、选择器和离线协议证明；全量 CDC、PLL、reset、完整 routed timing、硬件声画、SRAM/Flash 部署均未获本报告接受。M7 虽已完成布通，仍有其他 setup/hold 失败；不能由本地证明推导整机 release_ready。下一阶段继续处理 TF held-control 与 PC health 等实际剩余跨域路径。

M7 实际 VO 的重跑命令：

```sh
python3 projects/138k/push2_workstation/usb_a/tools/workstation_native_protocol_audit.py \
  --netlist /Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v7-physical-v1/impl/pnr/custom_138k_integration.vo \
  --mapping routed --profile m-demo-base \
  --sdc /Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v7-physical-v1/physical.sdc \
  --output /Users/sphenicidition/.cache/gw138k-dual-20261031/native-protocol-cdc-v1/m7-vo-final.json
```
