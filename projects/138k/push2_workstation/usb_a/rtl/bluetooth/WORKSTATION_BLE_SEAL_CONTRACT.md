# BLE 短录音外部封存边界

该边界是本地50 MHz媒体事务接口；BLE报文仍以根目录`BLUETOOTH_PROTOCOL_V1.md`和25K工程现有协商扩展为准，不新增opcode、状态值或音频格式。短录音仍为48 kHz stereo PCM16、单个片内有界对象；44.1 kHz模式下不允许开始新录音。此接口不实现DDR长录音，也不将25K独立协议或离线测试视为138K硬件接受。

## 来源和启用

`workstation_bluetooth` → 共享第一方`adaptations/bt_verilog_core.v` → `adaptations/bt_gatt.v` → `rtl/ble_protocol_command.v` → `rtl/ble_recording.v`逐层传递参数和端口。四份共享源属于`projects/25k/example/RTL8723DS_PROTOCOL/`，不是vendor。每层`EXTERNAL_SEAL_PROTOCOL`都默认0，138K新native top显式设1；既有25K工程及未启用wrapper保持原行为。

138K的`tools/workstation_bluetooth.py`调用共享`prepare_adapted.py`。后者对H5/GATT做唯一锚点检查的存储适配，wrapper工具再复制core、command、recording及受清单校验的vendor transport输入。封存端口随第一方源进入同一个checked prepare流程，不复制整链，也不修改冻结vendor、原manifest或baseline。稳定选源及物理候选另由profile owner登记。

## 50 MHz端口

| 端口 | 行为 |
|---|---|
| `seal_hold_i` | 事务owner持续持有，阻止新的REC_START/REC_STOP/REC_CLEAR变更；现有录音在request前仍可正常采样 |
| `seal_request_i` | 新事务单拍；pending中的重复请求合并，持续高电平不重复接受 |
| `seal_ready_o` | 可接收新请求；pending或此前request仍保持高时为0；关闭协议时为0 |
| `seal_pending_o` | 已接受事务尚未获得真实终态；超时后仍维持到实际清理结束 |
| `seal_done_o` | 单拍成功；仅确认该事务绑定对象已EMPTY或READY及CRC提交完成 |
| `seal_failed_o` | 每个接受事务至多一次单拍失败，恢复后不为同一失败事务补done |
| `seal_failure_code_o[3:0]` | 1已有ERROR，2活动对象enable丢失，3对象身份异常变化，4封存期间源/录音故障，8封存超时；新事务接受时清零 |
| `seal_record_state_o[7:0]` | 本事务的录音状态快照；成功为EMPTY=0或READY=4，失败可保留ERROR=5或已冻结诊断状态 |
| `seal_recording_id_o[31:0]` | 接受时绑定的原对象ID，不跟随新slot变化 |
| `seal_frames_o[31:0]` | 当前事务最终可观察前缀帧数 |
| `seal_crc_o[31:0]` | READY对象CRC；其它状态为0。失败事务的READY诊断快照不替代失败结果 |

hold须由整个媒体/时钟事务的真实owner持续到结果与回退处理完成，不能用CPU自身复位解除后立即放行新START。done/failed是本次接受的单拍结果；不得把旧done或只读READY状态复用于尚未接受的新事务。接口所有控制、快照与结果都在50 MHz，不跨域直接组合读取音频状态。

## 提交、失败和对象政策

request当沿关闭新PCM准入。此前已经接收的完整stereo word继续完成四个CRC byte与frame提交；只有capture空闲且对象ID仍等于本次绑定ID时才进入READY并冻结CRC。后续未接收PCM可被丢弃，音频采样节拍不等待封存。真实`source_ready_i`下降或`source_fault_i`在活动对象封存ACK前发生，事务明确失败，不能靠mask把源故障变为正常封存；没有修改sample rate标签。

EMPTY直接幂等成功，ID/frames/CRC均为0。已有READY保持原ID、frames、CRC并幂等成功，不依赖BLE初始化、连接、订阅、enable或当前48 kHz源。opt-in启用时，业务enable丢失不再清空EMPTY/READY对象；活动对象则进入ERROR，保留原ID和可观察前缀，拒绝正常下载。全局reset仍清除volatile对象，与原协议一致。关闭opt-in时保持原enable复位政策。

STARTING且零帧时，保留已分配原ID，封存READY、frames=0、CRC=0；START任务标失败，因为没有实际首帧，不能伪报START任务成功。已完成首帧的START任务保留原成功结果。已接受的远程STOP任务在原对象实际封存时完成；它的operation ID不被外部封存另建或替换。已有ERROR明确失败，不清除或新建对象。正常外部封存沿用已有USER_STOP=1；未增加线规stop_reason值。

同沿或已经组装但尚未执行的REC_START/REC_STOP/REC_CLEAR在hold/request/pending下返回已有BUSY=0x82，已接受的旧对象/任务先完成。此前已实际完成的CLEAR使下一次seal绑定EMPTY。完整请求CRC、nonce、精确请求缓存及错误响应仍按原协议处理；旧请求缓存重放不重新执行。INFO、任务查询及READY下载继续可用，传输引用和数据格式保持原线规。hold解除后，仍必须显式CLEAR旧READY/ERROR对象才能新建，且44.1 kHz或源不可用继续拒绝START。

默认64个50 MHz周期的封存watchdog远大于本地剩余CRC步数，异常超时发失败8并继续等待真实清理；不补发成功。该watchdog不是物理时钟/CRC正确性的替代证据。

## 验证边界

`sim/usb2/run_workstation_ble_seal.py`覆盖独立录音RAM/CRC、真实分片/CRC/缓存/下载协议、实际prepare后的五层wrapper端口，以及提前CRC提交、绕过变更屏障、掩盖source_ready三个临时负向副本。原25K `run_sim.sh`全矩阵必须在冻结输入上通过；runner可用`--protocol-result`绑定其完整结果并逐项核对当前源hash。138K `test_workstation_bluetooth.py`保留原UART/H5/真实PCM回归。

五层专项链只强制BLE初始化/连接控制与直接测试命令注入，录音、RAM、CRC、wrapper左右声道转换和全部seal端口仍为真实维护实现；真实UART/H5链另由原回归验证。未完成整机media preparation aggregator、录音→TF stop→clock联合政策、synthesis/P&R、routed CDC、实际SD/BLE/板上或部署接受。
