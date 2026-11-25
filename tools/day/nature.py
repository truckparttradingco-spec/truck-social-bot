"""Nature-scene 'good morning' feed post (1080x1350) per Persian month.
python3 nature.py MI out.jpg [json]   (MI = 1..12)"""
import sys,os,json,math,random,base64
from playwright.sync_api import sync_playwright
from PIL import Image
H=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,H);import months as MO
b=lambda p:base64.b64encode(open(H+'/'+p,'rb').read()).decode()
W,Hh=1080,1350
CFG={
1:dict(sky=['#4fb6ff','#aee8d2','#fff3a8'],sun=('#fffbd0',700,560,90),mt=['#8fd0b0','#62b98f'],hills=['#6fd45a','#4bbf48','#2fa23f'],el='blossom',ec=['#ffb3d1','#ff7eb0','#ffd6e8'],gr='#2e9a3a'),
2:dict(sky=['#6cc5ff','#ffc4e1','#fff0c2'],sun=('#fff4c0',300,540,85),mt=['#9fd8c0','#72c29f'],hills=['#76d95c','#52c04a','#33a33f'],el='roses',ec=['#ff2d6f','#ff6b9d','#ffd0e0'],gr='#2c9a3c'),
3:dict(sky=['#3fa9ff','#a9deff','#fff6c9'],sun=('#fff9c9',760,520,95),mt=['#8ed0a0','#66b985'],hills=['#8bdc45','#62c333','#43a82b'],el='cherry',ec=['#e0102f','#ff4060','#a00a22'],gr='#2e9a2e'),
4:dict(sky=['#1f8fff','#5fc0ff','#d6f1ff'],sun=('#fff7b0',800,300,120),mt=['#8cc4e0','#5fa7cf'],hills=['#a8dd4a','#78c62f','#4aa82a'],el='sunflower',ec=['#ffd21f','#ffb400','#6b3a10'],gr='#2f9a2a'),
5:dict(sky=['#ff8a2a','#ffc65a','#fff0a0'],sun=('#fffbd8',540,540,130),mt=['#f0b860','#e0a040'],hills=['#f6c640','#e6a825','#cf8918'],el='wheat',ec=['#ffd84a','#f0b020','#b87510'],gr='#b87510'),
6:dict(sky=['#6a4cd0','#f08fb0','#ffd27a'],sun=('#ffe9a8',300,600,100),mt=['#8a6ab8','#6c5498'],hills=['#a0b83a','#7e9a2c','#5c8226'],el='grape',ec=['#7b2fbf','#a64be0','#4b1a7a'],gr='#4c7a24'),
7:dict(sky=['#3f9ee6','#f4c48a','#ffe6b8'],sun=('#fff2c8',760,560,85),mt=['#d89a6a','#b87848'],hills=['#e8a838','#cf7a28','#a85a20'],el='autumn',ec=['#ff7a1a','#e8281e','#ffc21a'],gr='#a85a20'),
8:dict(sky=['#3f6f7e','#85b2bc','#cfe3e6'],sun=('#e8f4f4',340,380,70),mt=['#5f9aa6','#3f7f8e'],hills=['#4aa890','#2f8f7a','#1f7566'],el='rainpine',ec=['#1f6a5a','#2a8470','#134a40'],gr='#1a5a4a'),
9:dict(sky=['#f09a4a','#f7cf8a','#fff0c0'],sun=('#fff3c8',720,580,90),mt=['#d8a070','#b88050'],hills=['#e8b040','#d08428','#a8601c'],el='autumn',ec=['#ff6a1a','#e0301a','#ffb81a'],gr='#a8601c'),
10:dict(sky=['#27468a','#e48cb4','#ffd9b0'],sun=('#fff0d0',540,620,80),mt=['#ffffff','#dbe8ff'],hills=['#f4f8ff','#dfeaff','#c6d8f5'],el='snowpine',ec=['#1f5a4a','#2a7060','#154036'],gr='#9fb8e0'),
11:dict(sky=['#18306a','#4a7cc0','#cfe4ff'],sun=('#f4f8ff',300,330,60),mt=['#ffffff','#d8e6ff'],hills=['#f4f8ff','#e0ecff','#c8daf6'],el='snowpine',ec=['#1c5a50','#287066','#103a34'],gr='#a8c0e6'),
12:dict(sky=['#7fcfff','#ffd8ea','#fff8dc'],sun=('#fffbd0',700,560,90),mt=['#a8dcc0','#80c8a0'],hills=['#8ee068','#62cc52','#3fb04a'],el='almond',ec=['#ffffff','#ffc0d8','#ff90b8'],gr='#2fa040'),
}
def ridge(rnd,base,amp,col,step=10):
    p1,p2,p3=rnd.random()*6,rnd.random()*6,rnd.random()*6
    f1,f2,f3=rnd.uniform(.004,.007),rnd.uniform(.009,.014),rnd.uniform(.02,.03)
    pts=[(x,base+amp*(math.sin(f1*x+p1)*.6+math.sin(f2*x+p2)*.3+math.sin(f3*x+p3)*.1)) for x in range(-10,W+20,step)]
    d='M'+' L'.join(f'{x},{y:.1f}' for x,y in pts)+f' L{W+20},{Hh} L-10,{Hh}Z'
    return f'<path d="{d}" fill="{col}"/>',lambda x:base+amp*(math.sin(f1*x+p1)*.6+math.sin(f2*x+p2)*.3+math.sin(f3*x+p3)*.1)
