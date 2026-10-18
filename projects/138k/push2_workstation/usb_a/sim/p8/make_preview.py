from pathlib import Path
from PIL import Image,ImageDraw
import sys,json,csv
out=Path(sys.argv[1]);images=[]
for p in sorted(out.glob('frame_*.rgb')):
 data=p.read_bytes();assert len(data)==1040*156*3
 im=Image.frombytes('RGB',(1040,156),data);images.append(im)
assert not any(images[0].getpixel((x,y))==(229,240,250) for x in range(576-48,1040) for y in range(8,24)), 'effect title repeated'
images[0].save(out/'effect_slide_rtl.gif',save_all=True,append_images=images[1:],duration=50,loop=0,optimize=False)
frames=[141,144,147,150,153,156,243]
montage=Image.new('RGB',(1040,180*len(frames)),(15,24,35));d=ImageDraw.Draw(montage)
for i,n in enumerate(frames):
 im=Image.frombytes('RGB',(1040,156),(out/f'frame_{n:03d}.rgb').read_bytes())
 montage.paste(im,(0,i*180+24));d.text((12,i*180+5),f'RTL simulation / video frame {n} (not an HDMI camera capture)',fill='white')
montage.save(out/'effect_slide_contact_sheet.png')
# Pixel evidence independent of motion registers: the green delay card must
# occupy many intermediate horizontal positions on entry, then end at x64.
lefts=[]
for n in range(3,54,3):
 im=Image.frombytes('RGB',(1040,156),(out/f'frame_{n:03d}.rgb').read_bytes())
 xs=[x+48 for x in range(1040) if im.getpixel((x,42))==(21,91,81)]
 assert xs,'missing moving card fill'
 lefts.append(min(xs)-2)
assert len(set(lefts))>=10 and lefts[-1]==64 and all(b<=a for a,b in zip(lefts,lefts[1:])),lefts
(out/'pixel_verification.json').write_text(json.dumps({'passed':True,'observed_delay_left_edges':lefts,'source':'actual dashboard pixels','hardware_tested':False},indent=2)+'\n')
print(out/'effect_slide_contact_sheet.png');print(out/'effect_slide_rtl.gif');print('pixel left edges',lefts)
