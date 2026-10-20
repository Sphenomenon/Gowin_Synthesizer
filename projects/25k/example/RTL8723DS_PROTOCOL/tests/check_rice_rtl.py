"""Compare real encoder RTL to independent byte/bit reference vectors."""
import sys,random,struct,subprocess,wave,json,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from pcm_lossless import encode,decode
parser=argparse.ArgumentParser();parser.add_argument('--second',action='store_true');parser.add_argument('--output',type=Path,default=ROOT/'reports/speed18_20261020/encoder_legacy');args=parser.parse_args()
OUT=args.output;OUT.mkdir(parents=True,exist_ok=True)
STAGE=Path('/private/tmp/gw25k-rice-vectors');STAGE.mkdir(exist_ok=True)
with wave.open(str(ROOT/'audio/test_tone_1s.wav')) as f:tone=f.readframes(f.getnframes())
rng=random.Random(0x2517)
cases=[('tone_'+str(i),tone[i:i+8112]) for i in range(0,len(tone),8112)]
cases += [('silence',bytes(8112)),('extremes',struct.pack('<hhhh',-32768,32767,32767,-32768)*1014),('noise',rng.randbytes(8112)),('ramp',b''.join(struct.pack('<HH',i*13&65535,32760+i*29&65535) for i in range(2028)))]
cases += [('random_'+str(n),rng.randbytes(n)) for n in (4,8,20,460,972,3600,7888)]
for seed in (17,18,19):
    walk_rng=random.Random(seed);last=[32760,32780];pcm=bytearray()
    for i in range(4056):
        ch=i&1;last[ch]=(last[ch]+walk_rng.randint(-1000,1000))&65535;pcm.extend(struct.pack('<H',last[ch]))
    cases.append(('random_walk_'+str(seed),bytes(pcm)))

bench='''`timescale 1ns/1ps
module tb_rice;
reg clk=0;always #5 clk=~clk;
reg resetn=0,enable=1,start=0;reg [12:0] pcm_length;
wire [12:0] sample_addr,write_addr,encoded_length;wire [7:0] write_data;
wire write_valid,done,use_rice,use_second;reg allow_second=SECOND;reg [15:0] sample_data;reg [7:0] pcm[0:8111],expected[0:8111];
integer expected_length,expected_mode,count=0,cycles=0;
ble_rice_encoder dut(.*);
always @(posedge clk) sample_data<={pcm[sample_addr+1],pcm[sample_addr]};
always @(negedge clk) begin
 if(write_valid)begin
  if(write_addr!==count || write_data!==expected[count])$fatal(1,"encoded byte %0d addr=%0d got=%h expected=%h",count,write_addr,write_data,expected[count]);
  count=count+1;
 end
 cycles=cycles+1;if(cycles>300000)$fatal(1,"timeout");
end
initial begin
 $readmemh("INPUT",pcm);$readmemh("EXPECTED",expected);
 pcm_length=PCM_SIZE;expected_length=ENC_SIZE;expected_mode=MODE;
 repeat(3)@(negedge clk);resetn=1;@(negedge clk);start=1;@(negedge clk);start=0;
 wait(done);@(negedge clk);
 if(use_second!==(expected_mode==11) || use_rice!==(expected_mode!=0) || encoded_length!=expected_length || count!=(expected_mode!=0 ? expected_length : 0))$fatal(1,"result mode=%d len=%d count=%d",use_rice,encoded_length,count);
 $display("PASS encoder bytes=%0d cycles=%0d",encoded_length,cycles);$finish;
end
endmodule
'''
results=[]
for name,pcm in cases:
 mode,coded=encode(pcm,allow_second=args.second);assert decode(coded,len(pcm),mode,allow_second=args.second)==pcm
 inp=OUT/(name+'.pcm.mem');exp=OUT/(name+'.rice.mem');tb=OUT/(name+'.sv');exe=OUT/(name+'.vvp')
 inp.write_text('\n'.join(f'{x:02x}' for x in pcm)+'\n');exp.write_text('\n'.join(f'{x:02x}' for x in coded)+'\n')
 (STAGE/'pcm.mem').write_bytes(inp.read_bytes());(STAGE/'expected.mem').write_bytes(exp.read_bytes())
 text=bench.replace('INPUT',str(STAGE/'pcm.mem')).replace('EXPECTED',str(STAGE/'expected.mem')).replace('PCM_SIZE',str(len(pcm))).replace('ENC_SIZE',str(len(coded))).replace('MODE',str(mode)).replace('SECOND',str(int(args.second)));tb.write_text(text)
 subprocess.run(['iverilog','-g2012','-s','tb_rice','-o',str(exe),str(tb),str(ROOT/'rtl/ble_recording.v')],check=True)
 r=subprocess.run(['vvp',str(exe)],text=True,capture_output=True,errors="replace");(OUT/(name+'.log')).write_text(r.stdout+r.stderr)
 if r.returncode or 'PASS encoder' not in r.stdout:raise RuntimeError(name+':'+r.stdout+r.stderr)
 results.append(dict(case=name,pcm=len(pcm),encoded=len(coded),mode=mode))
 print(name,mode,len(coded),flush=True)
(OUT/'result.json').write_text(json.dumps(dict(passed=True,cases=results),indent=2)+'\n')
