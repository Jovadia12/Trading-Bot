import json, re, numpy as np, soundfile as sf
D=json.load(open('durs.json'));TXT={}
for line in open('../tts/tf/vo.py'):
    m=re.match(r'\s*\("(v\d)","(.*)"\),?\s*$',line)
    if m: TXT[m.group(1)]=m.group(2)
START={'v1':.8,'v2':9.9,'v3':19.6,'v4':30.3,'v5':40.6,'v6':52.2,'v7':62.8,'v8':72.3}
keys=sorted(START)
for a,b in zip(keys,keys[1:]): assert START[a]+D[a]<START[b]-.2,(a,b)
def kw(k,w): i=TXT[k].index(w); return round(START[k]+D[k]*i/len(TXT[k]),3)
DUR=78.5
CLIPS={'dash':[0.0,102],'econ':[10.0,150],'pnl':[22.6,306],'paper':[32.5,162],'pay':[39.5,294],'pay2':[47.0,42]}
SCENES=[dict(id='dash',clip='dash',a=-1,b=19.0,x=.6,src=[[0,.3]]),
 dict(id='econ',clip='econ',a=19.0,b=29.8,x=.6,src=[[18.4,10.05],[30.4,12.45]]),
 dict(id='pnl',clip='pnl',a=29.8,b=40.1,x=.6,src=[[29.2,22.65],[30.8,22.9],[34.6,26.6],[39.2,27.55],[40.7,27.6]]),
 dict(id='paper',clip='paper',a=40.1,b=51.7,x=.6,src=[[39.5,32.55],[42.5,33.6],[47.5,35.0],[52.3,35.15]]),
 dict(id='pay',clip='pay',a=51.7,b=57.3,x=.6,src=[[51.1,39.55],[52.6,40.8],[57.3,44.3],[57.9,44.35]]),
 dict(id='pay2',clip='pay2',a=57.3,b=62.3,x=.35,src=[[57.0,47.05],[62.9,47.65]]),
 dict(id='dash',clip='dash',a=62.3,b=DUR+2,x=.6,src=[[0,.3]])]
HL=[dict(scene='dash',r=[441,242,1721,374],t=kw('v2','Track your results')),
    dict(scene='dash',r=[1310,398,1720,898],t=kw('v2','review recent')),
    dict(scene='dash',r=[441,398,1286,1078],t=kw('v2','follow your daily')),
    dict(scene='dash',r=[1310,922,1720,1078],t=kw('v2','stay focused'),hold=1.6),
    dict(scene='econ',r=[465,393,870,455],t=kw('v3','high-impact'),red=1,hold=1.8),
    dict(scene='econ',r=[465,476,1697,628],t=kw('v3','high-impact')+.5,red=1,hold=2.2),
    dict(scene='econ',r=[465,758,1697,1078],t=kw('v3','market-moving'),hold=2.0),
    dict(scene='pnl',r=[766,769,1060,861],t=kw('v4','daily'),hold=1.6),
    dict(scene='pnl',r=[1169,366,1262,861],t=kw('v4','weekly'),hold=1.6),
    dict(scene='pnl',r=[581,268,774,296],t=kw('v4','identify patterns'),hold=1.8),
    dict(scene='paper',r=[272,240,559,661],t=kw('v5','practice your'),hold=1.5),
    dict(scene='paper',r=[577,182,1655,1078],t=kw('v5','analyze the market'),hold=1.6),
    dict(scene='paper',r=[272,677,575,713],t=kw('v5','test your decisions'),hold=1.5),
    dict(scene='paper',r=[272,240,559,325],t=kw('v5','simulated'),hold=1.4),
    dict(scene='pay2',r=[441,299,743,403],t=kw('v6','valid profit days'),hold=1.2),
    dict(scene='pay2',r=[1093,299,1395,403],t=kw('v6','payout split'),hold=1.0),
    dict(scene='pay2',r=[1419,299,1721,403],t=kw('v6','account balance'),hold=1.0),
    dict(scene='pay2',r=[441,803,1721,966],t=kw('v6','payout history'),hold=1.8)]
