"""
Build ui/case_view.html — a calm, one-case-at-a-time case file (standalone, offline, no CDN).
Reads cases/*.json and ui/traces/*.json.   python ui/build_case_view.py
"""
import glob, json, os

cases = {os.path.basename(f)[:-5]: json.load(open(f, encoding='utf-8')) for f in sorted(glob.glob('cases/*.json'))}
traces = {os.path.basename(f)[:-5]: json.load(open(f, encoding='utf-8')) for f in sorted(glob.glob('ui/traces/*.json'))}
data = json.dumps({'cases': cases, 'traces': traces}, default=str).replace('</', '<\\/')

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Fraud Detection Agent · Case file</title>
<style>
:root{--bg:#0e1116;--panel:#151a22;--line:#262d38;--ink:#e8eaee;--dim:#98a1b0;--accent:#6ea8fe;
--fraud:#ff6b6b;--legit:#4cd4a0;--unc:#f7b955;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 var(--sans)}
:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
.wrap{max-width:860px;margin:0 auto;padding:28px 22px 80px}
header{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
.brand{font-weight:700;letter-spacing:.2px}.brand small{display:block;color:var(--dim);font-weight:400;font-size:12px}
.bar{height:3px;border-radius:3px;background:linear-gradient(90deg,var(--accent),#b18cff);margin:14px 0 26px;width:120px}
select{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 12px;font:14px var(--sans)}
.nav{display:flex;gap:8px}.nav button{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 12px;cursor:pointer}
h1{font-size:30px;margin:0 0 4px}.trigger{color:var(--dim);margin:0 0 20px}
.badge{display:inline-block;padding:3px 12px;border-radius:99px;font-size:13px;font-weight:600;border:1px solid currentColor}
.fraud{color:var(--fraud)}.legitimate{color:var(--legit)}.uncertain{color:var(--unc)}
section{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin-bottom:16px}
h2{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin:0 0 14px;font-weight:600}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}
.stat b{display:block;font-size:22px}.stat span{color:var(--dim);font-size:13px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.cols h3{font-size:13px;color:var(--dim);margin:0 0 8px;font-weight:600}
ol{margin:0;padding-left:20px}li{margin-bottom:8px}
.route{font:11px var(--mono);padding:1px 6px;border-radius:4px;border:1px solid var(--line);margin-left:6px;color:var(--dim)}
.route.L1{color:var(--unc);border-color:#5a4a26}.route.L2{color:var(--fraud);border-color:#5a2c2c}
.why{color:var(--dim);font-size:13px}
.change{margin-top:14px;padding:12px 14px;border-radius:8px;background:#10141b;border-left:3px solid var(--accent);font-size:14px}
.ev{padding:8px 0;border-bottom:1px solid var(--line)}.ev:last-child{border:0}
.tag{font:11px var(--mono);color:var(--accent);margin-right:8px;text-transform:uppercase}
.sar{white-space:pre-wrap}
details{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 22px;margin-bottom:12px}
summary{cursor:pointer;color:var(--dim);font-size:13px;letter-spacing:.08em;text-transform:uppercase}
.row{font-size:13px;padding:5px 0;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.row:last-child{border:0}
.mono{font-family:var(--mono);font-size:12.5px}
@media (max-width:640px){.cols{grid-template-columns:1fr}h1{font-size:24px}}
</style></head><body><div class="wrap">
<header><div class="brand">Fraud Detection Agent<small>Fraud investigation · TigerGraph</small></div>
<div class="nav"><button id="prev">◀</button><select id="pick"></select><button id="next">▶</button></div></header>
<div class="bar"></div><div id="view"></div></div>
<script>
const D=__DATA__;const ids=Object.keys(D.cases).sort();const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const money=x=>'$'+Number(x).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const nice=s=>String(s).replace(/_/g,' ');
$('#pick').innerHTML=ids.map(i=>`<option value="${i}">${i} · ${D.cases[i].case.verdict}</option>`).join('');
const list=l=>`<ol>${l.map(x=>`<li><b>${nice(x.action)}</b><span class="route ${x.route}">${x.route}</span><div class="why">${esc(x.reason)}</div></li>`).join('')}</ol>`;
function show(id){const a=D.cases[id],t=D.traces[id]||{},c=a.case,v=c.verdict,n=a.next_best_actions;
const ev=c.evidence.filter(e=>e.source!=='document').slice(0,5);
const trig=t.flagged?`${nice(t.flagged.channel)} · ${money(t.flagged.amt)} · transaction ${t.flagged.id} · bank risk score ${t.flagged.risk_score}`:'';
$('#view').innerHTML=`
<h1>${id} <span class="badge ${v}">${v}</span></h1><p class="trigger">${esc(trig)}</p>
<section><h2>1 · Decision</h2><div class="stats">
<div class="stat"><b>${t.p_initial!=null?t.p_initial.toFixed(2):'–'} → <span class="${v}">${c.fraud_probability.toFixed(2)}</span></b><span>fraud probability before → after</span></div>
<div class="stat"><b>${money(c.exposure_usd)}</b><span>exposure</span></div>
<div class="stat"><b>${nice(c.pattern)}</b><span>pattern</span></div>
<div class="stat"><b>${nice(c.status)}</b><span>case status</span></div></div>
<p style="margin:16px 0 0">${esc(c.summary)}</p></section>
<section><h2>2 · What we recommend</h2>${a.evidence_requests.length?`<div class="cols">
<div><h3>Before evidence</h3>${list(n.initial)}</div><div><h3>After evidence</h3>${list(n.final)}</div></div>`:
`<h3 class="why" style="margin:0 0 8px">No extra evidence needed — evidence already settles the case</h3>${list(n.final)}`}
${a.evidence_requests.map(r=>`<div class="change"><b>Asked:</b> ${nice(r.type)} — ${esc(r.assumed_response)}</div>`).join('')}
${a.evidence_requests.length?`<div class="change"><b>What changed:</b> ${esc(n.what_changed)}</div>`:''}</section>
<section><h2>3 · Why</h2>${ev.map(e=>`<div class="ev"><span class="tag">${e.source}</span>${esc(e.claim)}</div>`).join('')}
${c.similar_prior_cases.length?`<div class="ev"><span class="tag">memory</span>Similar closed cases: ${c.similar_prior_cases.join(', ')}</div>`:''}</section>
<section><h2>4 · Report</h2>${a.sar.file?`<p><span class="badge fraud">SAR filed</span> <span class="why">${esc(a.sar.reason)}</span></p><div class="sar">${esc(a.sar.narrative)}</div>`:`<p class="why">No report required — ${esc(a.sar.reason)}</p>`}</section>
<details><summary>Investigation steps</summary>${(t.trace||[]).map(s=>`<div class="row"><b>${s.step}. ${nice(s.name)}</b> — <span class="why">${esc(s.detail)}</span></div>`).join('')}
<div class="row"><b>Stop</b> — <span class="why">${esc(a.stop_reason)}</span></div></details>
<details><summary>Permissions & decision history</summary>${(t.decision_history||[]).map(h=>`<div class="row mono">${esc(JSON.stringify(h))}</div>`).join('')}</details>
<details><summary>Affected transactions & connected cards</summary>
<div class="row">Transactions: <span class="mono">${c.affected_txn_ids.join(', ')||'none'}</span></div>
<div class="row">Connected cards: <span class="mono">${c.connected_card_ids.join(', ')||'none'}</span></div>
<div class="row">Devices: <span class="mono">${esc(c.connected_device_profiles.join(' ; ')||'none')}</span></div>
<div class="row">Graph case: <span class="mono">${esc(c.graph_case_id)}</span> · written to TigerGraph: ${c.written_to_graph}</div></details>
<details><summary>Tool calls (${a.tool_calls})</summary>${(t.tool_log||[]).map((x,i)=>`<div class="row mono">${i+1}. ${esc(x.tool)} ${esc(JSON.stringify(x.params))} → ${x.rows}</div>`).join('')}</details>`;
$('#pick').value=id;location.hash=id;window.scrollTo(0,0)}
$('#pick').onchange=e=>show(e.target.value);
const step=d=>{const i=ids.indexOf($('#pick').value);show(ids[(i+d+ids.length)%ids.length])};
$('#prev').onclick=()=>step(-1);$('#next').onclick=()=>step(1);
document.onkeydown=e=>{if(e.key==='ArrowRight')step(1);if(e.key==='ArrowLeft')step(-1)};
show(ids.includes(location.hash.slice(1))?location.hash.slice(1):ids[0]);
</script></body></html>"""
open('ui/case_view.html', 'w', encoding='utf-8').write(HTML.replace('__DATA__', data))
print('ui/case_view.html', len(cases), 'cases')
