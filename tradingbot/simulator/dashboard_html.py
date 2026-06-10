"""Single-page dashboard, embedded so a one-file .exe needs no data files."""

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><title>ctabot simulator</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#0d1117;--panel:#161b22;--border:#30363d;--text:#e6edf3;--dim:#8b949e;
      --green:#3fb950;--red:#f85149;--accent:#58a6ff;--amber:#d29922}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:14px/1.45 'Segoe UI',system-ui,sans-serif;padding:16px}
h1{font-size:18px;font-weight:600}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:700;
       letter-spacing:.08em;margin-left:10px;vertical-align:2px}
.badge.live{background:#1f6feb33;color:var(--accent);border:1px solid var(--accent)}
.badge.replay{background:#d2992233;color:var(--amber);border:1px solid var(--amber)}
.topbar{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:14px}
.topbar .spacer{flex:1}
.topbar .date{color:var(--dim);font-size:13px}
button{background:var(--panel);color:var(--text);border:1px solid var(--border);
       border-radius:6px;padding:6px 14px;cursor:pointer;font-size:13px}
button:hover{border-color:var(--accent)}
input[type=range]{accent-color:var(--accent);width:140px;vertical-align:middle}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:10px 14px}
.card .label{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.06em}
.card .value{font-size:20px;font-weight:650;margin-top:2px;font-variant-numeric:tabular-nums}
.card .sub{font-size:12px;color:var(--dim);font-variant-numeric:tabular-nums}
.pos{color:var(--green)}.neg{color:var(--red)}
.row{display:grid;grid-template-columns:2fr 1fr;gap:14px;margin-bottom:14px}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:14px}
.panel h2{font-size:13px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
th{color:var(--dim);text-align:right;font-weight:500;padding:4px 8px;border-bottom:1px solid var(--border)}
td{padding:4px 8px;text-align:right;border-bottom:1px solid #21262d}
th:first-child,td:first-child{text-align:left}
.fills{max-height:300px;overflow-y:auto;font-size:12px}
.fills div{padding:3px 0;border-bottom:1px solid #21262d;color:var(--dim)}
.fills b{color:var(--text)}
.footer{color:var(--dim);font-size:11px;margin-top:12px;line-height:1.6}
.err{color:var(--red);font-size:12px}
@media(max-width:900px){.row{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="topbar">
  <h1>ctabot <span style="color:var(--dim)">paper-trading simulator</span><span id="mode" class="badge replay">—</span></h1>
  <span class="date" id="date">—</span><span class="err" id="err"></span>
  <div class="spacer"></div>
  <span id="speedwrap" style="display:none">
    <span class="date">speed <b id="speedval">25</b> days/s</span>
    <input type="range" id="speed" min="0" max="8" step="0.25" value="4.64">
  </span>
  <button id="pause">⏸ pause</button>
</div>

<div class="grid" id="kpis"></div>

<div class="row">
  <div class="panel"><h2>Equity vs S&P 500 (same capital, buy &amp; hold futures)</h2>
    <canvas id="chart" height="110"></canvas></div>
  <div class="panel"><h2>Net exposure by asset class (× equity)</h2>
    <canvas id="expo" height="220"></canvas>
    <div class="footer" id="expnote"></div></div>
</div>

<div class="row">
  <div class="panel"><h2>Open positions</h2>
    <table id="postable"><thead><tr>
      <th>instrument</th><th>class</th><th>contracts</th><th>price</th>
      <th>notional</th><th>open P&amp;L</th><th>forecast</th>
    </tr></thead><tbody></tbody></table></div>
  <div class="panel"><h2>Recent fills</h2><div class="fills" id="fills"></div></div>
</div>

<div class="footer">
Paper simulation — no real orders are sent anywhere. Replay mode runs the validated
backtest bar-by-bar with contract-level accounting; live mode trades the trend sleeve
on delayed Yahoo quotes (no curve data → no carry; continuous quotes jump at contract
rolls, adding noise to live marks). Futures P&amp;L is excess of cash; the S&amp;P line is
the same capital in buy-and-hold S&amp;P futures for a like-for-like comparison. Costs:
half-spread + $1.50/contract per trade + pro-rated roll costs. Market impact and
capacity are NOT modelled — multi-decade compounding at fixed percentage risk grows
positions far beyond what real markets would absorb.
</div>

<script>
const $=id=>document.getElementById(id);
const fmt$=v=>v==null?"—":(v<0?"-$":"$")+Math.abs(v).toLocaleString(undefined,{maximumFractionDigits:0});
const fmtM=v=>v==null?"—":(v<0?"-$":"$")+(Math.abs(v)>=1e6?(Math.abs(v)/1e6).toFixed(2)+"M":Math.abs(v).toLocaleString(undefined,{maximumFractionDigits:0}));
const pct=v=>v==null?"—":(v*100).toFixed(2)+"%";
const num=(v,d=2)=>v==null?"—":v.toFixed(d);
const cls=v=>v==null?"":(v>=0?"pos":"neg");

let chart=null, expo=null, paused=false;

function kpiCard(label,value,klass="",sub=""){
  return `<div class="card"><div class="label">${label}</div>
    <div class="value ${klass}">${value}</div><div class="sub">${sub}</div></div>`;
}

function render(s){
  const k=s.kpis, m=s.meta;
  $("mode").textContent=m.mode.toUpperCase()+" · "+m.preset;
  $("mode").className="badge "+m.mode;
  const prog=m.progress||{};
  $("date").textContent=(prog.date?("as of "+prog.date):"warming up")+
    (prog.total?` · bar ${prog.index+1}/${prog.total}`:"")+(m.finished?" · FINISHED":"");
  $("err").textContent=m.error?("feed: "+m.error):"";
  $("speedwrap").style.display=m.mode==="replay"?"inline":"none";
  paused=m.paused; $("pause").textContent=paused?"▶ resume":"⏸ pause";

  $("kpis").innerHTML=
    kpiCard("Equity",fmtM(k.equity),"",`start ${fmtM(k.capital0)}`)+
    kpiCard("Total P&L",fmtM(k.total_pnl),cls(k.total_pnl),pct(k.total_return))+
    kpiCard("Today",fmtM(k.day_pnl),cls(k.day_pnl))+
    kpiCard("S&P 500 same capital",fmtM(k.benchmark_equity),"",pct(k.benchmark_return))+
    kpiCard("vs S&P 500",pct(k.vs_benchmark),cls(k.vs_benchmark),"of starting capital")+
    kpiCard("Sharpe (realised)",num(k.sharpe),cls(k.sharpe),"ann. vol "+pct(k.ann_vol))+
    kpiCard("Max drawdown",pct(k.max_drawdown),"neg")+
    kpiCard("Gross exposure",num(k.gross_exposure_x,2)+"×","",`margin est ${fmtM(k.margin_est)}`)+
    kpiCard("Costs paid",fmtM(k.costs_paid),"",k.n_fills+" fills");

  const labels=s.equity_series.map(p=>p.ts.slice(0,10));
  const eq=s.equity_series.map(p=>p.equity);
  const bn=s.equity_series.map(p=>p.benchmark);
  if(!chart){
    chart=new Chart($("chart"),{type:"line",data:{labels,datasets:[
      {label:"strategy",data:eq,borderColor:"#58a6ff",backgroundColor:"#58a6ff22",borderWidth:1.8,pointRadius:0,fill:true},
      {label:"S&P 500",data:bn,borderColor:"#8b949e",borderWidth:1.2,pointRadius:0,borderDash:[5,4]}]},
      options:{animation:false,responsive:true,interaction:{mode:"index",intersect:false},
        plugins:{legend:{labels:{color:"#8b949e"}}},
        scales:{x:{ticks:{color:"#8b949e",maxTicksLimit:10},grid:{color:"#21262d"}},
                y:{ticks:{color:"#8b949e",callback:v=>fmtM(v)},grid:{color:"#21262d"}}}}});
  } else {
    chart.data.labels=labels;
    chart.data.datasets[0].data=eq; chart.data.datasets[1].data=bn;
    chart.update("none");
  }

  const ce=s.class_exposure, names=Object.keys(ce).sort();
  const vals=names.map(n=>ce[n]);
  if(!expo){
    expo=new Chart($("expo"),{type:"bar",data:{labels:names,datasets:[{data:vals,
      backgroundColor:vals.map(v=>v>=0?"#3fb95088":"#f8514988"),borderColor:vals.map(v=>v>=0?"#3fb950":"#f85149"),borderWidth:1}]},
      options:{animation:false,indexAxis:"y",plugins:{legend:{display:false}},
        scales:{x:{ticks:{color:"#8b949e",callback:v=>(v*100).toFixed(0)+"%"},grid:{color:"#21262d"}},
                y:{ticks:{color:"#8b949e"},grid:{display:false}}}}});
  } else {
    expo.data.labels=names; expo.data.datasets[0].data=vals;
    expo.data.datasets[0].backgroundColor=vals.map(v=>v>=0?"#3fb95088":"#f8514988");
    expo.data.datasets[0].borderColor=vals.map(v=>v>=0?"#3fb950":"#f85149");
    expo.update("none");
  }
  $("expnote").textContent="net long/short notional per class, fraction of equity";

  $("postable").querySelector("tbody").innerHTML=s.positions.map(p=>`<tr>
    <td>${p.instrument}</td><td>${p.class}</td>
    <td>${p.contracts>0?"+":""}${p.contracts}</td><td>${p.price}</td>
    <td>${fmt$(p.notional)}</td>
    <td class="${cls(p.open_pnl)}">${fmt$(p.open_pnl)}</td>
    <td>${p.forecast==null?"—":p.forecast}</td></tr>`).join("");

  $("fills").innerHTML=s.fills.map(f=>`<div><b>${f.ts.slice(0,10)}</b>
    ${f.contracts>0?"<b class='pos'>BUY</b>":"<b class='neg'>SELL</b>"}
    ${Math.abs(f.contracts)} <b>${f.instrument}</b> @ ${f.price}
    <span>cost ${fmt$(f.cost_usd)}</span></div>`).join("");
}

async function tick(){
  try{const r=await fetch("/api/state");render(await r.json());}
  catch(e){$("err").textContent="connection lost — retrying";}
}
async function control(action,value){
  await fetch("/api/control",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({action,value})});
  tick();
}
$("pause").onclick=()=>control(paused?"resume":"pause");
$("speed").oninput=e=>{const v=Math.round(Math.pow(2,parseFloat(e.target.value))*4)/4;
  $("speedval").textContent=v;control("speed",v);};
tick(); setInterval(tick,800);
</script>
</body></html>
"""
