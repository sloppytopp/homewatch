"""Local dashboard (http://127.0.0.1:8777). Big green/amber/red tiles + 'log a beep' button."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>N0RMA</title><style>
:root{--bg:#000;--fg:#c8c8c8;--mut:#8a8a8a;--faint:#6a6a6a;--card:#0e0e0e;--ring:#2a2a2a;
--okbg:#0f1d15;--watchbg:#211b0d;--alertbg:#2a1313;--offbg:#141414;--ok:#5e9a74;--watch:#b39a55;--alert:#c06a6a;--off:#7a7a7a;--btn:#1c2a22;--btnfg:#9cc7ab}
html.night{--fg:#8c3030;--mut:#722b2b;--faint:#5a2222;--card:#0a0303;--ring:#2a0d0d;--okbg:#0c0404;--watchbg:#0c0404;--alertbg:#0c0404;--offbg:#0c0404;
--ok:#6e2a2a;--watch:#8c3434;--alert:#aa4040;--off:#4a1c1c;--btn:#1a0707;--btnfg:#8c3030}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:16px system-ui,sans-serif;max-width:900px;margin:auto}
.top{display:flex;align-items:center;gap:10px;margin:0 0 10px}.top h1{font-size:20px;margin:0;flex:1}
.dot{width:10px;height:10px;border-radius:50%;background:var(--off);display:inline-block}.dot.live{background:var(--ok);animation:br 1.4s ease-in-out infinite alternate}
@keyframes br{from{opacity:.3}to{opacity:1}}@media(prefers-reduced-motion:reduce){.dot.live{animation:none}}
.banner{border-radius:12px;padding:14px 16px;margin:8px 0;border-left:5px solid var(--off);background:var(--offbg)}
.banner b{font-size:18px;display:block}.banner span{font-size:12px;color:var(--mut)}
.tile{border-radius:10px;padding:12px 16px;margin:8px 0;border-left:5px solid var(--off);background:var(--offbg)}
.tile b{font-size:16px;display:block}.tile span{font-size:13px;color:var(--mut);word-break:break-word}
.ok{background:var(--okbg);border-color:var(--ok)}.ok b,.banner.ok b{color:var(--ok)}
.watch{background:var(--watchbg);border-color:var(--watch)}.watch b,.banner.watch b{color:var(--watch)}
.alert{background:var(--alertbg);border-color:var(--alert)}.alert b,.banner.alert b{color:var(--alert)}
.off b{color:var(--off)}
.card{background:var(--card);border-radius:10px;padding:12px 16px;margin:14px 0}.card h2{font-size:15px;margin:0 0 8px;color:var(--mut)}
table{width:100%;border-collapse:collapse;font-size:13px}td{padding:3px 6px;border-bottom:1px solid var(--ring)}
button{font-size:15px;padding:10px 16px;border-radius:8px;border:0;background:var(--btn);color:var(--btnfg);cursor:pointer}
button.s{font-size:12px;padding:3px 8px}label.n{font-size:13px;color:var(--mut);cursor:pointer}
.tabs{display:flex;gap:6px;margin:6px 0}.tabs button{flex:1;font-size:14px;padding:8px 4px;background:var(--card);color:var(--faint)}.tabs button.on{background:var(--btn);color:var(--btnfg)}.e-alert{color:var(--alert)}.e-watch{color:var(--watch)}.m{color:var(--mut)}a{color:var(--btnfg)}
</style><div class=top><span class=dot id=hb></span><h1>N0RMA <span class=m id=t></span></h1><label class=n><input type=checkbox id=night> Night</label></div>
<div class=tabs id=tabs><button data-t=status>Status</button><button data-t=nearby>Nearby</button><button data-t=radar>Radar</button><button data-t=history>History</button></div>
<div data-tab=status><div id=banner class=banner><b>Starting...</b></div><div id=tiles></div>
<p><button onclick="fetch('/api/beep',{method:'POST',headers:{'X-Homewatch':'1'}}).then(load)">I heard the sensor beep - log it now</button></p>
</div>
<div data-tab=radar><div class=card><h2>Proximity radar <span class=m>(rough estimate from signal strength - indoors it can be badly wrong; direction is NOT known, blip angles are arbitrary)</span></h2>
<canvas id=radar width=640 height=640 style="width:100%;max-width:560px;display:block;margin:auto"></canvas>
<p class=m style="font-size:12px;text-align:center">green = your network &nbsp; gray = neighbors &nbsp; amber = tracker/watch &nbsp; red = alert &nbsp; triangle = drone</p></div>
<div class=card id=dmapcard style="display:none"><h2>Drone map <span class=m>(real positions from Remote ID)</span></h2>
<canvas id=dmap width=640 height=480 style="width:100%;max-width:560px;display:block;margin:auto"></canvas><div id=dinfo class=m style="font-size:13px"></div></div>
</div>
<div data-tab=history><div class=card><h2>Recent events</h2><table id=ev></table></div></div>
<div data-tab=status>
<details class=card><summary><b>If something is flagged - what to do</b></summary><div style="font-size:14px;line-height:1.5">
<p><b>Stay calm.</b> Most alerts turn out to be ordinary: a neighbor's device, your own phone, a passing car. A single amber or red line is a reason to look, not proof that someone is targeting you.</p>
<p><b>Tracker:</b> a tracker that stays strong for many minutes is worth finding. Use <code>n0rma find &lt;address&gt;</code> to walk toward it. Don't move or destroy it yet: photograph it where it is, note the time, and contact local law enforcement. iPhone: Find My &rarr; Items &rarr; Identify Found Item. Android: Settings &rarr; Safety &amp; emergency &rarr; Unknown tracker alerts.</p>
<p><b>Drone:</b> a Remote ID broadcast only <i>claims</i> a drone and can be faked. Note the time and what you saw. Don't shoot at, jam or interfere with it (that is a federal crime). You can report it to local law enforcement or the FAA.</p>
<p><b>Unknown device on your Wi-Fi:</b> look it up in your router's client list, block it, then change the Wi-Fi password and turn off WPS and any guest network you don't use.</p>
<p><b>If you feel unsafe</b> (for example a stalker or abusive partner), contact local police or the National Domestic Violence Hotline (US: 1-800-799-7233). A quiet dashboard is not a guarantee of safety: this tool cannot see every kind of device.</p>
</div></details></div>
<div data-tab=nearby><div class=card><h2>Wi-Fi networks nearby</h2><table id=wifi></table></div>
<div class=card><h2>Devices on your network</h2><table id=lan></table></div>
<div class=card><h2>Bluetooth trackers / drones in range</h2><table id=ble></table></div></div>
<script>
try{if(localStorage.getItem('hw_night')==='1'){document.documentElement.classList.add('night');night.checked=true}}catch(e){}
night.onchange=()=>{document.documentElement.classList.toggle('night',night.checked);try{localStorage.setItem('hw_night',night.checked?'1':'0')}catch(e){}};
function showTab(t){document.querySelectorAll('[data-tab]').forEach(e=>e.style.display=e.dataset.tab===t?'':'none');
 document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.t===t));try{localStorage.setItem('hw_tab',t)}catch(e){}}
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>showTab(b.dataset.t));
let T0='status';try{T0=localStorage.getItem('hw_tab')||'status'}catch(e){}showTab(['status','nearby','radar','history'].includes(T0)?T0:'status');
const post=async u=>{await fetch(u,{method:'POST',headers:{'X-Homewatch':'1'}});load()};
const ICON={ok:'✓',watch:'◔',alert:'▲',off:'–'};
const ago=s=>s<60?Math.round(s)+'s':Math.floor(s/60)+'m '+Math.round(s%60)+'s';
function banner(d){const lv=Object.values(d.state).filter(x=>x.title.indexOf('computer')<0).map(x=>x.level);const w=lv.includes('alert')?'alert':lv.includes('watch')?'watch':'ok';
 const b=document.getElementById('banner');b.className='banner '+w;hb.className='dot live';
 const wa=d.live.wifi_at?' · Wi-Fi: '+(d.live.wifi||[]).length+' networks (scanned '+ago(d.now-d.live.wifi_at)+' ago)':'';
 const ads=d.live.ble?' · Bluetooth: '+d.live.ble.advertisements_seen+' signals heard':'';
 b.innerHTML='<b>'+(w==='alert'?'Needs your attention':w==='watch'?'Keeping an eye on something':'All clear')+'</b><span>Scanning for '+ago(d.now-(d.started||d.now))+wa+ads+'</span>'}
const E=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
let LAST=null,MY=new Set();
async function mine(a,on){await fetch('/api/mine?addr='+encodeURIComponent(a)+'&on='+on,{method:'POST',headers:{'X-Homewatch':'1'}});load()}
const C=()=>getComputedStyle(document.documentElement);
function hash(str){let h=0;for(let i=0;i<str.length;i++)h=(h*31+str.charCodeAt(i))>>>0;return h}
function rssiToM(r,tx){return Math.pow(10,(tx-r)/25)}   // log-distance, n=2.5 (rough, indoors)
function rpos(m){const R=[5,20,60];const mm=Math.max(.5,m);let f;
 if(mm<=5)f=mm/5*.33;else if(mm<=20)f=.33+(mm-5)/15*.33;else f=Math.min(1,.66+Math.min(mm-20,40)/40*.34);return f}
function blips(d){const L=d.live,out=[],mine=new Set(d.my_ssids||[]);
 (L.wifi||[]).forEach(w=>{const known=mine.has(w.ssid)||w.klass==='camera';
  out.push({id:w.bssid,label:w.ssid||'hidden',m:rssiToM(w.signal,-45),col:mine.has(w.ssid)?getComputedStyle(document.documentElement).getPropertyValue('--ok').trim():(w.klass==='camera'||w.klass==='drone')?'#da3633':'#7a7a7a'})});
 const b=L.ble||{trackers:[],drones:[]};
 b.trackers.forEach(t=>out.push({id:t.addr,label:t.label,m:rssiToM(t.rssi,-59),col:d.state.tracker.level==='alert'?'#da3633':'#d29922',pulse:1}));
 b.drones.forEach(t=>out.push({id:t.addr,label:'DRONE',m:rssiToM(t.rssi,-59),col:'#da3633',tri:1,pulse:1}));
 return out}
function drawRadar(d){const c=document.getElementById('radar'),x=c.getContext('2d'),W=c.width,cx=W/2,R=W/2-24;
 x.clearRect(0,0,W,W);const dark=matchMedia('(prefers-color-scheme: dark)').matches;
 const line=dark?'#30363d':'#c9d1d9',txt=dark?'#7a7a7a':'#59636e';
 x.strokeStyle=line;x.fillStyle=txt;x.font='20px sans-serif';
 [[.33,'very close'],[.66,'close'],[1,'far']].forEach(([f,l])=>{x.beginPath();x.arc(cx,cx,R*f,0,7);x.stroke();x.fillText(l,cx+6,cx-R*f+20)});
 x.beginPath();x.moveTo(cx-R,cx);x.lineTo(cx+R,cx);x.moveTo(cx,cx-R);x.lineTo(cx,cx+R);x.stroke();
 const t=Date.now()/1000;
 x.fillStyle='#58a6ff';x.fillRect(cx-7,cx-7,14,14);   // this computer
 blips(d).forEach(p=>{const a=(hash(p.id)%3600)/3600*2*Math.PI,r=R*rpos(p.m);
  const px=cx+r*Math.cos(a),py=cx+r*Math.sin(a);x.fillStyle=p.col;x.strokeStyle=p.col;
  if(p.pulse){x.globalAlpha=.35;x.beginPath();x.arc(px,py,10+8*Math.abs(Math.sin(t*2)),0,7);x.fill();x.globalAlpha=1}
  x.beginPath();if(p.tri){x.moveTo(px,py-11);x.lineTo(px+10,py+8);x.lineTo(px-10,py+8);x.closePath()}else x.arc(px,py,7,0,7);x.fill();
  x.fillStyle=txt;x.font='17px sans-serif';x.fillText((p.label||'').slice(0,16),px+11,py+5)})}
function toM(lat,lon,H){const k=111320;return [(lon-H.lon)*k*Math.cos(H.lat*Math.PI/180),(lat-H.lat)*k]}
function drawDrone(d){const fixes=[].concat(...Object.values(d.live.drone_fixes||{})).filter(f=>f.lat),H=d.home;
 const card=document.getElementById('dmapcard');if(!fixes.length||!H){card.style.display='none';return}
 card.style.display='block';const c=document.getElementById('dmap'),x=c.getContext('2d'),W=c.width,Hh=c.height;
 x.clearRect(0,0,W,Hh);const dark=matchMedia('(prefers-color-scheme: dark)').matches,txt=dark?'#7a7a7a':'#59636e';
 let pts=[];fixes.forEach(f=>{pts.push(toM(f.lat,f.lon,H));if(f.op_lat)pts.push(toM(f.op_lat,f.op_lon,H))});
 const maxd=Math.max(100,...pts.map(p=>Math.hypot(p[0],p[1])))*1.25,sc=Math.min(W,Hh)/2/maxd,cx=W/2,cy=Hh/2;
 x.strokeStyle=dark?'#30363d':'#c9d1d9';x.fillStyle=txt;x.font='16px sans-serif';
 [.25,.5,1].forEach(f=>{x.beginPath();x.arc(cx,cy,maxd*f*sc,0,7);x.stroke();x.fillText(Math.round(maxd*f)+' m',cx+4,cy-maxd*f*sc+16)});
 x.fillText('N',cx-5,18);x.fillStyle='#58a6ff';x.fillRect(cx-7,cy-7,14,14);x.fillStyle=txt;x.fillText('HOME',cx+10,cy+4);
 let info=[];fixes.forEach(f=>{const [mx,my]=toM(f.lat,f.lon,H),px=cx+mx*sc,py=cy-my*sc,dist=Math.round(Math.hypot(mx,my));
  const brg=Math.round((Math.atan2(mx,my)*180/Math.PI+360)%360);x.fillStyle='#da3633';x.beginPath();x.moveTo(px,py-12);x.lineTo(px+11,py+9);x.lineTo(px-11,py+9);x.closePath();x.fill();
  if(f.op_lat){const [ox,oy]=toM(f.op_lat,f.op_lon,H);x.fillStyle='#d29922';x.beginPath();x.arc(cx+ox*sc,cy-oy*sc,7,0,7);x.fill();x.strokeStyle='#d29922';x.beginPath();x.moveTo(px,py);x.lineTo(cx+ox*sc,cy-oy*sc);x.stroke()}
  info.push(`Drone ${E(f.id)}: ${dist} m ${['N','NE','E','SE','S','SW','W','NW'][Math.round(brg/45)%8]} of home, alt ${f.alt??'?'} m`+(f.op_lat?' (amber dot = operator)':'')+` - <a href="https://www.openstreetmap.org/?mlat=${f.lat}&mlon=${f.lon}#map=17/${f.lat}/${f.lon}" target=_blank>open in map</a>`)});
 dinfo.innerHTML=info.join('<br>')}
async function load(){try{const d=await (await fetch('/api/status')).json();LAST=d;MY=new Set(d.my_ssids||[]);drawRadar(d);drawDrone(d);
document.getElementById('t').textContent=new Date(d.now*1000).toLocaleTimeString();
banner(d);tiles.innerHTML=Object.values(d.state).map(s=>`<div class="tile ${s.level}"><b>${ICON[s.level]} ${s.level.toUpperCase()} · ${E(s.title)}</b><span>${E(s.msg)}</span></div>`).join('');
ev.innerHTML=d.events.map(e=>`<tr class="e-${e.level}"><td>${new Date(e.ts*1000).toLocaleTimeString()}</td><td>${e.level}</td><td>${e.domain}</td><td>${E(e.msg)}</td></tr>`).join('')||'<tr><td class=m>nothing yet</td></tr>';
wifi.innerHTML=(d.live.wifi||[]).map(w=>`<tr><td>${E(w.ssid)}</td><td>${w.bssid}</td><td>${w.signal} dBm</td><td>${E(w.vendor)}</td><td>${w.klass}</td><td>${w.ssid&&w.ssid!=='(hidden)'?(MY.has(w.ssid)?`<b>(yours)</b> <button class=s onclick="post('/api/mynet?on=0&ssid='+encodeURIComponent(this.dataset.s))" data-s="${E(w.ssid).replace(/"/g,'&quot;')}">not mine</button>`:`<button class=s onclick="post('/api/mynet?on=1&ssid='+encodeURIComponent(this.dataset.s))" data-s="${E(w.ssid).replace(/"/g,'&quot;')}">this is my network</button>`):''}</td></tr>`).join('');
lan.innerHTML=(d.live.lan||[]).map(w=>`<tr><td>${w.ip}</td><td>${w.mac}</td><td>${E(w.vendor)}</td><td>${w.klass}${w.gateway?' (router)':''}</td><td>${Object.values(w.ports).join(',')}</td><td>${w.trusted?'<b>(known)</b> ':''}<button class=s onclick="post('/api/trust?on=${w.trusted?0:1}&mac=${w.mac}')">${w.trusted?'not known':'I know this device'}</button></td></tr>`).join('');
const b=d.live.ble||{trackers:[],drones:[]};
ble.innerHTML=[...b.drones.map(x=>['DRONE',x]),...b.trackers.map(x=>['tracker',x])].map(([k,x])=>`<tr><td>${k}${x.mine?' <b>(yours)</b>':''}</td><td>${E(x.label)}</td><td>${x.addr}</td><td>${x.rssi} dBm</td><td>${x.seen_s}s</td><td>${k==='tracker'?`<button class=s onclick="mine('${x.addr}',${x.mine?0:1})">${x.mine?'not mine':'this is mine'}</button>`:''}</td></tr>`).join('')||'<tr><td class=m>none</td></tr>';
}catch(e){}}
load();setInterval(load,2500);setInterval(()=>{if(LAST)drawRadar(LAST)},120);</script>"""