def tree(x,y,s,cols,rnd,trunk='#6b4423'):
    o=f'<rect x="{x-5*s}" y="{y-40*s}" width="{10*s}" height="{42*s}" fill="{trunk}" rx="3"/>'
    for _ in range(9):
        o+=f'<circle cx="{x+rnd.uniform(-28,28)*s:.1f}" cy="{y-rnd.uniform(48,92)*s:.1f}" r="{rnd.uniform(16,26)*s:.1f}" fill="{rnd.choice(cols)}"/>'
    return o
def pine(x,y,s,c,snow,rnd):
    o=f'<rect x="{x-4*s}" y="{y-10*s}" width="{8*s}" height="{18*s}" fill="#4a3320"/>'
    for i in range(4):
        w=(44-i*8)*s;yy=y-10*s-i*26*s
        o+=f'<polygon points="{x-w},{yy} {x+w},{yy} {x},{yy-44*s}" fill="{c}"/>'
        if snow: o+=f'<polygon points="{x-w*.7},{yy-12*s} {x+w*.7},{yy-12*s} {x},{yy-44*s}" fill="#fff" opacity=".92"/>'
    return o
def flower(x,y,r,cols,stem=None,n=6):
    o=''
    if stem: o+=f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y+stem}" stroke="#2c8a34" stroke-width="{max(3,r/5):.1f}"/>'
    for i in range(n):
        a=2*math.pi*i/n
        o+=f'<circle cx="{x+r*.7*math.cos(a):.1f}" cy="{y+r*.7*math.sin(a):.1f}" r="{r*.55:.1f}" fill="{cols[0]}"/>'
    return o+f'<circle cx="{x}" cy="{y}" r="{r*.45:.1f}" fill="{cols[1]}"/>'
def wheat(x,y,h,c):
    o=f'<path d="M{x},{y} Q{x+6},{y-h/2} {x+3},{y-h}" stroke="{c[2]}" stroke-width="4" fill="none"/>'
    for i in range(6):
        yy=y-h+i*10
        o+=f'<ellipse cx="{x-7+3}" cy="{yy}" rx="4" ry="10" transform="rotate(-30 {x-4} {yy})" fill="{c[i%2]}"/><ellipse cx="{x+13}" cy="{yy}" rx="4" ry="10" transform="rotate(30 {x+13} {yy})" fill="{c[(i+1)%2]}"/>'
    return o
