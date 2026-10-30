# 媒体结束结果组合

`workstation_media_preparation` 只组合常开 50 MHz 域内两个已有 owner 的请求、保持、就绪和终态。runtime owner 负责封存受控 REC、取消 score、停止并排空 TF；BLE owner 负责它自己的正常录音封存和 CRC 提交。录音对象、参数、持音及采样率核心仍各自由原 owner 管理。

`ENABLE_BLE=0` 默认逐信号透传 runtime 接口，BLE 请求与 hold 为 0。显式启用后，仅在 IDLE 且两个 owner 都 ready 时接受单拍 request，并注册向两端同时发出单拍请求。请求送达当沿已有的终态不能回答新请求；注册 owner 最早在下一沿返回本次结果。每端只接受第一个 done/failed，失败优先于同沿 done。两个 owner 都返回本次终态后，组合器才发布一次 done 或 failed；一端失败不能丢弃仍运行的另一端。

组合器在接受时自行锁住 hold。调用者（包括 CPU observer reset）撤销 hold 不会中断尚未结束的后台事务。双端终态后，等调用者 hold 撤销才释放自身 hold，再等双端实际 ready 才重新开放准入。超时/失败后仍在清理的后端必须保持自己的 pending/ready 屏障；组合器不能用旧终态替代后端就绪。公共 reset 清除组合器，CPU command reset 不连接本模块。

`failure_code_o` 保留 runtime 原因 1..9；BLE 失败映射 10，详细 BLE 原因保留在 `ble_failure_code_o`。若上游观察 ready 后、请求到达前后端已经不 ready，则本次不发后端请求并明确失败 11。上游按此失败处理和重新读取实际状态，不能自动重试。新请求接受时清除旧失败详情。

这里没有独立 watchdog。上游时钟服务负责命令超时；后端负责自己的实际停止和失败清理。上游超时不能复位组合器、解除尚未结束的 hold，或让迟到结果启动旧时钟命令。所有输入输出属于同一个 50 MHz 域，跨到 compute/memory/selected 域的握手与稳定 payload 由后端负责。

`sim/services/run_media_preparation.py` 验证两种成功顺序、同时终态、两种失败顺序、双失败优先级、调用者撤销、旧终态与请求送达沿重合、ready 竞争和默认透传，并用提前完成及复用旧结果的临时变体检验断言。此测试使用后端协议 fixture，不证明 TF、BLE、实际时钟切换或整机已经联动；真实联合回归、来源 profile、EDA 和硬件接受分别提供证据。
