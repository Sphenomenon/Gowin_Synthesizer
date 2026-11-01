#!/usr/bin/env python3
"""Compare the HMI text lookup with a sealed pre-change dashboard in four states."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def function(text):
    start = text.index('    function automatic [23:0] decimal3(')
    end = text.index('    endfunction', start) + len('    endfunction')
    return text[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-dashboard', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'rtl/display_data/feedback_dashboard.v'
    reference = args.reference_dashboard.resolve()
    previous = reference.read_text()
    current = source.read_text()
    old, new = function(previous), function(current)
    assert current.replace(new, old, 1) == previous, 'Change outside decimal3'
    assert old != new, 'Reference is already the lookup implementation'
    bench = r'''`timescale 1ns/1ps
module tb;
OLD
NEW
reg [6:0] value;
reg [23:0] expected;
integer code, bit_index, digit, known=0, unknown=0;
initial begin
 for(code=0;code<16384;code=code+1)begin
  for(bit_index=0;bit_index<7;bit_index=bit_index+1)begin
   digit=(code>>(2*bit_index))&3;
   case(digit)
    0:value[bit_index]=1'b0;1:value[bit_index]=1'b1;
    2:value[bit_index]=1'bx;3:value[bit_index]=1'bz;
   endcase
  end
  #1;
  if(decimal3(value)!==original_decimal3(value))
   $fatal(1,"four-state mismatch value=%b got=%h expected=%h",value,decimal3(value),original_decimal3(value));
  if((^value)!==1'bx)begin
   expected={8'(48+value/100),8'(48+(value/10)%10),8'(48+value%10)};
   if(decimal3(value)!==expected)$fatal(1,"decimal text mismatch %0d",value);
   known=known+1;
  end else unknown=unknown+1;
 end
 if(known!=128 || unknown!=16256)$fatal(1,"coverage");
 $display("PASS decimal3: 128 binary and 16256 X/Z inputs, no latency");$finish;
end
endmodule
'''.replace('OLD', old.replace('decimal3', 'original_decimal3')).replace('NEW', new)
    variants = {
        'positive': bench,
        'wrong_volume_096': bench.replace('7\'d96: decimal3="096";', '7\'d96: decimal3="095";'),
        'lost_unknown_projection': bench,
    }
    # Removing the legacy default must be observable even though all binary
    # inputs are enumerated by the lookup.
    start = variants['lost_unknown_projection'].index('                default: begin')
    end = variants['lost_unknown_projection'].index('                end', start) + len('                end')
    variants['lost_unknown_projection'] = (bench[:start] +
        "                default: decimal3=24'hxxxxxx;" + bench[end:])
    runs = {}
    for name, text in variants.items():
        assert name == 'positive' or text != bench, 'Inert negative control'
        path = output / f'{name}.sv'
        path.write_text(text)
        executable = output / name
        compile_command = ['iverilog', '-g2012', '-s', 'tb', '-o', str(executable), str(path)]
        subprocess.run(compile_command, check=True, capture_output=True, text=True, timeout=60)
        result = subprocess.run(['vvp', str(executable)], capture_output=True, text=True, timeout=60)
        (output / f'{name}.log').write_text(result.stdout + result.stderr)
        assert (result.returncode == 0) == (name == 'positive'), f'Unexpected result: {name}'
        runs[name] = {'exit_code': result.returncode, 'expected_result': True}
    result = {
        'passed': True, 'binary_inputs': 128, 'unknown_inputs': 16256,
        'only_decimal_function_changed': True, 'pipeline_latency_changed': False,
        'source_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (source, reference, Path(__file__).resolve())},
        'runs': runs, 'hardware_tested': False,
        'scope': 'Actual decimal3 function, exact inverse against sealed dashboard; no routed timing claim'
    }
    (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
