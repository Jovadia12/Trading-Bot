import json, re, numpy as np, soundfile as sf
D=json.load(open('durs.json'));TXT={}
for line in open('../tts/nx/vo.py'):
    m=re.match(r'\s*\("(v\d)","(.*)"\),?\s*$',line)
    if m: TXT[m.group(1)]=m.group(2)
START={'v1':1.0,'v2':18.4,'v3':32.4,'v4':43.6,'v5':54.0,'v6':65.0,'v7':78.2}
keys=sorted(START)
for a,b in zip(keys,keys[1:]): assert START[a]+D[a]<START[b]-.2,(a,b)
def kw(k,w): i=TXT[k].index(w); return round(START[k]+D[k]*i/len(TXT[k]),3)
DUR=85.0
CLIPS={n:[0,1] for n in ['home','shop','catalog','coa','account']}
one=lambda: [[0,0]]
SCENES=[dict(id='home',clip='home',a=-1,b=31.9,x=.6,src=one()),
 dict(id='shop',clip='shop',a=31.9,b=43.0,x=.6,src=one()),
 dict(id='catalog',clip='catalog',a=43.0,b=53.4,x=.7,src=one(),dy=120),
 dict(id='coa',clip='coa',a=53.4,b=64.4,x=.6,src=one()),
 dict(id='account',clip='account',a=64.4,b=DUR+2,x=.6,src=one())]
def H(scene,r,t,label,hold=1.6): return dict(scene=scene,r=r,t=t,label=label,hold=hold)
HL=[H('home',[2,124,1904,164],kw('v2','announcement'),'Announcement banner',1.5),
    H('home',[393,178,565,224],kw('v2','logo'),'Logo',1.0),
    H('home',[592,178,880,224],kw('v2','search field'),'Search',1.1),
    H('home',[895,182,1360,220],kw('v2','four category'),'Category links',1.3),
    H('home',[1368,184,1443,218],kw('v2','Affiliates link'),'Affiliates',1.0),
    H('home',[1450,182,1525,220],kw('v2','account and cart'),'Account · Cart',1.2),
    H('home',[757,711,1148,775],kw('v2','hero section'),'Hero buttons',2.2),
    H('shop',[820,340,1085,405],kw('v3','The Archive'),'Page title',1.3),
    H('shop',[440,636,1466,690],kw('v3','search field'),'Search',1.2),
    H('shop',[440,706,1424,801],kw('v3','category filter'),'Category filters',1.5),
    H('shop',[452,838,1172,925],kw('v3','price slider'),'Max price',1.2),
    H('shop',[1182,842,1445,921],kw('v3','sort menu'),'Sort',1.0),
    H('shop',[440,972,570,996],kw('v3','product count'),'Result count',1.4),
    H('catalog',[443,302,943,920],kw('v4','Each card'),'Product card',1.4),
    H('catalog',[459,795,927,850],kw('v4','name, price'),'Name · price · category',1.6),
    H('catalog',[458,860,928,906],kw('v4','View Options'),'Card button',1.2),
    H('catalog',[2,124,1904,192],kw('v4','header stays'),'Fixed header',1.8),
    H('coa',[840,265,1066,360],kw('v5','COA Library'),'Section title',1.5),
    H('coa',[727,461,1179,515],kw('v5','search field'),'Search',1.6),
    H('coa',[441,551,1464,962],kw('v5','grid of'),'Expandable entries',2.4),
    H('account',[749,428,861,477],kw('v6','Affiliate tab'),'Affiliate tab',1.3),
    H('account',[523,503,1012,548],kw('v6','five sub-tabs'),'Sub-tabs',1.3),
    H('account',[523,569,1383,659],kw('v6','summary metrics'),'Summary metrics',1.3),
    H('account',[523,675,1383,779],kw('v6','three status'),'Status cards',1.3),
    H('account',[523,795,1383,1033],kw('v6','panel with'),'Affiliate code panel',2.2)]
CAM=[[0,1,960,601],[2.5,1,960,601],[17.0,1.12,960,560],
 [19.5,1.4,960,420],[27.5,1.4,1000,440],[29.5,1.35,955,640],[31.9,1.3,955,620],
 [33.5,1.4,955,640],[42.5,1.4,955,760],
 [44.5,1.18,955,600],[49.0,1.22,955,640],[51.5,1.35,960,420],[53.4,1.3,960,600],
 [55.5,1.4,955,480],[61.5,1.4,955,720],[64.4,1.3,955,601],
 [66.5,1.45,955,560],[72.0,1.45,955,700],[76.5,1.3,955,700],[77.6,1,960,601],[DUR,.98,960,601]]
WP=[(2.0,1300,860,0),(kw('v2','logo')-.1,480,201,1.2),(kw('v2','search field')-.1,700,201,.6),(kw('v2','four category')-.1,1040,201,.7),
    (kw('v2','Affiliates link')-.1,1405,201,.6),(kw('v2','account and cart')-.1,1506,201,.5),(30.9,855,742,1.4),
    (kw('v3','category filter'),760,730,1.0),(kw('v3','price slider'),1000,888,.8),(kw('v3','sort menu'),1320,896,.7),
    (kw('v4','Each card')+.2,945,560,1.0),(kw('v4','View Options')+.1,693,883,.8),(52.6,476,156,1.4),
    (kw('v5','search field')+.2,900,488,1.0),(kw('v5','grid of')+.6,1000,700,1.0),(63.7,1533,157,1.6),
    (kw('v6','Affiliate tab')+.1,805,452,1.0),(kw('v6','five sub-tabs'),688,526,.7),(kw('v6','panel with')+.3,1316,898,1.2)]