def scene(mi,seed=0):
    C=CFG[mi];r=random.Random(mi*100+seed);o=''
    o+=f'<defs><linearGradient id="sk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{C["sky"][0]}"/><stop offset=".55" stop-color="{C["sky"][1]}"/><stop offset="1" stop-color="{C["sky"][2]}"/></linearGradient><radialGradient id="sg"><stop offset="0" stop-color="{C["sun"][0]}"/><stop offset=".45" stop-color="{C["sun"][0]}" stop-opacity=".9"/><stop offset="1" stop-color="{C["sun"][0]}" stop-opacity="0"/></radialGradient></defs>'
    o+=f'<rect width="{W}" height="{Hh}" fill="url(#sk)"/>'
    sx,sy,sr=C['sun'][1:];sy=585;sr=int(sr*.95)
    o+=f'<circle cx="{sx}" cy="{sy}" r="{sr*2.6}" fill="url(#sg)" opacity=".75"/><circle cx="{sx}" cy="{sy}" r="{sr}" fill="{C["sun"][0]}"/>'
    if C['el'] in('rainpine','snowpine') or mi in(8,11):
        for _ in range(6): o+=f'<ellipse cx="{r.randint(0,W)}" cy="{r.randint(120,420)}" rx="{r.randint(90,170)}" ry="{r.randint(22,40)}" fill="#fff" opacity=".35"/>'
    else:
        for _ in range(4): o+=f'<ellipse cx="{r.randint(0,W)}" cy="{r.randint(140,430)}" rx="{r.randint(80,150)}" ry="{r.randint(18,32)}" fill="#fff" opacity=".55"/>'
    s,_=ridge(r,640,70,C['mt'][0]);o+=s
    s,_=ridge(r,700,60,C['mt'][1]);o+=s
    if mi in(10,11):
        o+=''.join(f'<polygon points="{x-70},780 {x},{y} {x+70},780" fill="#fff" opacity=".0"/>' for x,y in [])
    s0,f0=ridge(r,800,40,C['hills'][0]);o+=s0
    s1,f1=ridge(r,900,45,C['hills'][1]);o+=s1
    if mi==4:
        o+=f'<rect x="0" y="730" width="{W}" height="70" fill="#2f9aff" opacity=".7"/>'+''.join(f'<line x1="{x}" y1="{y}" x2="{x+40}" y2="{y}" stroke="#fff" stroke-width="3" opacity=".6"/>' for x in range(0,W,70) for y in (745,770))
    if mi==8: o+=f'<path d="M0 790 Q300 760 540 800 T1080 790 L1080 830 L0 830Z" fill="#6fc3d0" opacity=".85"/>'
    el=C['el'];ec=C['ec']
    # mid-ground
    if el in('blossom','cherry','autumn','almond','grape'):
        for x in range(60,W,150):
            y=f0(x)+30+r.randint(-6,10)
            cols={'blossom':ec,'cherry':['#3fa83a','#58c04a','#2f9030'],'autumn':ec,'almond':ec,'grape':['#6faa2c','#8cc43c','#52902a']}[el]
            o+=tree(x+r.randint(-20,20),y,1.0 if el!='almond' else 1.1,cols,r)
    if el in('rainpine','snowpine'):
        for x in range(40,W,90):
            y=f0(x)+26+r.randint(-4,8);o+=pine(x+r.randint(-14,14),y,.9,ec[r.randint(0,2)],el=='snowpine',r)
    o+=s1 if False else ''
    s2,f2=ridge(r,1010,40,C['hills'][2]);o+=s2
    # foreground
    for x in range(20,W,38):
        y=f2(x)+r.randint(10,300)
        if y>Hh-20: continue
        if el in('roses','blossom','almond'):
            pass
    if el=='roses':
        for x in range(30,W,110):
            y=f2(x)+r.randint(40,200);o+=flower(x+r.randint(-20,20),y,r.randint(34,50),[r.choice(ec[:2]),ec[2]],stem=140,n=7)
    if el=='blossom':
        for x in range(40,W,70):
            y=f2(x)+r.randint(60,230);o+=flower(x,y,r.randint(14,22),[r.choice(ec),'#ffe27a'],stem=60,n=5)
    if el=='cherry':
        for x in range(30,W,95):
            y=f2(x)+r.randint(60,230);o+=flower(x,y,r.randint(14,20),['#ffffff','#ffd21f'],stem=60,n=6)
    if el=='sunflower':
        for x in range(30,W,120):
            y=f2(x)+r.randint(50,220);rr=r.randint(40,58)
            o+=flower(x,y,rr,[ec[0],ec[2]],stem=190,n=12)
    if el=='wheat':
        for x in range(10,W,20):
            y=f2(x)+r.randint(40,330);o+=wheat(x,y,r.randint(130,230),ec)
    if el=='grape':
        for x in range(60,W,140):
            y=f2(x)+r.randint(30,160)
            for row in range(4):
                for k in range(row+1): o+=f'<circle cx="{x-row*9+k*18}" cy="{y+row*17}" r="9" fill="{r.choice(ec)}"/>'
            o+=f'<path d="M{x} {y-6} q8 -20 20 -24" stroke="#4c7a24" stroke-width="4" fill="none"/>'
    if el=='autumn':
        for _ in range(26):
            x=r.randint(0,W);y=r.randint(900,1300)
            o+=f'<ellipse cx="{x}" cy="{y}" rx="13" ry="7" transform="rotate({r.randint(0,180)} {x} {y})" fill="{r.choice(ec)}"/>'
        for x in range(40,W,170):
            y=f2(x)+r.randint(110,280);o+=tree(x,y,1.5,ec,r,trunk='#5a3a1c')
    if el=='almond':
        o+=f'<path d="M-20 1120 Q300 960 560 1010 T1110 880" stroke="#5a3a28" stroke-width="16" fill="none" stroke-linecap="round"/>'
        for _ in range(60):
            t=r.random();x=-20+t*1130;y=1120-t*240+math.sin(t*6)*40+r.randint(-40,40)
            o+=flower(x,y,r.randint(12,22),[r.choice(ec),'#ffd84a'],n=5)
    if el in('rainpine','snowpine'):
        for x in range(20,W,160):
            y=f2(x)+r.randint(90,260);o+=pine(x,y,1.6,ec[r.randint(0,2)],el=='snowpine',r)
    if el=='rainpine':
        for _ in range(160):
            x=r.randint(0,W);y=r.randint(0,Hh);o+=f'<line x1="{x}" y1="{y}" x2="{x-12}" y2="{y+46}" stroke="#e8f6f8" stroke-width="2.5" opacity=".55"/>'
    if mi in(10,11):
        for _ in range(110):
            o+=f'<circle cx="{r.randint(0,W)}" cy="{r.randint(0,Hh)}" r="{r.choice([2,3,4,5])}" fill="#fff" opacity=".85"/>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{Hh}" viewBox="0 0 {W} {Hh}" style="position:absolute;left:0;top:0">{o}</svg>'
