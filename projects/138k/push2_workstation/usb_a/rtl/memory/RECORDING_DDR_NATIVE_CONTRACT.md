# 未选择的 owner8 DDR 组件

`workstation_recording_ddr_client_queues`、`workstation_recording_ddr_arbiter_pipeline` 和 `workstation_recording_ddr_native_bridge` 仅是可显式选择的 DDR 机制。本阶段没有改 top、profile、固件、录音业务 owner、最终 PCM CDC 或现有 BLE 后备。没有通过测试实例化宣称生产接入或物理资源节省。

## 来源与默认隔离

原 `rtl/timing/basic_pitch_ddr_client_queues.sv`、`basic_pitch_ddr_arbiter_pipeline.sv` 及 music 同名来源保持不变。生产 prepare 的 timing 文件仍受 `workstation_bus_timing.MODULES` 硬锁；资源父配置另有 `slot_payload` 的受控适配。本新增版本不进入这些变换，不改 baseline、vendor 或硬锁以强行通过。

两新组件的 `RECORDING_ENABLE` 默认0，generate 的默认分支直接实例化旧组件。关闭时没有新 recording slot、owner tag 宽度或 fairness 寄存器；录音 ready/response和 native_accept 均为0。queues 的 core_accept 也为0，因为旧 wrapper 没有导出其内部边界，不能用 slot ready 冒充；独立 core 的 core_accept仅别名原各 ready。queues 的 slot_accept仍是实际外部 valid&&ready。旧 externally visible 输出需逐拍等价，未完成该证明不得宣称默认路径兼容。这里的资源路径是源码结构事实，未运行新组件综合/P&R，不提供实际物理资源计数。

开启分支复用原 `basic_pitch_ddr_client_slot`，每client一个稳定本地槽；新 core 维护在版本化源码，不由构建器逐文本生成。现有 owner0=BIST、1=scan、2=CPU、3=writer、4=TF audio、5=music/CNN、6=delay、7=display保持；recording独占8。`TAG_BITS` 只决定返回队列深度 `1<<TAG_BITS`（默认32），与owner位宽不同。启用时 tag entry、reservation_owner、command_owner、response_owner均为4 bit，grant为9 bit。

旧输入／选入路径只能在显式新来源策略/profile revision中切换：登记新依赖、唯一编译 owner、来源哈希和默认旧路径准备比较，再做同配置物理验证。当前 revision5、accepted/pinned、resource-only和无profile新板入口全部保持现状；没有新的 builder 或复制完整工程。旧路径只有在真实客户端、mask/返回/取消/期限、物理时序和硬件验收齐备后才可退役，历史来源及证据继续保留。

## 三层接受边界

所有端口均为持续运行的 DDR UI 域，原生地址为32-bit word，BL8=32 B、地址步长8，active-low mask的1表示保留对应字节。模块不重新分配地址，调用方使用唯一 `ddr_address_map.vh`。同一通道有序读返回及先写后读可见仍需控制器保证。

| 事件 | 成立条件及含义 |
| --- | --- |
| slot_accept_o[owner] | producer valid&&local ready，完整request写入其稳定槽；不代表core或DDR已接收 |
| core_accept_o[owner] | 已排队request被复制到共享native command寄存器；registered grant只引用稳定槽，不是额外payload缓存 |
| native_accept_o[owner] | 实际app_en且已存command_owner匹配；读push返回owner账本；写同时满足app_ready与app_write_ready，并assert app_wren/app_wend |
| client response及response_data | 控制器app_response按顺序pop一项账本，owner pulse与256-bit data共同寄存后交付；不能直接用当拍raw data搭旧pulse |

启用时每个core/native事件最多一位为1，多个client可同拍接受到各自slot。native command在stall期间保持cmd/address/data/mask；没有用PHY ready反馈重开本地槽，也没有撤销等待中的command。读队列满时停止新的读buffer/native接受，写仍可前进；同时pop/push沿用原账本规则和保守空拍。CPU单读pending、BIST独占及BIST→display身份分离保持。

## owner8 真实接受桥

backend发布一条命令后保持valid及payload直到真实native接受。桥仅用一个submitted位：首次slot接受后屏蔽重复enqueue；slot变空、core buffer接受或用户cancel/soft reset都不能清submitted。只有 `native_accept_o[8]` 清submitted并产生backend的ddr_ready。一次只有一个已提交recording命令，所以该pulse对应唯一保持中的payload，不生成第二份业务对象ID。

桥不新增数据shadow buffer；源payload稳定是明确契约，并在backend及独立native scoreboard中检查，硬件不宣称能逐位检出所有payload变更。无submitted的native完成、或submitted时源撤valid会经组合protocol_fault_now立即关闭admission/输出，并锁存protocol_fault；不能等到下一沿才让READY/download知道。cancel/soft reset是业务作废而非通道复位，已发布命令继续排空；桥、slots、core、控制器返回账本和backend只能共同复位，不能单独清桥后把旧完成归给新命令。

## 失败、取消与返回

新core检测无账本的app_response，以及账本中的非法owner（3仅写；9..15未分配）。`transport_fault_o`包含检测当拍和sticky response_fault，故障已可见的采样沿不得继续admit新下载。非法owner不产生成功response；其pop与故障被记录，不能误路由到BIST或别的client。物理响应不得在native读接受同拍提前返回；此接口要求later、once、in-order。

sticky fault不撤销已发布native command、不清返回count/tag、不伪造排空。新的backend可显式设置 `TRANSPORT_FAULT_ENABLE=1`，把core/bridge fault接到transport_fault_i；故障在CAPTURE、SEALING、READY或下载都进入failure9/ERROR，关闭新请求和输出，已有终态保持。fault仍高时，终态也不开放clear/create，soft reset不重新arm；共同controller/ledger/backend复位才清故障。旧默认参数0忽略这一新增输入，source_error仍只有采集期含义。

已接受读延迟返回时，取消、引用release或transport fault仍保持读pending；真实返回后丢弃旧数据，禁止流入新对象或预取。若返回永久丢失，只能保持失败及禁止复用，直到共同复位；超时不能代替账本完成。故障不等于全客户端恢复协议：本组件没有为既有CPU/TF/CNN各业务补上终态或系统级重新启动策略。

## 调度边界

scan、music_turn、TF audio、display、delay保持原高优先级结构。背景组recording与原CPU/writer选择交替；recording也计入music的背景竞争条件。recording_valid=0时原仲裁选择和legacy可见行为需逐拍相同。该局部turn防止连续recording把CPU/writer永久挡住，不建立对无界scan/audio/delay的全局公平保证；这些高优先级持续有效仍可阻挡背景请求。

真实集成必须另定各client最大突发/水位/期限和控制器Gread、联合Gwrite、Lread，按实际流量验证D01/D04；native bridge本身不提供服务期限。后端FIFO overflow或命令/返回deadline按既有规则显式失败，音频采样不等待。测试中的并发music/NN是合法有界client流量模型，不是完整CNN算法或任意最坏流量证明。

## 显式 R00 生产选择

`custom138k-workstation-r00-v1` 现在显式把这些机制接到真实生产 top/HDMI、物理 PCM 与 AE350 对象服务，见[服务组合契约](../services/RECORDING_DDR_SERVICE_CONTRACT.md)。上述默认与原组件阶段证据保持原边界；其他 profile 仍未选择本路径。生产选择不提升物理 CDC、时序、资源收益或硬件接受。
