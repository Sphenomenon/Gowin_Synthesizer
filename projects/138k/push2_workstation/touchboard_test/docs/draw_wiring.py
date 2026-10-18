#!/usr/bin/env python3
"""Render U4/J8 wiring from the frozen netlist and the bundled official PCB iBOM."""
from pathlib import Path
import json, math, re, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[3]
sys.path.insert(0,str(ROOT))
from netlist import connector_wiring
HTML=REPO/'Mega_138K/Doc/Mega_138K_60K/03_Designator_drawing/ibom_Tang_Mega_NEO_Dock_31004.html'
# The iBOM bundles LZString and a compressed JSON PCB. Evaluate only the codec,
# not the browser application, then decode its literal data.
s=HTML.read_text()
lz=s[s.index('var LZString'):].split('\n')[0]
b64=re.search(r'var pcbdata = JSON.parse\(LZString.decompressFromBase64\("([A-Za-z0-9+/=]+)"\)\)',s)[1]
js='const vm=require("vm"); const c={}; vm.createContext(c); vm.runInContext('+json.dumps(lz)+',c); process.stdout.write(c.LZString.decompressFromBase64('+json.dumps(b64)+'));'
pcb=json.loads(subprocess.run(['node','-'],input=js,check=True,capture_output=True,text=True).stdout)
u4,wiring=connector_wiring()
assert u4==dict(sda1=3,scl1=5,sda2=4,scl2=6,sda3=10,scl3=8,change_n=9,ws2812_din=7)
assert wiring==dict(sda1=12,scl1=10,sda2=11,scl2=9,sda3=5,scl3=7,change_n=6,ws2812_din=8)

W,H=2400,1950
BG='#F2F5F9'; INK='#172B45'; MUTED='#526277'
image=Image.new('RGB',(W,H),BG);draw=ImageDraw.Draw(image)
FONT='/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Regular.ttc'
BOLD='/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Bold.ttc'
fonts={}
def font(size,bold=False):
 key=(size,bold)
 if key not in fonts:fonts[key]=ImageFont.truetype(BOLD if bold else FONT,size,index=2)
 return fonts[key]
def text(x,y,t,size=32,fill=INK,bold=False,anchor=None):
 draw.text((x,y),t,font=font(size,bold),fill=fill,anchor=anchor)
def panel(box):draw.rounded_rectangle(box,radius=24,fill='white',outline='#DBE3EC',width=2)
def arrow(a,b,color=INK,width=5,head=16):
 draw.line([a,b],fill=color,width=width)
 ang=math.atan2(b[1]-a[1],b[0]-a[0]);p1=(b[0]-head*math.cos(ang)+head*.55*math.sin(ang),b[1]-head*math.sin(ang)-head*.55*math.cos(ang));p2=(b[0]-head*math.cos(ang)-head*.55*math.sin(ang),b[1]-head*math.sin(ang)+head*.55*math.cos(ang));draw.polygon([b,p1,p2],fill=color)
COLORS={'SDA1':'#1769D2','SCL1':'#1769D2','SDA2':'#0097A7','SCL2':'#0097A7','SDA3':'#7953C5','SCL3':'#7953C5','DIN':'#CC7B0B','CHANGE':'#2C9262','GND':'#536474','3V3':'#D84343','NC':'#A4ACB6'}
U4={1:'NC',2:'NC',3:'SDA1',4:'SDA2',5:'SCL1',6:'SCL2',7:'DIN',8:'SCL3',9:'CHANGE',10:'SDA3',11:'GND',12:'GND',13:'3V3',14:'3V3'}
J8={15-n:v for n,v in U4.items() if n>=3}
def pin(x,y,n,sig,r=36,square=False,size=34):
 c=COLORS[sig]
 if square:draw.rounded_rectangle((x-r,y-r,x+r,y+r),radius=6,fill=c)
 else:draw.ellipse((x-r,y-r,x+r,y+r),fill=c)
 text(x,y,str(n),size,'white',True,'mm')

text(70,40,'触摸板 U4 ↔ 138K 底板 J8 / PMOD1',58,bold=True)
text(74,120,'当前测试程序的接线顺序  ·  U4 是 2×7，J8 是 2×6  ·  U4 的 1、2 脚不接',34,MUTED)
panel((50,185,1320,990));panel((1350,185,2350,990));panel((50,1020,2350,1780))
text(85,214,'① 底板上找 J8（不是 J9）',42,bold=True)
text(85,275,'元件面俯视；位置取自工程自带的 NEO Dock 31004 位号图',27,MUTED)