def serve(eng, host="127.0.0.1", port=8777, token=None):
    import hmac
    from http.cookies import SimpleCookie
    from urllib.parse import urlparse, parse_qs

    class H(BaseHTTPRequestHandler):
        def _host_ok(self):
            """Without a token (localhost mode) only accept Host: 127.0.0.1/localhost - blocks DNS rebinding."""
            if token:
                return True
            h = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            return h in ("127.0.0.1", "localhost", "::1")

        def _authed(self):
            if not self._host_ok():
                return False
            if not token:
                return True
            q = parse_qs(urlparse(self.path).query).get("k", [""])[0]
            if hmac.compare_digest(q.encode(), token.encode()):
                return True
            try:
                ck = SimpleCookie(self.headers.get("Cookie", ""))
                v = ck["hw_k"].value if "hw_k" in ck else ""
            except Exception:
                v = ""
            return hmac.compare_digest(v.encode(), token.encode())

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            b = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            path = urlparse(self.path).path
            if not self._authed():
                return self._send(401, "Locked. Open the full link printed by n0rma (it ends in ?k=...).", "text/plain")
            if path == "/api/status":
                self._send(200, json.dumps(eng.snapshot(), default=str))
            elif path == "/":
                b = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                if token:
                    self.send_header("Set-Cookie", f"hw_k={token}; Path=/; Max-Age=31536000; SameSite=Strict; HttpOnly")
                self.end_headers()
                self.wfile.write(b)
            else:
                self._send(404, "{}")

        def do_POST(self):
            if not self._authed() or self.headers.get("X-Homewatch") != "1":
                return self._send(403, "{}")  # custom header forces a CORS preflight -> cross-site POSTs die
            if self.path.startswith("/api/mine"):
                q = parse_qs(urlparse(self.path).query)
                addr = (q.get("addr", [""])[0]).upper()
                if not re.fullmatch(r"[0-9A-F]{2}(:[0-9A-F]{2}){5}", addr):
                    return self._send(400, '{"error":"bad address"}')
                cur = set(eng.db.kv_get("ble_ignore", []))
                (cur.add if q.get("on", ["1"])[0] == "1" else cur.discard)(addr)
                eng.db.kv_set("ble_ignore", sorted(cur))
                return self._send(200, '{"ok":true}')
            if self.path.startswith("/api/trust"):
                q = parse_qs(urlparse(self.path).query)
                mac = (q.get("mac", [""])[0]).lower()
                if not re.fullmatch(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}", mac):
                    return self._send(400, '{"error":"bad mac"}')
                eng.db.exec("UPDATE devices SET trusted=? WHERE mac=?", (1 if q.get("on", ["1"])[0] == "1" else 0, mac))
                return self._send(200, '{"ok":true}')
            if self.path.startswith("/api/mynet"):
                from .core import load_config, save_config
                q = parse_qs(urlparse(self.path).query)
                ssid = q.get("ssid", [""])[0]
                if not ssid or ssid == "(hidden)" or len(ssid.encode()) > 32 or any(ord(c) < 32 for c in ssid):
                    return self._send(400, '{"error":"bad ssid"}')
                cfg = load_config()
                cur = set(cfg.get("my_ssids", []))
                (cur.add if q.get("on", ["1"])[0] == "1" else cur.discard)(ssid)
                cfg["my_ssids"] = sorted(cur)
                save_config(cfg)
                return self._send(200, '{"ok":true}')
            if self.path == "/api/beep":
                eng.beep("dashboard")
                eng.emit("host", "info", "beep", "x", "Sensor beep logged", cooldown=0)
                self._send(200, '{"ok":true}')
            else:
                self._send(404, "{}")

    srv = ThreadingHTTPServer((host, port), H)
    threading.Thread(target=srv.serve_forever, daemon=True, name="web").start()
    return srv