MOVES=[]
for (t0,x0,y0,_),(t1,x1,y1,tr) in zip(WP,WP[1:]): MOVES.append([round(t1-tr,3),round(t1,3),[x0,y0],[x1,y1]])
CLICKS=[[855,742,31.1],[476,156,52.8],[1533,157,63.9],[805,452,kw('v6','Affiliate tab')+.2]]
CVIS=[[17.8,76.6]]
S=dict(pull=76.5,end=77.6,e1=0,e2=0,e3=0)
CHIPS=[[18.2,31.9,'1 · Homepage'],[32.2,43.0,'2 · Shop — categories & filters'],[43.3,53.4,'3 · Product catalog'],[53.7,64.4,'4 · COA Library'],[64.7,77.3,'5 · Affiliate-program section']]
CAPS=[]
for k in keys:
    txt=TXT[k];st,du=START[k],D[k]
    parts=re.split(r'(?<=[.:,?])\s+',txt);chunks=[];cur=''
    for p in parts:
        if cur and len(cur)+len(p)>64: chunks.append(cur);cur=p
        else: cur=(cur+' '+p).strip()
    chunks.append(cur);tot=sum(len(c) for c in chunks);acc=0
    for c in chunks:
        a=st+du*acc/tot;acc+=len(c);b=st+du*acc/tot;CAPS.append([round(a,3),round(b+.08,3),c])
open('timeline.js','w').write('const TL='+json.dumps(dict(DUR=DUR,CLIPS=CLIPS,SCENES=SCENES,HL=HL,CAM=CAM,S=S,CHIPS=CHIPS,CAPS=CAPS,MOVES=MOVES,CLICKS=CLICKS,CVIS=CVIS))+';')
# audio: calm neutral bed
SR=48000;N=int(DUR*SR);t=np.arange(N)/SR;rng=np.random.default_rng(2)
mid=lambda m:440*2**((m-69)/12)
def env(n,a,r):
    e=np.ones(n);ai=int(a*SR);ri=int(r*SR)
    if ai:e[:ai]=np.linspace(0,1,ai)
    if ri:e[-ri:]*=np.linspace(1,0,ri)
    return e
CH=[[48,55,60,64,67],[45,52,57,60,64],[41,48,53,57,60],[43,50,55,59,62]];cl=5.0;mus=np.zeros(N)
for ci in range(int(DUR/cl)+1):
    s0=int(ci*cl*SR);n=min(int((cl+1.5)*SR),N-s0)
    if n<=0:break
    tt=np.arange(n)/SR;pad=np.zeros(n)
    for m in CH[ci%4]:
        f=mid(m+12)
        for det in(-.06,.06):pad+=np.sin(2*np.pi*f*2**(det/12)*tt)+.15*np.sin(2*np.pi*2*f*tt)
    mus[s0:s0+n]+=pad*env(n,1.6,1.8)*.013+np.sin(2*np.pi*mid(CH[ci%4][0]-12)*tt)*env(n,.5,1.5)*.035
    for j in range(8):
        ts=ci*cl+j*cl/8;si=int(ts*SR);nn=min(int(.7*SR),N-si)
        if nn<=0 or ts<3:continue
        tn=np.arange(nn)/SR;mus[si:si+nn]+=np.sin(2*np.pi*mid(CH[ci%4][[2,3,4,3,1,3,4,2][j]]+24)*tn)*np.exp(-tn*6)*.006
mus*=np.clip(t/3,0,1)*np.clip((DUR-t)/3,0,1)
vo=np.zeros(N)
for k in keys:
    a,sr=sf.read(f'{k}.wav');a=a if a.ndim==1 else a.mean(1)
    up=np.interp(np.arange(int(len(a)*SR/sr))*sr/SR,np.arange(len(a)),a);si=int(START[k]*SR);vo[si:si+len(up)]+=up[:N-si]
vo*=.9/np.abs(vo).max()
act=np.zeros(N)
for k in keys: act[int((START[k]-.15)*SR):int((START[k]+D[k]+.2)*SR)]=1
duck=np.convolve(act,np.ones(int(.35*SR))/int(.35*SR),'same');mus*=1-.5*duck
sfx=np.zeros(N)
def add(ts,x):
    si=int(ts*SR);n=min(len(x),N-si);sfx[si:si+n]+=x[:n]
for c in CLICKS:
    n=int(.05*SR);tn=np.arange(n)/SR;add(c[2],(rng.standard_normal(n)*np.exp(-tn*400)*.5+np.sin(2*np.pi*2400*tn)*np.exp(-tn*160))*.2)
for sc in SCENES[1:]:
    n=int(.7*SR);x=rng.standard_normal(n);y=np.convolve(x,np.ones(40)/40,'same')-np.convolve(x,np.ones(400)/400,'same')
    add(sc['a']-.25,y*np.sin(np.pi*np.arange(n)/n)**2*.15)
mix=vo+mus+sfx;mix/=np.abs(mix).max()/.89
sf.write('audio.wav',np.stack([mix,mix],1),SR,subtype='PCM_16');print('ok')
