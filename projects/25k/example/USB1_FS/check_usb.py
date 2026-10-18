"""Check this example's USB1 12 Mbps CDC target; optionally verify binary echo."""
import sys
from tools.usb_check import main

if __name__ == '__main__':
    sys.argv[1:1] = ['--vid', 'FB9A', '--pid', 'FB9A', '--product', 'FPGA-USB-Serial',
                     '--expected-speed-mbps', '12',
                     '--chunk-sizes', '1,7,31,32,33,63,64']
    raise SystemExit(main())
