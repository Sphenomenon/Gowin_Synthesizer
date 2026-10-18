import json,math,pathlib
P=pathlib.Path(__file__).resolve().parent
D=json.loads((P/'parsed.json').read_text());R=D[67]['records'];FP={d['header']['uuid']:d for d in D if d['header']['docType']=='FOOTPRINT'}
attrs={};pn={}
for l,a,b in R:
 if a['type']=='ATTR':attrs.setdefault(b.get('parentId'),{})[b['key']]=b['value']
 if a['type']=='PAD_NET':q=json.loads(a['id']);pn[(q[1],q[3])]=b['padNet']
sh=[];pads=[]
def rot(x,y,a):
 t=math.radians(a);return x*math.cos(t)-y*math.sin(t),x*math.sin(t)+y*math.cos(t)
def capsule(p,q,r,net,layer,name,line):return {'kind':'cap','p':p,'q':q,'r':r,'net':net,'layer':layer,'name':name,'line':line}
for l,a,b in R:
 typ=a['type']
 if typ=='LINE' and b['layerId'] in (1,2):sh.append(capsule((b['startX'],b['startY']),(b['endX'],b['endY']),b['width']/2,b['netName'],b['layerId'],a['id'],l))
 if typ=='VIA':
  for layer in (1,2):sh.append(capsule((b['centerX'],b['centerY']),(b['centerX'],b['centerY']),b['viaDiameter']/2,b['netName'],layer,a['id'],l))
 if typ=='COMPONENT':
  cid=a['id'];at=attrs[cid];fp=FP.get(at.get('Footprint'))
  if not fp:continue
  for pl,pa,pb in fp['records']:
   if pa['type']!='PAD':continue
   pad=pb['defaultPad'];angle=pb.get('padAngle',0)+b['angle'];x,y=rot(pb['centerX'],pb['centerY'],b['angle']);x+=b['x'];y+=b['y'];net=pn.get((cid,pa['id']),'');name=at.get('Designator',cid)+'.'+pb['num'];layers=(1,2) if pb['layerId']==12 else (b['layerId'],)
   w,h=pad.get('width',0),pad.get('height',0);pt=pad['padType']
   if pt not in ('RECT','OVAL','ROUND'):continue
   for ly in layers:
    s={'net':net,'layer':ly,'name':name,'line':l,'source_pad_line':pl,'center':[x,y]}
    if pt=='RECT':
     poly=[rot(u,v,angle) for u,v in ((-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2))];s.update(kind='poly',poly=[(u+x,v+y) for u,v in poly])
    else:
     ax,ay=rot(max(w-h,0)/2,max(h-w,0)/2,angle);s.update(kind='cap',p=(x-ax,y-ay),q=(x+ax,y+ay),r=min(w,h)/2)
    sh.append(s);pads.append(s)
def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def pd(p,a,b):
 dx=b[0]-a[0];dy=b[1]-a[1];t=0 if dx*dx+dy*dy<1e-20 else max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)));return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)
def sd(a,b,c,d):
 ab1=cross(a,b,c);ab2=cross(a,b,d);cd1=cross(c,d,a);cd2=cross(c,d,b)
 if ab1*ab2<0 and cd1*cd2<0:return 0
 return min(pd(a,c,d),pd(b,c,d),pd(c,a,b),pd(d,a,b))
def inside(p,poly):
 v=False
 for a,b in zip(poly,poly[1:]+poly[:1]):
  if (a[1]>p[1])!=(b[1]>p[1]) and p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:v=not v
 return v
def edges(s):return list(zip(s['poly'],s['poly'][1:]+s['poly'][:1]))
def distance(s,t):
 if s['kind']=='cap' and t['kind']=='cap':return sd(s['p'],s['q'],t['p'],t['q'])-s['r']-t['r']
 if s['kind']=='poly' and t['kind']=='cap':s,t=t,s
 if s['kind']=='cap':
  if inside(s['p'],t['poly']) or inside(s['q'],t['poly']):return -s['r']
  return min(sd(s['p'],s['q'],a,b) for a,b in edges(t))-s['r']
 if inside(s['poly'][0],t['poly']) or inside(t['poly'][0],s['poly']):return -1
 return min(sd(a,b,c,d) for a,b in edges(s) for c,d in edges(t))
DP={'USB2_HS_DP','$1N25'};DM={'USB2_HS_DM','$1N26'};us=[s for s in sh if s['net'] in DP|DM]
results=[]
for s in us:
 for t in sh:
  if t['layer']!=s['layer'] or t['net'] in (DP if s['net'] in DP else DM):continue
  d=distance(s,t)
  if d<10:results.append({'gap_mil':d,'gap_mm':d*0.0254,'a':s['name'],'a_line':s['line'],'a_net':s['net'],'b':t['name'],'b_line':t['line'],'b_net':t['net'],'layer':s['layer']})
