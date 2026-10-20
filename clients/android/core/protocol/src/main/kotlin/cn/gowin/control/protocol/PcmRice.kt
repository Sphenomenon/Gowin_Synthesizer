package cn.gowin.control.protocol

/** Bounded codec10, stereo signed16 modular deltas and Rice k9. */
object PcmRice {
    fun decode(encoded:ByteArray,pcmSize:Int,codec:Int,allowSecond:Boolean=false):ByteArray {
        checkWire(pcmSize in 4..8112 && pcmSize%4==0,"PCM 长度无效")
        if(codec==0) {
            checkWire(encoded.size==pcmSize,"原始 PCM 长度错误")
            return encoded.copyOf()
        }
        checkWire((codec==10 || allowSecond && codec==11) && encoded.isNotEmpty() && encoded.size<pcmSize,"无损 PCM 编码或长度错误")
        val k=if(codec==11)5 else 9
        var at=0
        val end=encoded.size*8
        fun bit():Int {
            checkWire(at<end,"无损 PCM 数据截断")
            val value=(encoded[at/8].toInt() ushr (7-(at and 7))) and 1
            at++
            return value
        }
        val previous=IntArray(2)
        val before=IntArray(2)
        val pcm=ByteArray(pcmSize)
        repeat(pcmSize/2) { index ->
            var q=0
            while(q<15 && bit()==1)q++
            var value=0
            repeat(if(q==15)16 else k){value=(value shl 1) or bit()}
            if(q==15)checkWire(value ushr k>=15,"非规范无损 PCM 转义")
            else value=value or (q shl k)
            val delta=(value ushr 1) xor -(value and 1)
            val channel=index and 1
            val predictor=if(codec==11)2*previous[channel]-before[channel] else previous[channel]
            val sample=(predictor+delta) and 65535
            before[channel]=previous[channel]
            previous[channel]=sample
            pcm[index*2]=sample.toByte();pcm[index*2+1]=(sample ushr 8).toByte()
        }
        checkWire(end-at<8,"无损 PCM 尾部冗余字节")
        while(at<end)checkWire(bit()==0,"无损 PCM 填充错误")
        return pcm
    }
}