CAM=[[0,1,960,601],[1.5,1,960,601],[9.4,1.3,1080,600],
 [11.0,1.45,1080,520],[13.6,1.5,1209,600],[15.6,1.5,860,700],[17.6,1.5,1209,760],[19.0,1.4,1080,600],
 [20.0,1.42,1080,530],[24.5,1.5,1080,560],[27.5,1.5,1080,700],[29.8,1.4,1000,600],
 [31.0,1.42,880,560],[34.6,1.5,900,600],[36.5,1.5,1000,620],[39.0,1.45,860,560],[40.1,1.4,1000,600],
 [41.0,1.45,800,560],[43.5,1.6,700,520],[45.0,1.55,1100,600],[47.5,1.6,1200,680],[49.2,1.6,700,640],[51.0,1.5,900,600],[51.7,1.45,1080,560],
 [52.6,1.45,1080,520],[53.8,1.6,960,600],[57.0,1.62,960,600],[57.5,1.45,1080,540],[59.5,1.5,1080,500],[61.6,1.5,1080,760],[62.6,1.3,1000,601],
 [65.0,1.25,1000,601],[68.8,1.3,1050,601],[70.8,1,960,601],[DUR,.98,960,601]]
S=dict(pull=69.0,end=71.5,e1=kw('v8','Know'),e2=kw('v8','Track'),e3=kw('v8','Trade with'))
CHIPS=[[9.9,19.0,'Dashboard'],[19.4,29.8,'Economic Calendar'],[30.1,40.1,'P&L Calendar'],[40.5,51.7,'Paper Trading'],[52.0,62.3,'Payout Tracker']]
CAPS=[]
for k in keys:
    if k=='v8':continue
    txt=TXT[k].replace('P and L','P&L');st,du=START[k],D[k]
    parts=re.split(r'(?<=[.:,?])\s+',txt);chunks=[];cur=''
    for p in parts:
        if cur and len(cur)+len(p)>62: chunks.append(cur);cur=p
        else: cur=(cur+' '+p).strip()
    chunks.append(cur);tot=sum(len(c) for c in chunks);acc=0
    for c in chunks:
        a=st+du*acc/tot;acc+=len(c);b=st+du*acc/tot;CAPS.append([round(a,3),round(b+.08,3),c])
open('timeline.js','w').write('const TL='+json.dumps(dict(DUR=DUR,CLIPS=CLIPS,SCENES=SCENES,HL=HL,CAM=CAM,S=S,CHIPS=CHIPS,CAPS=CAPS))+';')
# ---------------- audio ----------------
SR=48000;N=int(DUR*SR);t=np.arange(N)/SR;rng=np.random.default_rng(7)
mid=lambda m:440*2**((m-69)/12)
def env(n,a,r):
    e=np.ones(n);ai=int(a*SR);ri=int(r*SR)
    if ai:e[:ai]=np.linspace(0,1,ai)
    if ri:e[-ri:]*=np.linspace(1,0,ri)
    return e
