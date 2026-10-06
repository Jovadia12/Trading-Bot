import json, re, numpy as np, soundfile as sf
D=json.load(open('durs.json'))
TXT={}
for line in open('../tts/vo.py'):
    m=re.match(r'\s*\("(v\d)","(.*)"\),?\s*$',line)
    if m: TXT[m.group(1)]=m.group(2)
START={'v1':1.0,'v2':13.6,'v3':24.3,'v4':32.4,'v5':41.5,'v6':50.2,'v7':58.8,'v8':65.0,'v9':71.6}
keys=sorted(START)
for a,b in zip(keys,keys[1:]): assert START[a]+D[a]<START[b]-.2,(a,b)
def kw(k,w): i=TXT[k].index(w); return START[k]+D[k]*i/len(TXT[k])
DUR=78.5
S=dict(applyClick=15.0, selClick=17.0, selPick=17.7, amtClick=18.5, type=18.75, contClick=START['v3']+.4)
S['proc']=kw('v3','agreement')+1.25; S['procOk']=S['proc']+.9
S.update(navLoans=31.9, navHist=40.9, navPay=49.6, toast=58.5, rowClick=59.9, badge=60.4,
         finalDash=64.4, rowIn=65.6, pull=69.6, endStart=70.7)
SCENES=[['sc_dash',-1,15.2],['sc_apply',15.2,31.95],['sc_loans',31.95,40.95],['sc_hist',40.95,49.65],
        ['sc_pay',49.65,57.95],['sc_inbox',57.95,64.4],['sc_dash',64.4,DUR+1]]
CAM=[[0,1,960,601],[1.0,1,960,601],[4.5,1.38,1085,560],[11.5,1.42,1085,620],[13.6,1.42,1200,560],[15.2,1.4,1150,560],
 [16.5,1.42,1085,560],[22.5,1.45,1085,560],[24.6,1.45,1085,600],[25.5,1.6,1100,420],[29.6,1.6,1100,420],[30.4,1.45,1085,600],[31.2,1.3,900,601],[32.2,1.3,900,601],
 [33.6,1.42,1000,560],[38.0,1.45,1250,560],[40.0,1.45,1300,560],[40.6,1.3,900,601],[41.4,1.3,900,601],
 [42.8,1.42,1000,540],[47.8,1.45,1300,540],[49.0,1.3,900,601],[49.9,1.3,880,601],
 [51.6,1.6,880,500],[57.4,1.62,880,505],[58.3,1.05,980,601],
 [59.6,1.12,1050,590],[60.9,1.5,1185,560],[64.1,1.56,1185,556],[64.9,1.35,1100,560],[69.6,1.38,1100,560],[70.8,1,960,601],[DUR,.98,960,601]]
# cursor waypoints: (arrive_time, x, y, travel_seconds)
WP=[(2.6,1000,760,0),(4.6,700,330,1.8),(7.4,1480,330,1.8),(10.2,1100,560,1.6),(14.85,1560,180,1.45),
    (16.85,1080,589,1.25),(17.6,1060,638,.45),(18.4,960,675,.5),(kw('v2','up to seventy'),1170,444,1.0),(S['contClick']-.15,1085,755,1.6),
    (31.75,110,326,1.0),
    (kw('v4','collateral')-.05,712,312,.9),(kw('v4','amount,')-.05,816,312,.4),(kw('v4','amount owed')-.05,936,312,.4),(kw('v4','due date')-.05,1072,312,.4),(kw('v4','status')-.05,1190,312,.4),
    (kw('v4','download')+.1,1559,311,.7),(40.75,110,370,.8),
    (kw('v5','borrowed')-.05,820,367,.9),(kw('v5','received')-.05,942,367,.4),(kw('v5','you owe')-.05,1063,367,.4),(kw('v5','term')-.05,1181,367,.4),(kw('v5','transaction')-.05,1420,367,.5),
    (49.45,128,414,.9),
    (kw('v6','Zelle')-.05,719,376,1.0),(kw('v6','Venmo')-.05,1040,376,.4),(kw('v6','wire')-.05,719,502,.4),(kw('v6','PayPal')-.05,1040,502,.4),
    (59.0,1300,700,0),(59.75,520,232,.75),(67.0,1000,452,1.1)]
