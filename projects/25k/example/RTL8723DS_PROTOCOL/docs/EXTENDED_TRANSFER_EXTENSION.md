# 可选 OPEN_EXTENDED / 最多8112字节PCM块

`OPEN_EXTENDED=0x3c`显式选择B3 DATA与DATA成功回执。请求沿用16字节boot_id:u64、recording_id:u32、offset:u32；成功响应沿用OPEN_LONG的24字节格式。`max_chunk=min(8112,(value_limit-4)*64-48)`，4字节对齐，业务窗口1。value_limit仍ATT_MTU−3、范围20..244。value20/61/182/244时最大PCM分别976/3600/8112/8112，DATA逻辑最大1024/3648/8160/8160。B3仍4字节头、6位分片序号，最多64片，末片序号不超过63。

只有有效成功0x3c响应授权本次Transfer/B3最多8160逻辑字节；客户端还按协商value_limit限制重组长度和max_chunk。超过512的消息必须是成功DATA0xD0。Command/Response/Status、默认Capability仍512；旧OPEN_LONG0x3b仍972 PCM/1020逻辑，其他旧模式仍原限额。旧APP不会主动选择0x3c。

READ/ACK_READ仍原B1请求；长度必须在4..max_chunk且4字节对齐。DATA仍16字节逻辑头、28字节音频头、PCM和CRC32，未压缩。完整逻辑/PCM CRC、nonce、请求ID、transfer_id、boot_id、recording_id、偏移、长度和对象范围均须验证，才能用DATA作为成功回执。错误仍独立Response。APP先可靠保存PCM与原子检查点，再ACK_READ；末块独立ACK、完整对象CRC通过后CLOSE。业务窗口1、H5窗口1、27字节ACL、8个实际控制器额度不变。

计数与地址扩至13位，缓冲8192字节，最大DATA8160避免8192长度回绕。当前Gowin工具对重复宽/窄地址表达式发生截断；地址算术采用显式13位操作数，窄Response地址从完整地址切片取得。缓冲使用四个独立2048字节同步RAM，读延迟保持1周期。验收额外核对综合网表四个RAM均保留11位地址，并用实板PCM逐字节验证；源码仿真不能代替这一检查。

仅明确UNSUPPORTED0x80允许每连接按3c→3b→39→38→37→36→30回退；BUSY、超时、CRC或元数据错误不能降级。超时先重试完全相同的逻辑请求ID和字节。其他OPEN撤销扩展授权。任意4字节对齐检查点可跨七种模式续传。

已执行的缓存READ/ACK_READ在切回较小块模式后，若缓存长度超过当前允许上限，返回0x8d且不发送DATA，不改变新游标、不覆盖原缓存成功项；重开足够大的模式仍能重建原DATA，且不再次提交ACK。跨连接重新协商；板卡重启或重配置后仍须删除手机未完成下载，既有boot_id重复问题未解决。

本轮原始证据见[第十二轮](../reports/speed12_20261020/README.md)。手机原生Android GATT、UI、权限、后台及手机速率需单独实测；音源仍为内置1秒双声道48kHz PCM16测试音频。