BPM=100;beat=60/BPM;bar=4*beat
CH=[[50,57,62,65,69],[46,53,58,62,65],[53,60,64,65,69],[48,55,60,62,67]]   # Dm9 Bbmaj9 F(add) C(sus)
BASS=[38,34,41,36]
mus=np.zeros(N)
for ci in range(int(DUR/bar)+1):
    s0=int(ci*bar*SR);n=min(int((bar+1.5)*SR),N-s0)
    if n<=0:break
    tt=np.arange(n)/SR;ch=CH[ci%4];pad=np.zeros(n)
    for m in ch:
        f=mid(m+12)
        for det in(-.07,.07):
            ff=f*2**(det/12);pad+=np.sin(2*np.pi*ff*tt)+.22*np.sin(2*np.pi*2*ff*tt)
    mus[s0:s0+n]+=pad*env(n,1.2,1.5)*.014
    for j in range(8):  # pulsing bass 8ths
        ts=ci*bar+j*beat/2;si=int(ts*SR);nn=min(int(.28*SR),N-si)
        if nn<=0 or ts<4:continue
        tn=np.arange(nn)/SR;f=mid(BASS[ci%4])
        mus[si:si+nn]+=(np.sin(2*np.pi*f*tn)+.3*np.sin(2*np.pi*2*f*tn))*np.exp(-tn*9)*.045
    for j in range(16):  # soft pluck arp 16ths
        ts=ci*bar+j*beat/4;si=int(ts*SR);nn=min(int(.35*SR),N-si)
        if nn<=0 or ts<6 or j%2==1 and j%4!=3:continue
        tn=np.arange(nn)/SR;m=ch[[0,2,4,3,1,4,2,3,0,3,4,2,1,2,4,3][j]]+24
        mus[si:si+nn]+=np.sin(2*np.pi*mid(m)*tn)*np.exp(-tn*11)*.008
for j in range(int(DUR/beat)):
    ts=j*beat
    if ts<8 or ts>DUR-6:continue
    si=int(ts*SR);nn=min(int(.25*SR),N-si);tn=np.arange(nn)/SR
    mus[si:si+nn]+=np.sin(2*np.pi*(48+70*np.exp(-tn*32))*tn)*np.exp(-tn*13)*.06
    hs=int((ts+beat/2)*SR);hn=min(int(.06*SR),N-hs)
    if hn>0:
        h=rng.standard_normal(hn);h=np.diff(np.concatenate([[0],h]))*np.exp(-np.arange(hn)/SR*70)
        mus[hs:hs+hn]+=h*.006
mus*=np.clip(t/3,0,1)*np.clip((DUR-t)/3,0,1)
vo=np.zeros(N)
for k in keys:
    a,sr=sf.read(f'{k}.wav');a=a if a.ndim==1 else a.mean(1)
    up=np.interp(np.arange(int(len(a)*SR/sr))*sr/SR,np.arange(len(a)),a);si=int(START[k]*SR);vo[si:si+len(up)]+=up[:N-si]
vo*=.9/np.abs(vo).max()
act=np.zeros(N)
for k in keys: act[int((START[k]-.15)*SR):int((START[k]+D[k]+.2)*SR)]=1
duck=np.convolve(act,np.ones(int(.35*SR))/int(.35*SR),'same');mus*=1-.55*duck
sfx=np.zeros(N)
def add(ts,x,g=1.):
    si=int(ts*SR);n=min(len(x),N-si);sfx[si:si+n]+=x[:n]*g
def whoosh(dur=.8,g=.06):
    n=int(dur*SR);x=rng.standard_normal(n);k_=np.ones(40)/40;y=np.convolve(x,k_,'same')-np.convolve(x,np.ones(400)/400,'same')
    return y*np.sin(np.pi*np.arange(n)/n)**2*g*3
def chime(notes,gap=.1,dec=2.5,g=.06):
    n=int((gap*len(notes)+1.8)*SR);x=np.zeros(n)
    for i,m in enumerate(notes):
        si=int(i*gap*SR);tn=np.arange(n-si)/SR;f=mid(m);x[si:]+=(np.sin(2*np.pi*f*tn)+.3*np.sin(2*np.pi*2*f*tn))*np.exp(-tn*dec)
    return x*g
for sc in SCENES[1:]: add(sc['a']-.25,whoosh())
add(S['end']-.1,whoosh(1.3,.07))
for h in HL: add(h['t']-.1,chime([86],dec=9,g=.012))
add(S['end']+.3,chime([62,69,74,77],gap=.12,dec=1.4,g=.05))
mix=vo+mus+sfx;mix/=np.abs(mix).max()/.89
sf.write('audio.wav',np.stack([mix,mix],1),SR,subtype='PCM_16');print('ok',S)
