"""Check this example's 480 Mbps CDC target; pass --loopback to exercise data."""
import sys
from tools.usb_check import main

if __name__ == '__main__':
    sys.argv[1:1] = ['--vid', 'FB9A', '--pid', 'FB9B', '--product', 'GW25K-USB-HS',
                     '--expected-speed-mbps', '480',
                     '--chunk-sizes', '1,31,64,511,512,513,1024']
    raise SystemExit(main())
