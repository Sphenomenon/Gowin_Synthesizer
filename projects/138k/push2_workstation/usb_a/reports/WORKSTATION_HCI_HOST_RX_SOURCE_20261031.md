# HCI host RX lease／return 源阶段

日期2026-10-31。源基点为共享HCI源阶段 `cd34562c31f71a8579a868d6d56844f9eee4a2d7`；新隔离clone开发，不改其sealed tree或既有证据。该阶段尚未由任何整机profile选择。

## 实现

新增 `rtl/bluetooth/hci_owner/workstation_hci_host_rx_owner.sv`，管理控制器→主机物理ACL包预算、外部RAM槽租约和专用0x0c35归还。发送owner仅增加只读 `handle_is_le_o` 观测端口，让RX分类和generation使用同一权威handle表；原发送行为与状态不改，原bench增加对应wire。

默认4个物理RX槽、276字节data，保留1个空闲槽供BLE。Classic慢消费者至多占用其他3槽；完整丢弃的物理包登记pending return，CPU服务不参与接收准入。lease token严格递增、不回绕；政策丢弃、槽满和代次耗尽有独立drop reason。代次耗尽要求受控共同恢复，不以重连绕回token。

控制器预算只有实际接收packet才debit，只有0x0c35不可撤回接受或断连隐式flush才增加。consumer release只增加pending，不能提前退款。实际8字节HCI命令为opcode0x0c35、参数长度5、一个handle/count pair，经唯一flow owner的专用owner3发送，普通命令credit为零仍可发送。归还snapshot的count／handle／generation保持稳定，新完成包另计；packet bytes持有至匹配transport_done，不能在接受后改写给H5读取或自动重放。

Core HCI §4.3允许控制器在Disconnection Complete后视host buffers已flush，因此断连清pending并隐式退款，撤销未接受的旧return。仍有真实读者的外部RAM槽只标retired，保持物理租约，直到有效token的真实release；旧槽释放不重复退款，相同HCI handle的新generation不复用旧槽。外层丢失disconnect或偷偷改变权威generation时明确fault，不猜测状态。

详细握手、错误、取消与集成约束见[README](../rtl/bluetooth/hci_owner/README.md)。激活输入只代表外层已真实完成Host_Buffer_Size／ACL flow enable；该bootstrap producer和原H5路由仍未实现，不能据此宣称H5接收包长已被控制器约束。

## 验证与身份

入口：`python3 -B projects/138k/push2_workstation/usb_a/sim/run_workstation_hci_host_rx_owner.py --output /absolute/external/empty-dir`。最终证据为 `/Users/sphenicidition/.cache/gw138k-task-20261030/b04-hci-rx-owner-v1/verification-v2/verification.json`。

| 范围 | 结果 |
|---|---|
| 实际RX RTL+真实发送owner | 160,228 checks，12场景，10,000步独立模型；3,146个物理RX，2,822个显式归还，其余由断连／在途／最终模型状态区分 |
| 定向场景 | Classic保留BLE槽、普通命令零credit、RAM quarantine／重连、旧token／重复释放、未接受snapshot撤销、新completions不改snapshot、接受后bytes跨RX／release／disconnect稳定、最后token、控制器超预算、坏handle／长度、漏生命周期、transport不确定性与非法完成 |
| RX行为突变 | 13项全部由实际断言拒绝：移除reserve、drop不归还、断连不退款、旧DMA槽提前重用／丢retired身份、旧snapshot不撤销、inflight bytes改写、token回绕、忽略release身份、不扣outstanding、接受时清payload、忽略owner漂移、命令参数长度错误 |
| 原共享HCI回归 | 116,780 flow checks／15场景／10,000步，9,174 event checks／1,830events／1,806schema长度负测；原11行为突变全拒绝，4参数错误拒绝 |
| 严格工具检查 | Icarus13.0实际编译／仿真；三个module的Verilator5.052 `-Wall`无warning豁免；新增8个无效参数显式拒绝 |

第一轮 `verification-v1/` 保留158,656 checks；第二轮增加显式drop／exhaustion reason后验证以上最终源码。开发bench曾有posedge驱动竞争，已将输入握手驱动固定到negedge，完整重跑；不将调试失败误作RTL通过证据。

| 最终测试输入 | SHA256 |
|---|---|
| flow owner（只读LE分类端口） | `a3d51a2d2c07cb16cfe221a67f1bca82bf3bf5952afa27576ca005358b34f67b` |
| host RX owner | `82ff377a3516d3be912cb98eedf5ef904d3720a69aedf673644bc63ede6a9105` |
| host RX bench | `bec13bbfc03e357216716f3634fb73289f0200ac0b1b99c3f42713490ccb274f` |
| host RX runner | `b371c76144cd3ad1b96afe6f51cc556086d4ee9aa89915d49417bf640c861874` |

原始规范、回执和历史源阶段保持在只读 `b04-hci-owner-v1/standards/`。本阶段使用Core6.0 HCI §4.2、§4.3、§7.3.39、§7.3.40；具体官方URL／SHA256见[前一源阶段](WORKSTATION_HCI_OWNER_SOURCE_20261031.md)。完整规范不进入仓库。

## 剩余边界与回退

本模块不含payload RAM、实际copy／DMA／邮箱、H5收包router或Host_Buffer_Size／Set_Controller_To_Host_Flow_Control producer。真实release必须来自硬件完成与读者排空复核，不能把CPU声明直接当物理空闲；lease grant也不是payload已完整复制的发布屏障。持续断连留下的未完成读者可能占满RAM，届时BLE也按明确drop／链路停止政策处理，不能宣称reserve解决了未完成的物理读者或无线调度时限。

双向在途0x0c35与控制器已发生的disconnect可能竞争；接受后的packet保持原字节，异常0x12响应使共享账本fault，不能重放到新generation。RTL8723DS对该竞争的实测行为、bootstrap命令支持、H5吞吐／重传、原bridge与GATT信用退役、CPU服务延迟与完整BLE行为保留仍未验证。

没有生产profile变化、EDA、净资源收益、STA／CDC／PLL、SRAM／Flash操作、物理音频、手机互通或SIG qualification结论。回退为移除未选择的RX组件／其测试与只读分类端口；不改变现有板上身份。后续生产集成必须以新source／configuration／bitstream身份独立验证。