# Faithful front-side geometry from the official iBOM. Keep its x/y view, so
# J9 is to the left of J8 and the PMOD edge is at the top of this drawing.
minx,miny,maxx,maxy=(pcb['edges_bbox'][k] for k in ('minx','miny','maxx','maxy'))
scale=6.5;ox=240;oy=355
def pt(p):return (ox+(p[0]-minx)*scale,oy+(p[1]-miny)*scale)
def rot(p,deg):
 a=math.radians(deg);return(p[0]*math.cos(a)-p[1]*math.sin(a),p[0]*math.sin(a)+p[1]*math.cos(a))
def shape(d,color):
 typ=d.get('type')
 width=max(1,round(d.get('width',d.get('thickness',.12))*scale))
 if typ=='segment':draw.line([pt(d['start']),pt(d['end'])],fill=color,width=width)
 elif typ=='circle':
  p=pt(d['start']);r=d['radius']*scale;draw.ellipse((p[0]-r,p[1]-r,p[0]+r,p[1]+r),outline=color,width=width)
 elif typ=='arc':
  p=pt(d['start']);r=d['radius']*scale;draw.arc((p[0]-r,p[1]-r,p[0]+r,p[1]+r),d['startangle'],d['endangle'],fill=color,width=width)
 elif typ=='polygon':
  for poly in d['polygons']:
   points=[]
   for v in poly:
    v=rot(v,-d.get('angle',0));points.append(pt([v[0]+d.get('pos',[0,0])[0],v[1]+d.get('pos',[0,0])[1]]))
   if d.get('filled'):draw.polygon(points,fill=color)
   else:draw.line(points+[points[0]],fill=color,width=width)
 elif 'svgpath' in d:
  # KiCad stroked text paths in this iBOM use only M and L commands.
  for command,x,y in re.findall(r'([ML])(-?[\d.]+),(-?[\d.]+)',d['svgpath']):
   p=pt((float(x),float(y)))
   if command=='L':draw.line([last,p],fill=color,width=width)
   last=p
# Approximate green PCB fill; precise official board outline is overlaid.
draw.rounded_rectangle((*pt((minx,miny)),*pt((maxx,maxy))),radius=12,fill='#DCEEE7',outline='#719D8B',width=3)
for f in pcb['footprints']:
 if f['layer']!='F':continue
 bb=f['bbox'];points=[]
 for dx,dy in [(0,0),(bb['size'][0],0),tuple(bb['size']),(0,bb['size'][1])]:
  p=rot((bb['relpos'][0]+dx,bb['relpos'][1]+dy),-bb['angle']);points.append(pt((bb['pos'][0]+p[0],bb['pos'][1]+p[1])))
 draw.polygon(points,fill='#BBD5CA',outline='#8CAC9E')
 for p in f['pads']:
  if 'F' not in p['layers']:continue
  x,y=pt(p['pos']);sx,sy=p['size'];a=abs(p.get('angle',0))%180
  if abs(a-90)<.1:sx,sy=sy,sx
  rx,ry=sx*scale/2,sy*scale/2
  if p['shape']=='rect':draw.rectangle((x-rx,y-ry,x+rx,y+ry),fill='#C8B881')
  else:draw.ellipse((x-rx,y-ry,x+rx,y+ry),fill='#C8B881')
  if p.get('drillsize'):
   r=p['drillsize'][0]*scale/2;draw.ellipse((x-r,y-r,x+r,y+r),fill='#EFF7F3')
for d in pcb['drawings']['silkscreen']['F']:shape(d,'#537365')
for d in pcb['edges']:shape(d,'#557869')
# Highlight complete socket housings at their actual native positions.
for ref,color in [('J9','#6C7C8E'),('J8','#E34D4D')]:
 f=next(f for f in pcb['footprints'] if f['ref']==ref);bb=f['bbox'];points=[]
 for dx,dy in [(0,0),(bb['size'][0],0),tuple(bb['size']),(0,bb['size'][1])]:
  r=rot((bb['relpos'][0]+dx,bb['relpos'][1]+dy),-bb['angle']);points.append(pt((bb['pos'][0]+r[0],bb['pos'][1]+r[1])))
 draw.line(points+[points[0]],fill=color,width=6)
 xs=[p[0] for p in points];ys=[p[1] for p in points]
 labelx=sum(xs)/4
 text(labelx+(16 if ref=='J8' else -16),330,ref+(' / PMOD1' if ref=='J8' else ' / PMOD0'),25,color,True,'mm')
 arrow((labelx,351),(labelx,min(ys)-7),color,3,10)