MOVES=[]
for (t0,x0,y0,_),(t1,x1,y1,tr) in zip(WP,WP[1:]):
    if tr>0: MOVES.append([round(t1-tr,3),round(t1,3),[x0,y0],[x1,y1],.12])
CLICKS=[[1560,180,S['applyClick']],[1080,589,S['selClick']],[1060,638,S['selPick']],[960,675,S['amtClick']],[1085,755,S['contClick']],
        [110,326,S['navLoans']],[110,370,S['navHist']],[128,414,S['navPay']],[520,232,S['rowClick']]]
CVIS=[[2.6,25.1],[30.6,69.4]]
IBEAM=[[18.3,19.5]]
NAV=[[S['navLoans'],326],[S['navHist'],370],[S['navPay'],414]]
CHIPS=[[1.3,14.9,'Your Dashboard'],[15.6,31.6,'Apply for a Loan'],[32.3,40.7,'My Loans'],[41.3,49.4,'Loan History'],
       [50.0,57.7,'Payment Preferences'],[58.4,64.1,'Approval'],[64.8,69.9,'Track to Funding']]
CHIPS=[[a,b,f'{i+1}  ·  {txt}'] for i,(a,b,txt) in enumerate(CHIPS)]
VO={}
for k in keys:
    txt=TXT[k].replace('I D','ID'); st,du=START[k],D[k]
    # caption chunks: split after sentence ends / colons / commas when chunk is long enough
    parts=re.split(r'(?<=[.:,])\s+',txt); chunks=[];cur=''
    for p in parts:
        if cur and len(cur)+len(p)>62: chunks.append(cur);cur=p
        else: cur=(cur+' '+p).strip()
    chunks.append(cur)
    tot=sum(len(c) for c in chunks);acc=0;cap=[]
    for c in chunks:
        a=st+du*acc/tot;acc+=len(c);b=st+du*acc/tot;cap.append([round(a,3),round(b+.08,3),c])
    VO[k]=dict(start=st,dur=du,text=TXT[k],cap=cap if k!='v9' else None)
CAM=[[a,(min(1.66,1+(z-1)*1.25) if z>1.2 else z),x,y] for a,z,x,y in CAM]
TL=dict(DUR=DUR,VO=VO,S=S,SCENES=SCENES,CAM=CAM,MOVES=MOVES,CLICKS=CLICKS,CVIS=CVIS,IBEAM=IBEAM,NAV=NAV,CHIPS=CHIPS)
open('timeline.js','w').write('const TL='+json.dumps(TL)+';')

# ---------------- audio ----------------
SR=48000;N=int(DUR*SR);t=np.arange(N)/SR
rng=np.random.default_rng(3)
def env(n,a,r):  # attack/release envelope in samples
    e=np.ones(n);ai=int(a*SR);ri=int(r*SR)
    if ai: e[:ai]=np.linspace(0,1,ai)
    if ri: e[-ri:]*=np.linspace(1,0,ri)
    return e
def lp(x,a):  # one-pole lowpass
    y=np.empty_like(x);acc=0.0
    for i in range(len(x)): acc+=a*(x[i]-acc);y[i]=acc
    return y
# music: Am9 - Fmaj7 - C(add9) - G6, 4s per chord
mid=lambda m:440*2**((m-69)/12)
CH=[[57,64,67,71,72],[53,60,64,67,69],[48,55,62,64,67],[55,59,62,64,71]]
BASS=[45,41,48,43]
music=np.zeros(N)
cl=4.0
for ci in range(int(DUR/cl)+1):
    s0=int(ci*cl*SR);n=min(int((cl+1.5)*SR),N-s0)
    if n<=0:break
    tt=np.arange(n)/SR;ch=CH[ci%4]
    pad=np.zeros(n)
    for m in ch:
        f=mid(m)
        for det in (-0.08,0.08):
            ff=f*2**(det/12)
            pad+=np.sin(2*np.pi*ff*tt)+.25*np.sin(2*np.pi*2*ff*tt)+.08*np.sin(2*np.pi*3*ff*tt)
    pad*=env(n,1.4,1.6)*.018
    b=np.sin(2*np.pi*mid(BASS[ci%4]-12)*tt)*env(n,.3,1.4)*.06
    music[s0:s0+n]+=pad+b
    # arp (8th notes at 90bpm -> .333s)
    for j in range(12):
        ts=ci*cl+j*(cl/12);si=int(ts*SR);m=ch[[0,2,4,3,1,2,4,3,0,2,3,4][j]]+12
        nn=min(int(.6*SR),N-si)
        if nn<=0 or ts<2.0:continue
        tn=np.arange(nn)/SR
        music[si:si+nn]+=np.sin(2*np.pi*mid(m)*tn)*np.exp(-tn*7)*.012