results.sort(key=lambda x:x['gap_mil']);out={'scope':'explicit lines, vias and footprint pads; does not include poured copper or arc records','usb_pads':[{k:v for k,v in p.items() if k!='poly'} for p in pads if p['net'] in DP|DM], 'nearest_foreign_copper':results[:50], 'shorts':[r for r in results if r['gap_mil']<-0.01], 'min_dp_dm':next(r for r in results if (r['a_net'] in DP and r['b_net'] in DM) or (r['a_net'] in DM and r['b_net'] in DP))}
(P/'geometry_result.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k!='usb_pads'},indent=2))
def poly_path(path):
 pts=[(path[0]*10,path[1]*10)];i=2;mode='L'
 while i<len(path):
  if isinstance(path[i],str):mode=path[i];i+=1
  if mode=='L':
   pts.append((path[i]*10,path[i+1]*10));i+=2
  elif mode=='ARC':
   theta=math.radians(path[i]);end=(path[i+1]*10,path[i+2]*10);i+=3
   start=pts[-1];dx=end[0]-start[0];dy=end[1]-start[1]
   if abs(theta)<1e-10 or math.hypot(dx,dy)<1e-10:pts.append(end);continue
   cx=(start[0]+end[0])/2-dy/(2*math.tan(theta/2));cy=(start[1]+end[1])/2+dx/(2*math.tan(theta/2));rad=math.hypot(start[0]-cx,start[1]-cy);base=math.atan2(start[1]-cy,start[0]-cx);n=max(1,math.ceil(abs(theta)/(2*math.acos(max(-1,min(1,1-.0005/max(rad,.0005)))))))
   pts.extend((cx+rad*math.cos(base+theta*k/n),cy+rad*math.sin(base+theta*k/n)) for k in range(1,n));pts.append(end);mode='L'
  else:raise ValueError(mode)
 return pts
pours={a['id']:b for l,a,b in R if a['type']=='POUR'};fills=[]
for l,a,b in R:
 if a['type']!='POURED':continue
 pid=json.loads(a['id'])[1]
 if pid not in pours:continue
 pp=pours[pid]
 for f in b['pourFill']:
  contours=[poly_path(p) for p in f['path']]
  fills.append({'contours':contours,'net':pp['netName'],'layer':pp['layerId'],'id':f['id'],'line':l})
print('Active fill count',len(fills),'segments',sum(sum(len(p) for p in f['contours']) for f in fills))
def filldist(s,f):
 cont=f['contours'];points=[s['p'],s['q']] if s['kind']=='cap' else s['poly']
 if any(sum(inside(p,c) for c in cont)%2 for p in points):return -1
 ds=1e99
 if s['kind']=='cap':
  for c in cont:
   ds=min(ds,min(sd(s['p'],s['q'],a,b) for a,b in zip(c,c[1:]+c[:1]))-s['r'])
 else:
  for c in cont:
   ds=min(ds,min(sd(a,b,c1,d) for a,b in edges(s) for c1,d in zip(c,c[1:]+c[:1])))
 return ds
pour_gaps=[]
for s in us:
 for f in fills:
  if s['layer']!=f['layer'] or s['net']==f['net']:continue
  dd=filldist(s,f)
  if dd<10:pour_gaps.append({'gap_mil':dd,'a':s['name'],'a_net':s['net'],'b':f['id'],'b_net':f['net'],'b_line':f['line'],'layer':s['layer']})
pour_gaps.sort(key=lambda p:p['gap_mil']);out['poured_copper']={'arc_sagitta_bound_mil':.0005,'gaps':pour_gaps,'shorts':[p for p in pour_gaps if p['gap_mil']<-.01]};(P/'geometry_result.json').write_text(json.dumps(out,indent=2));print('POUR NEAREST',json.dumps(pour_gaps[:10],indent=2))
# Component-wise connected groups within explicit native copper, with vias joining both layers.
for net in sorted(DP|DM|{'VDD18','$1N107','$1N87'}):
 ss=[s for s in sh if s['net']==net];parent=list(range(len(ss)))
 def find(x):
  while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
  return x
 for i,s in enumerate(ss):
  for j,t in enumerate(ss[:i]):
   if s['layer']==t['layer'] and distance(s,t)<=.01 or (s['name']==t['name'] and s['line']==t['line'] and s['kind']=='cap' and s['p']==s['q']):parent[find(i)]=find(j)
 groups={}
 for i,s in enumerate(ss):groups.setdefault(find(i),[]).append(s['name'])
 print('CONNECTED',net,len(groups),list(groups.values()))
for net in DP|DM:
 best=(1e99,None,None)
 for s in [u for u in us if u['net']==net]:
  for f in fills:
   if s['layer']==f['layer']:
    dd=filldist(s,f)
    if dd<best[0]:best=(dd,s['name'],f['id'])
 print('MINPOUR',net,best)