# Port landmarks and the J8 pin1 pad.
for ref,label in [('J18','USB-A'),('J12','RJ45'),('J29','HDMI')]:
 f=next(f for f in pcb['footprints'] if f['ref']==ref);x,y=pt(f['bbox']['pos']);text(x,y+35,label,23,INK,True,'mm')
f=next(f for f in pcb['footprints'] if f['ref']=='J8');p1=next(p for p in f['pads'] if p.get('pin1'));x,y=pt(p1['pos'])
draw.rectangle((x-9,y-9,x+9,y+9),outline='#D84343',width=4)
text(85,942,'红框 = 本次使用的 J8    灰框 = 旁边的 J9',29,MUTED)

text(1388,214,'② J8 引脚放大：同一俯视方向',39,bold=True)
text(1390,276,'显示 PCB 焊脚位置，不是迎面看插口的视图',28,MUTED)
text(1395,337,'← 靠 J9 / SDA 端',30,'#1769D2',True)
text(2310,337,'3.3V 电源端 →',30,'#D84343',True,'ra')
arrow((1410,410),(2298,410),'#7B8C9D',3,12)
text(1850,370,'靠板边',28,MUTED,anchor='mm')
xs=[1440+i*165 for i in range(6)]
for i,x in enumerate(xs):
 top=12-2*i;bottom=11-2*i
 pin(x,495,top,J8[top],r=37,size=35)
 pin(x,685,bottom,J8[bottom],r=37,square=(bottom==1),size=35)
 for y,n in [(554,top),(744,bottom)]:
  sig=J8[n];name='+3.3V' if sig=='3V3' else sig
  text(x,y,name,26,COLORS[sig],True,'mm')
text(1850,809,'靠板内',28,MUTED,anchor='mm')
text(1395,865,'方框中的 1 = J8 的 1 脚（方形焊盘标记）',27,MUTED)
text(1395,910,'SDA1 = 12 脚；SDA2 = 11 脚',31,'#1769D2',True)
text(1395,951,'DIN = WS2812_DIN；CHANGE = CHANGE12',24,MUTED)

text(85,1045,'③ 逐针接线：相同颜色与信号一一对应',40,bold=True)
text(85,1107,'下面按针号分组，不表示 U4 的实物朝向。U4 编号请从实物 1 脚标记开始确认。',29,MUTED)
centers=[215+i*315 for i in range(7)]
text(85,1208,'U4',32,bold=True)
text(85,1536,'J8',32,bold=True)
for i,cx in enumerate(centers):
 n1,n2=2*i+1,2*i+2
 for dx,n in [(-56,n1),(56,n2)]:
  x=cx+dx;sig=U4[n]
  pin(x,1235,n,sig,r=39,square=(n==1),size=35)
  if n<=2:
   draw.line((x,1292,x,1350),fill=COLORS['NC'],width=5)
   draw.line((x-15,1350,x+15,1380),fill=COLORS['NC'],width=5)
   draw.line((x+15,1350,x-15,1380),fill=COLORS['NC'],width=5)
  else:
   j=15-n
   arrow((x,1290),(x,1478),COLORS[sig],5,15)
   draw.rounded_rectangle((x-62,1360,x+62,1403),radius=8,fill='white')
   text(x,1381,'+3.3V' if sig=='3V3' else sig,24,COLORS[sig],True,'mm')
   pin(x,1537,j,sig,r=39,size=35)
 if i==0:
  text(cx,1450,'NC / 悬空',25,MUTED,True,'mm')
  text(cx,1588,'没有 J8 对应脚',24,MUTED,anchor='mm')
 else:
  text(cx,1632,f'U4 {n1}/{n2} → J8 {15-n1}/{15-n2}',25,MUTED,anchor='mm')
text(100,1715,'电源核对：U4 13/14 → J8 2/1（3.3V）   |   U4 11/12 → J8 4/3（GND）',34,'#AA3333',True)
text(75,1820,'位置参考：工程内 NEO Dock 31004 官方位号图；J8/PMOD1 针号与 31005 原理图第 19 页核对。',26,MUTED)
text(75,1866,'线序来自触摸板网表与当前测试位流；若实物位置与参考图不同，以 J8 丝印、1 脚标记和针号为准。',26,MUTED)
OUT=ROOT/'docs/U4_J8_wiring.png'
image.save(OUT,optimize=True,dpi=(200,200))
image.save(OUT.with_suffix('.pdf'),'PDF',resolution=180)
print(OUT)