# soft kick on beats after intro
beat=60/90
for j in range(int(DUR/beat)):
    ts=j*beat
    if ts<5 or ts>DUR-3:continue
    si=int(ts*SR);nn=min(int(.25*SR),N-si);tn=np.arange(nn)/SR
    music[si:si+nn]+=np.sin(2*np.pi*(45+60*np.exp(-tn*30))*tn)*np.exp(-tn*14)*.05
music*=np.clip(t/3.0,0,1)*np.clip((DUR-t)/2.5,0,1)
# voice track
vo=np.zeros(N)
for k in keys:
    a,sr=sf.read(f'{k}.wav');a=a if a.ndim==1 else a.mean(1)
    up=np.interp(np.arange(int(len(a)*SR/sr))*sr/SR,np.arange(len(a)),a)
    si=int(START[k]*SR);vo[si:si+len(up)]+=up[:N-si]
vo*=0.9/np.abs(vo).max()
# ducking envelope
act=np.zeros(N)
for k in keys: act[int((START[k]-.15)*SR):int((START[k]+D[k]+.2)*SR)]=1
k_=int(.004*SR);duck=np.convolve(act,np.ones(int(.35*SR))/int(.35*SR),'same')
music*=1-.55*duck
# sfx
sfx=np.zeros(N)
def add(ts,x,g=1.0):
    si=int(ts*SR);n=min(len(x),N-si);sfx[si:si+n]+=x[:n]*g
def click(g=.22):
    n=int(.05*SR);tn=np.arange(n)/SR;x=rng.standard_normal(n)*np.exp(-tn*400)*.5+np.sin(2*np.pi*2400*tn)*np.exp(-tn*160)
    return x*g
def whoosh(dur=.7,g=.07):
    n=int(dur*SR);x=rng.standard_normal(n);y=lp(x,.08)-lp(x,.01);e=np.sin(np.pi*np.arange(n)/n)**2
    return y*e*g*4
def chime(notes,gap=.09,dec=3.2,g=.09):
    n=int((gap*len(notes)+1.6)*SR);x=np.zeros(n)
    for i,m in enumerate(notes):
        si=int(i*gap*SR);tn=np.arange(n-si)/SR;f=mid(m)
        x[si:]+= (np.sin(2*np.pi*f*tn)+.3*np.sin(2*np.pi*2*f*tn))*np.exp(-tn*dec)
    return x*g
for c in CLICKS: add(c[2],click())
add(S['type'],click(.12));add(S['type']+.16,click(.12))
add(S['selClick']+.02,click(.08))
for sc in SCENES[1:]: add(sc[1]-.2,whoosh())
add(S['endStart']-.1,whoosh(1.2,.08))
stepT=[kw('v3','loan offer'),kw('v3','repayment'),kw('v3','review'),kw('v3','agreement'),kw('v3','agreement')+.9]
for i,ts in enumerate(stepT): add(ts,chime([76+i*2],dec=6,g=.035))
add(S['procOk'],chime([72,76,79],g=.06))
add(S['toast'],chime([88,93],gap=.12,g=.07))
add(S['badge'],chime([72,76,79,84],gap=.08,g=.08))
add(S['rowIn'],chime([79,84],gap=.1,g=.05))
add(S['endStart']+.2,chime([60,67,72,76],gap=.12,dec=1.5,g=.05))
mix=vo*1.0+music*1.0+sfx
mix/=np.abs(mix).max()/0.89
st=np.stack([mix,mix],1)
sf.write('audio.wav',st,SR,subtype='PCM_16')
print('ok',DUR,'S',{k:round(v,2) for k,v in S.items()})