QE=json.load(open(H+'/quotes_energy.json'))
D=dict(mi=9,wd='چهارشنبه',day='۴',year='۱۴۰۵',gd='25',gm='November',hd='۱۵',hm='جمادی‌الثانی',hy='۱۴۴۸',gy='2026',qi=0)
def build(D):
    mi=D['mi'];q,by=QE[D['qi']%len(QE)]
    sh='#00000066'
    dark={1:'#0b4a2a',2:'#7a0f3a',3:'#7a1020',4:'#07407a',5:'#7a4300',6:'#3a1a6a',7:'#7a3200',8:'#0a3a46',9:'#7a3000',10:'#14305f',11:'#0f2550',12:'#8a2a5a'}[mi]
    qs=60 if len(q)<45 else (50 if len(q)<80 else 42)
    ph=os.environ.get('NATURE_DIR','')+f'/{mi}.jpg'
    if os.environ.get('NATURE_DIR') and os.path.exists(ph):
        BG=f'<div style="position:absolute;inset:0;background:url(data:image/jpeg;base64,{base64.b64encode(open(ph,"rb").read()).decode()}) center/cover"></div><div style="position:absolute;inset:0;background:linear-gradient(180deg,#000a 0,#0003 34%,#0000 48%,#0000 62%,#0009 100%)"></div>'
    else: BG=scene(mi)
    return f'''<!doctype html><meta charset=utf8><style>
@font-face{{font-family:P;src:url(data:font/ttf;base64,{b('Parastoo-Print-Bold.ttf')})}}
*{{box-sizing:border-box;margin:0}}html{{width:{W}px;overflow:hidden}}body{{width:{W}px;height:{Hh}px;position:relative;overflow:hidden;font-family:P,sans-serif;direction:rtl;color:#fff}}
.t1{{position:absolute;top:70px;left:0;right:0;text-align:center;font-size:92px;line-height:1.1;text-shadow:0 4px 0 {dark},0 10px 30px #0007}}
.t2{{position:absolute;top:175px;left:0;right:0;text-align:center;font-size:132px;line-height:1.1;color:#fff7c2;text-shadow:0 6px 0 {dark},0 14px 34px #0008}}
.chip{{position:absolute;top:340px;left:110px;right:110px;background:#ffffffee;color:{dark};border-radius:70px;text-align:center;font-size:62px;padding:12px 10px;box-shadow:0 10px 0 {dark}55,0 22px 50px #0005}}
.sub{{position:absolute;top:458px;left:0;right:0;text-align:center;font-size:40px;text-shadow:0 3px 0 {dark},0 6px 18px #0007;direction:rtl}}.sub i{{font-style:normal;font-family:Inter,Arial,sans-serif;font-weight:700;direction:ltr;unicode-bidi:isolate;margin-inline:14px;font-size:36px}}
.q{{position:absolute;top:712px;left:70px;right:70px;background:#00000066;backdrop-filter:blur(8px);border:2px solid #ffffff55;border-radius:50px;padding:30px 44px;text-align:center}}
.q div{{font-size:{qs}px;line-height:1.55;text-shadow:0 3px 0 #0006}}.q span{{display:block;margin-top:10px;font-size:38px;color:#ffe27a}}
.ft{{position:absolute;bottom:0;left:0;right:0;height:96px;background:#000000b8;display:flex;align-items:center;justify-content:center;gap:50px;direction:ltr;font-family:Inter,Arial,sans-serif;font-weight:700;font-size:34px}}
.lg{{width:170px;height:70px;background:#ffd84a;-webkit-mask:url(data:image/png;base64,{b('tp_alpha.png')}) center/contain no-repeat}}
</style>{BG}
<div class=t1>صبح زیبای</div><div class=t2>{D['wd']}‌ات بخیر!</div>
<div class=chip>امروز {D['wd']} {D['day']} {MO.NAMES[mi]} {D['year']}</div>
<div class=sub><i>{D['gd']} {D['gm']} {D['gy']}</i> • {D['hd']} {D['hm']} {D['hy']}</div>
<div class=q><div>«{q}»</div><span>— {by}</span></div>
<div class=ft><div class=lg></div><span>www.truckparttrading.com</span><span>021-55282160-61</span></div>'''
if __name__=='__main__':
    D2=dict(D);D2['mi']=int(sys.argv[1])
    if len(sys.argv)>3: D2.update(json.load(open(sys.argv[3])))
    with sync_playwright() as p:
        br=p.chromium.launch();pg=br.new_page(viewport={'width':W,'height':Hh});pg.set_content(build(D2));pg.wait_for_timeout(500)
        pg.screenshot(path=sys.argv[2].replace('.jpg','.png'));br.close()
    Image.open(sys.argv[2].replace('.jpg','.png')).convert('RGB').save(sys.argv[2],quality=92)
