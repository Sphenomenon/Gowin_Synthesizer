"""Exercise the actual W key predicates, including unknowns and missing bits."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_w_identity_bytes import MANIFEST,normalize


class IdentityBytes(unittest.TestCase):
    def test_native_four_state_and_omitted_bits(self):
        manifest=json.loads((ROOT/MANIFEST).read_text())
        fragments={}
        for row in manifest['sources']:
            text=(ROOT/row['source']).read_text()
            parent=normalize(row['source'],text)
            self.assertEqual(hashlib.sha256(parent.encode()).hexdigest(),row['parent_sha256'])
            fragments[row['source']]=row['edits'][0]['after']
        cnn=fragments['rtl/music/workstation_task3_cnn_stream_w.sv']
        recording=fragments['rtl/workstation/workstation_task3_record_ingress.sv']
        declarations='''
reg [127:0] a,b,c,d;
reg cancel_valid_i,frame_44k1_i,frame_error_i;
wire [191:0] frame_i={a,64'd0},seal_i={c,64'd0};
wire [127:0] identity=b,cancel_i=d;
wire [31:0] frame_session_i=a[127:96],frame_generation_i=a[95:64];
wire [31:0] frame_physical_epoch_i=a[63:32],frame_sequence_i=a[31:0];
wire [31:0] session_o=b[127:96],generation_o=b[95:64];
wire [31:0] physical_epoch_o=b[63:32],expected_sequence=b[31:0];
'''
        # Both production fragments are in independent scopes, as in the board.
        harness='''
integer checks=0,seed=32'h317a0942;
task check;
begin
 #1;
 if(cnn.frame_match !== (a==b) || cnn.seal_match !== (c==b) ||
    cnn.cancel_match !== (cancel_valid_i && d==b) ||
    recording.identity_bad !== (a[127:96]!=b[127:96] || a[95:64]!=b[95:64] ||
      a[63:32]!=b[63:32] || a[31:0]!=b[31:0] || frame_44k1_i || frame_error_i))
   $fatal(1,"key predicate mismatch at check %0d",checks);
 checks=checks+1;
end endtask
integer trial,bit_index,mode;
initial begin
 cancel_valid_i=1;frame_44k1_i=0;frame_error_i=0;
 for(trial=0;trial<32;trial=trial+1)begin
   b={$random(seed),$random(seed),$random(seed),$random(seed)};
   a=b;c=b;d=b;check;
   for(bit_index=0;bit_index<128;bit_index=bit_index+1)begin
     a=b;c=b;d=b;
     a[bit_index]=!b[bit_index];c[bit_index]=!b[bit_index];d[bit_index]=!b[bit_index];check;
     a=b;c=b;d=b;
     a[bit_index]=1'bx;c[bit_index]=1'bx;d[bit_index]=1'bx;check;
     a[bit_index]=1'bz;c[bit_index]=1'bz;d[bit_index]=1'bz;check;
     // A known difference must dominate a different byte's unknown.
     a[(bit_index+8)%128]=!b[(bit_index+8)%128];
     c[(bit_index+8)%128]=!b[(bit_index+8)%128];
     d[(bit_index+8)%128]=!b[(bit_index+8)%128];check;
   end
 end
 for(mode=0;mode<16;mode=mode+1)begin
   a='x;b='x;c='z;d='z;
   cancel_valid_i=mode[0]?1'bx:mode[1];
   frame_44k1_i=mode[2]?1'bz:mode[3];frame_error_i=mode[3]?1'bx:mode[0];check;
 end
 $display("PASS actual W identity predicates %0d four-state comparisons",checks);$finish;
end
'''
        def program(cnn_fragment,record_fragment):
            return ('module tb;\n'+declarations+'\nif(1)begin:cnn\n'+cnn_fragment+
                '\nend\nif(1)begin:recording\n'+record_fragment+'\nend\n'+harness+'\nendmodule\n')
        cases=[('native',cnn,recording,True),
               ('CNN-last-byte-omitted',cnn.replace('task_key_byte<16','task_key_byte<15'),recording,False),
               ('recording-last-byte-omitted',cnn,recording.replace('frame_key_byte<16','frame_key_byte<15'),False)]
        with tempfile.TemporaryDirectory(prefix='task3-w-identity-')as tmp:
            p=Path(tmp)
            for name,cf,rf,expected in cases:
                source=p/(name+'.sv');binary=p/(name+'.vvp');source.write_text(program(cf,rf))
                subprocess.run(['iverilog','-g2012','-s','tb','-o',str(binary),str(source)],check=True,capture_output=True,text=True)
                result=subprocess.run(['vvp',str(binary)],capture_output=True,text=True)
                self.assertEqual(result.returncode==0,expected,result.stdout+result.stderr)
                print(name,result.stdout.strip())


if __name__=='__main__':unittest.main()
