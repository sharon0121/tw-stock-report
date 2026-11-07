"""
產生每日盤後報告 HTML（手機優先、快速閱讀版）
輸入：data/history/YYYY-MM-DD.json
輸出：public/YYYY-MM-DD.html、public/today.html
"""
import json, os, sys
from datetime import date, datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

PUBLIC_DIR = os.path.join(os.path.dirname(__file__), '..', 'public')
DATA_DIR   = os.path.join(os.path.dirname(__file__), '..', 'data', 'history')
os.makedirs(PUBLIC_DIR, exist_ok=True)

LESSONS = [
    ("均線 MA", "把過去 N 天收盤平均。股價站上均線偏多，均線向上彎動能增強。20 日看短期，60 日看中期。"),
    ("KD 指標", "K > 80 短期過熱，K < 20 超跌。K 線穿越 D 線向上為黃金交叉（買訊參考）。"),
    ("RSI", "衡量漲跌力道比率。RSI > 70 偏熱，< 30 偏冷。超買超賣須搭配其他指標確認。"),
    ("布林通道", "20 日均線上下各 2 倍標準差。股價觸上緣為壓力，觸下緣為支撐。通道收窄代表蓄勢。"),
    ("外資買賣超", "台股最大法人。連續買超代表長線資金流入。短期可能因避險、匯率賣出，不必過度恐慌。"),
    ("投信買賣超", "本土基金。投信與外資同向買超，訊號較強；方向相反代表多空分歧。"),
    ("季度收入年增率", "與去年同期比較的收入成長。正成長基本面向好，需連續 2～3 季確認趨勢。"),
    ("殖利率", "除息金額 ÷ 股價。高股息 ETF 重要指標。要分清楚是股價低還是配息多。"),
    ("支撐與壓力", "支撐是過去常有買盤的價位，壓力是常有賣盤的價位。跌破支撐、突破壓力都是關鍵訊號。"),
    ("風險警戒線", "近 60 日最低點。跌破代表中期下跌趨勢確立，建議等待止跌確認再行動。"),
]

def get_lesson(d):
    dt  = datetime.strptime(d, '%Y-%m-%d')
    idx = dt.timetuple().tm_yday % len(LESSONS)
    return LESSONS[idx]

def fmt(v, d=1):
    if v is None: return '—'
    if isinstance(v, str): return v
    try: return f'{float(v):,.{d}f}'
    except: return str(v)

def inst_short(v):
    if not v: return '—'
    try:
        v = int(v)
        sign = '+' if v > 0 else ''
        a = abs(v)
        if a >= 100_000_000: return f'{sign}{v/100_000_000:.1f}億'
        if a >= 10_000:      return f'{sign}{v/10_000:.0f}萬'
        return f'{sign}{v:,}'
    except: return str(v)

def chg_cls(v):
    try: return 'up' if float(v) > 0 else ('dn' if float(v) < 0 else '')
    except: return ''

def top_signal(signals):
    """取分數絕對值最大的一個訊號作為主要訊號標示"""
    if not signals:
        return ''
    best = max(signals, key=lambda x: abs(x.get('score', 0)))
    score = best.get('score', 0)
    label = best.get('label', '')
    cls = 'sig-pos' if score > 0 else 'sig-neg'
    return f'<div class="top-sig {cls}">{label}</div>'

_LIGHT_MAP = {'🟢': ('bull', '▲'), '🟡': ('neu', '—'), '🔴': ('bear', '▼')}

def light_disp(light):
    cls, arrow = _LIGHT_MAP.get(light, ('', light))
    if cls:
        return f'<span class="light light-{cls}">{arrow}</span>'
    return f'<span class="light">{light}</span>'

def card(s, prev_light):
    sid    = s['id']
    name   = s['name']
    is_etf = s['type'] == 'etf'
    light  = s['light']
    close  = s['close']
    chg    = s.get('change_pct', 0) or 0
    chg_str = f'{chg:+.2f}%'
    cls    = chg_cls(chg)

    changed   = prev_light and prev_light != light
    chg_badge = (f'<span class="badge-chg">'
                 f'{_LIGHT_MAP.get(prev_light,("",""))[1]}→{_LIGHT_MAP.get(light,("",""))[1]}'
                 f'</span>') if changed else ''
    heat       = s.get('heat_flag')
    heat_badge = ''
    if heat == 'overbought': heat_badge = '<span class="badge-heat hot">🔥 過熱</span>'
    elif heat == 'oversold': heat_badge = '<span class="badge-heat cold">🧊 超跌</span>'

    if light == '🟢':
        rec_badge = '<span class="rec-badge rec-buy">可買進</span>'
    elif light == '🔴':
        rec_badge = '<span class="rec-badge rec-sell">建議賣出</span>'
    else:
        rec_badge = ''

    type_badge = '<span class="type-etf">ETF</span>' if is_etf else '<span class="type-stk">個股</span>'

    # 主要訊號（最重要的一個）
    main_sig = top_signal(s.get('signals', []))

    # 壓力支撐價格條
    res  = s.get('resistance')
    sup  = s.get('support')
    risk = s.get('risk_level')
    try:
        lo  = float(risk or sup or close * 0.9)
        hi  = float(res or close * 1.1)
        pct = max(2, min(98, (float(close) - lo) / (hi - lo) * 100))
    except:
        pct = 50

    price_bar = f'''<div class="pbar">
  <div class="pbar-track"><div class="pbar-fill" style="width:{pct:.0f}%"></div>
    <div class="pbar-dot" style="left:calc({pct:.0f}% - 5px)"></div></div>
  <div class="pbar-labels">
    <span>⛔{fmt(risk)}</span><span>🔻{fmt(sup)}</span>
    <span class="cur">▲{fmt(close,1)}</span><span>🔺{fmt(res)}</span>
  </div>
</div>'''

    # 展開詳情
    inst   = s.get('inst_5d', {})
    fn     = inst.get('foreign_net', 0)
    tn     = inst.get('trust_net', 0)
    fn_cls = 'green' if fn > 0 else 'red'
    tn_cls = 'green' if tn > 0 else 'red'

    ma20d     = s.get('ma20_direction')
    ma20d_str = '↗上彎' if ma20d == 'up' else ('↘下彎' if ma20d == 'down' else '→持平')
    kk = s.get('kd_k'); kd = s.get('kd_d'); rsi = s.get('rsi')

    rev_html = ''
    if not is_etf:
        rv = s.get('rev_growth')
        if rv is not None:
            rv_cls = 'green' if rv > 0 else 'red'
            rev_html = f'<div class="chip {rv_cls}">收入 {rv*100:+.1f}%</div>'

    dy = s.get('div_yield')
    dy_html = f'<div class="chip">殖利率 {fmt(dy)}%</div>' if dy else ''

    sc = s.get('scenarios', [])
    sc_html = ''
    if sc:
        sc_html  = f'<div class="sc-row up">{sc[0]}</div>'
        if len(sc) > 1:
            sc_html += f'<div class="sc-row dn">{sc[1]}</div>'

    obs = s.get('observations', [])
    obs_html = ''.join(f'<li>{o}</li>' for o in obs)

    detail = f'''<div class="detail">
  <div class="d-row">
    <div class="d-col">
      <div class="d-label">均線</div>
      <div class="chips">
        <div class="chip">MA5 {fmt(s.get("ma5"),1)}</div>
        <div class="chip">MA20 {fmt(s.get("ma20"),1)}</div>
        <div class="chip">MA60 {fmt(s.get("ma60"),1)}</div>
        <div class="chip">{ma20d_str}</div>
      </div>
    </div>
    <div class="d-col">
      <div class="d-label">動能</div>
      <div class="chips">
        <div class="chip">KD {fmt(kk,0)}/{fmt(kd,0)}</div>
        <div class="chip">RSI {fmt(rsi,0)}</div>
        <div class="chip">布↑{fmt(s.get("bb_up"),1)}</div>
        <div class="chip">布↓{fmt(s.get("bb_low"),1)}</div>
      </div>
    </div>
  </div>
  <div class="d-row">
    <div class="d-col">
      <div class="d-label">法人 5 日</div>
      <div class="chips">
        <div class="chip {fn_cls}">外資 {inst_short(fn)}</div>
        <div class="chip {tn_cls}">投信 {inst_short(tn)}</div>
      </div>
    </div>
    <div class="d-col">
      <div class="d-label">基本面</div>
      <div class="chips">{rev_html}{dy_html}</div>
    </div>
  </div>
  <div class="d-label mt8">走勢情境</div>
  <div class="scenarios">{sc_html}</div>
  <div class="d-label mt8">觀察重點</div>
  <ul class="obs">{obs_html}</ul>
</div>'''

    card_cls = 'card changed' if changed else 'card'
    return f'''<div class="{card_cls}" data-sid="{sid}" data-name="{name}" data-light="{light}">
  <div class="card-top">
    <div class="ct-left">
      {light_disp(light)}
      <div class="name-row">
        {type_badge}<span class="sid">{sid}</span><span class="sname">{name}</span>
        {chg_badge}{heat_badge}{rec_badge}
      </div>
      <div class="conclusion">{s.get("conclusion","")}</div>
      {main_sig}
    </div>
    <div class="ct-right">
      <div class="close-price">{fmt(close,1)}</div>
      <div class="chg-val {cls}">{chg_str}</div>
      <div class="toggle-btn">詳情<span class="toggle-icon">＋</span></div>
    </div>
  </div>
  {price_bar}
  {detail}
</div>'''


CSS = '''
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f2f2f7;--card:#fff;--text:#1c1c1e;--sub:#8e8e93;
  --sep:#e5e5ea;--blue:#007aff;--green:#34c759;--red:#ff3b30;
  --yellow:#ff9500;--dot:#007aff;
}
@media(prefers-color-scheme:dark){
  :root{--bg:#000;--card:#1c1c1e;--text:#f5f5f7;--sub:#aeaeb2;--sep:#2c2c2e}
}
/* 強制深/淺色（覆蓋 media query） */
html.dark{--bg:#000;--card:#1c1c1e;--text:#f5f5f7;--sub:#aeaeb2;--sep:#2c2c2e}
html.light{--bg:#f2f2f7;--card:#fff;--text:#1c1c1e;--sub:#8e8e93;--sep:#e5e5ea}
html.dark .type-etf{background:#1a2a3a;color:#64b5f6}
html.dark .type-stk{background:#3a1a1a;color:#ef9a9a}
html.dark .badge-chg{background:#1a2240;color:#64b5f6}
html.dark .badge-heat.hot{background:#3a2000;color:#ffa726}
html.dark .badge-heat.cold{background:#002040;color:#64b5f6}
html.dark .chip{background:#2c2c2e}
html.dark .chip.green{background:#0a2a0a;color:#66bb6a}
html.dark .chip.red{background:#2a0a0a;color:#ef9a9a}
.theme-btn{background:none;border:none;font-size:18px;cursor:pointer;padding:4px 6px;line-height:1;border-radius:8px}
.theme-btn:hover{background:var(--sep)}
*{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;
  background:var(--bg);color:var(--text);
  max-width:480px;margin:0 auto;padding-bottom:48px;font-size:14px;
}
.hdr{
  background:var(--card);padding:10px 16px 12px;
  border-bottom:1px solid var(--sep);position:sticky;top:0;z-index:9;
}
.hdr-nav{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.nav-btn{
  background:var(--bg);border:1px solid var(--sep);color:var(--blue);
  font-size:13px;font-weight:600;padding:5px 12px;border-radius:8px;
  cursor:pointer;white-space:nowrap;
}
.nav-btn:disabled{color:var(--sub);cursor:default;opacity:.4}
.nav-today{
  font-size:12px;color:var(--sub);font-weight:600;
  text-decoration:none;padding:5px 8px;
}
.hdr-title{font-size:17px;font-weight:700;margin-bottom:8px}
.hdr-lights{display:flex;gap:6px;font-size:14px;font-weight:600}
.hdr-lights span{cursor:pointer;padding:5px 12px;border-radius:20px;transition:background .15s,opacity .15s;user-select:none}
.hdr-lights span:hover{opacity:.8}
.hdr-bull.active{background:rgba(224,53,53,.18)}
.hdr-neu.active{background:rgba(255,149,0,.18)}
.hdr-bear.active{background:rgba(0,170,98,.18)}
.hdr-changes{margin-top:6px;font-size:12px;color:var(--sub)}
.hdr-hint{margin-top:4px;font-size:11px;color:var(--sub)}
.group-label{
  font-size:11px;font-weight:700;color:var(--sub);letter-spacing:.5px;
  padding:12px 16px 4px;text-transform:uppercase
}
/* 兩欄 grid */
.card-grid{
  display:grid;grid-template-columns:1fr 1fr;
  gap:6px;padding:0 8px;
}
.card{
  background:var(--card);border-radius:12px;
  border:1.5px solid var(--sep);overflow:hidden;min-width:0;
}
.card.changed{border-color:var(--blue)}
/* 展開時佔滿整排 */
.card.open{grid-column:span 2}
.card-top{
  display:flex;justify-content:space-between;align-items:flex-start;
  padding:10px 10px 8px;cursor:pointer;gap:6px;
}
.ct-left{flex:1;min-width:0;overflow:hidden}
.ct-right{text-align:right;flex-shrink:0}
.light,.light-bull,.light-neu,.light-bear{font-size:20px;line-height:1;font-weight:800}
.light-bull{color:#e03535}
.light-neu{color:var(--yellow)}
.light-bear{color:#00aa62}
.hdr-bull{color:#e03535;font-weight:700}
.hdr-neu{color:var(--yellow);font-weight:700}
.hdr-bear{color:#00aa62;font-weight:700}
.rec-badge{font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;white-space:nowrap}
.rec-buy{background:rgba(255,59,48,.12);color:var(--red)}
.rec-sell{background:rgba(52,199,89,.12);color:var(--green)}
.name-row{display:flex;align-items:center;gap:4px;flex-wrap:wrap;margin:2px 0}
.sid{font-size:11px;color:var(--sub)}
.sname{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:80px}
.close-price{font-size:18px;font-weight:700;line-height:1.1}
.chg-val{font-size:12px;font-weight:600}
.chg-val.up{color:var(--red)}
.chg-val.dn{color:var(--green)}
.conclusion{font-size:11px;color:var(--sub);margin-top:3px;line-height:1.4;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
/* 展開後結論不截斷 */
.card.open .conclusion{display:block;-webkit-line-clamp:unset}
/* 主要訊號（一行） */
.top-sig{font-size:12px;font-weight:600;margin-top:5px}
.top-sig.sig-pos{color:var(--red)}
.top-sig.sig-neg{color:var(--green)}
.toggle-btn{font-size:12px;color:var(--blue);margin-top:6px;display:flex;align-items:center;gap:3px;font-weight:600;white-space:nowrap}
.toggle-icon{font-size:14px;transition:transform .2s;display:inline-block}
.card.open .toggle-icon{transform:rotate(45deg)}
.type-etf,.type-stk{font-size:10px;padding:1px 5px;border-radius:4px;font-weight:600}
.type-etf{background:#e8f4fd;color:#0277bd}
.type-stk{background:#fce4ec;color:#c62828}
@media(prefers-color-scheme:dark){
  .type-etf{background:#1a2a3a;color:#64b5f6}
  .type-stk{background:#3a1a1a;color:#ef9a9a}
}
.badge-chg{font-size:11px;background:#e8f0fe;color:var(--blue);padding:1px 6px;border-radius:10px;font-weight:600}
.badge-heat{font-size:11px;padding:1px 6px;border-radius:10px;font-weight:600}
.badge-heat.hot{background:#fff3e0;color:#e65100}
.badge-heat.cold{background:#e3f2fd;color:#0277bd}
@media(prefers-color-scheme:dark){
  .badge-chg{background:#1a2240;color:#64b5f6}
  .badge-heat.hot{background:#3a2000;color:#ffa726}
  .badge-heat.cold{background:#002040;color:#64b5f6}
}
.pbar{padding:0 14px 10px}
.pbar-track{position:relative;height:5px;background:var(--sep);border-radius:3px;margin-bottom:5px}
.pbar-fill{height:100%;background:linear-gradient(90deg,var(--green),var(--yellow),var(--red));border-radius:3px}
.pbar-dot{position:absolute;top:-4px;width:12px;height:12px;background:var(--dot);border:2px solid var(--card);border-radius:50%}
.pbar-labels{display:flex;justify-content:space-between;font-size:10px;color:var(--sub)}
.pbar-labels .cur{color:var(--text);font-weight:600}
.detail{display:none;padding:0 14px 14px;border-top:1px solid var(--sep)}
.card.open .detail{display:block}
.d-row{display:flex;gap:12px;margin-top:12px}
.d-col{flex:1;min-width:0}
.d-label{font-size:11px;font-weight:700;color:var(--sub);text-transform:uppercase;letter-spacing:.3px;margin-bottom:5px}
.d-label.mt8{margin-top:10px}
.chips{display:flex;flex-wrap:wrap;gap:4px}
.chip{font-size:12px;padding:3px 8px;border-radius:6px;background:var(--bg);color:var(--text);font-weight:500}
.chip.green{background:#e8f8ed;color:#1b5e20}
.chip.red{background:#fdecea;color:#b71c1c}
@media(prefers-color-scheme:dark){
  .chip{background:#2c2c2e}
  .chip.green{background:#0a2a0a;color:#66bb6a}
  .chip.red{background:#2a0a0a;color:#ef9a9a}
}
.scenarios{display:flex;flex-direction:column;gap:5px;margin-top:4px}
.sc-row{font-size:12px;padding:7px 10px;border-radius:7px;line-height:1.4}
.sc-row.up{background:rgba(52,199,89,.1);border-left:3px solid var(--green)}
.sc-row.dn{background:rgba(255,59,48,.1);border-left:3px solid var(--red)}
.obs{padding-left:16px;font-size:12px;color:var(--sub)}
.obs li{margin-bottom:3px;line-height:1.4}
.lesson{background:var(--card);margin:8px 8px 4px;border-radius:12px;padding:14px;border:1px solid var(--sep)}
.lesson-hd{font-size:11px;font-weight:700;color:var(--sub);letter-spacing:.5px;margin-bottom:5px}
.lesson-title{font-size:14px;font-weight:600;margin-bottom:4px}
.lesson-body{font-size:12px;color:var(--sub);line-height:1.6}
.disc{font-size:11px;color:var(--sub);text-align:center;padding:16px}
/* 搜尋欄 */
.search-wrap{padding:8px 8px 4px;position:sticky;top:var(--hdr-h,110px);z-index:8;background:var(--bg)}
.search-box{display:flex;align-items:center;background:var(--card);border:1.5px solid var(--sep);border-radius:10px;padding:0 10px;gap:6px}
.search-icon{font-size:14px;flex-shrink:0}
#search{flex:1;border:none;background:transparent;padding:10px 0;font-size:15px;color:var(--text);outline:none;min-width:0}
#search::placeholder{color:var(--sub);font-size:13px}
.clear-btn{background:none;border:none;color:var(--sub);font-size:16px;cursor:pointer;padding:4px;line-height:1}
.no-result{text-align:center;padding:32px 16px;color:var(--sub);font-size:14px}
.card.hidden{display:none}
.group-label.hidden{display:none}
'''

JS = '''
// 展開/收合（補償捲軸，讓卡片保持在同一視覺位置）
document.querySelectorAll('.card-top').forEach(el=>{
  el.addEventListener('click',()=>{
    const card = el.closest('.card');
    const before = card.getBoundingClientRect().top;
    card.classList.toggle('open');
    requestAnimationFrame(()=>{
      requestAnimationFrame(()=>{
        const after = card.getBoundingClientRect().top;
        window.scrollBy(0, after - before);
      });
    });
  });
});
document.querySelectorAll('.card.changed').forEach(c=>c.classList.add('open'));

// 深淺色切換
(function(){
  const btn  = document.getElementById('theme-toggle');
  const html = document.documentElement;
  function apply(t){
    html.classList.remove('dark','light');
    html.classList.add(t);
    btn.textContent = t==='dark' ? '🌙' : '☀️';
    localStorage.setItem('theme', t);
  }
  btn.addEventListener('click',()=>{
    apply((localStorage.getItem('theme')||'dark')==='dark' ? 'light' : 'dark');
  });
  // 初始圖示同步（class 已由 head script 設好）
  btn.textContent = (localStorage.getItem('theme')||'dark')==='dark' ? '🌙' : '☀️';
})();

// 搜尋 + 燈號篩選
const inp    = document.getElementById('search');
const clrBtn = document.getElementById('search-clear');
const noRes  = document.getElementById('no-result');
const grpE   = document.getElementById('grp-etf');
const grpS   = document.getElementById('grp-stock');
let activeLight = null;

function filterCards(){
  const q = inp.value.trim().toLowerCase();
  clrBtn.style.display = q ? 'block' : 'none';
  document.querySelectorAll('.card').forEach(c=>{
    const matchQ = !q
      || (c.dataset.sid  ||'').toLowerCase().includes(q)
      || (c.dataset.name ||'').toLowerCase().includes(q);
    const matchL = !activeLight || c.dataset.light === activeLight;
    const match  = matchQ && matchL;
    c.classList.toggle('hidden', !match);
    if(match && q) c.classList.add('open');
  });
  const anyEtf   = [...document.querySelectorAll('#grid-etf .card')].some(c=>!c.classList.contains('hidden'));
  const anyStock = [...document.querySelectorAll('#grid-stock .card')].some(c=>!c.classList.contains('hidden'));
  if(grpE) grpE.classList.toggle('hidden', !anyEtf);
  if(grpS) grpS.classList.toggle('hidden', !anyStock);
  document.getElementById('grid-etf').classList.toggle('hidden', !anyEtf);
  document.getElementById('grid-stock').classList.toggle('hidden', !anyStock);
  noRes.style.display = (!anyEtf && !anyStock) ? 'block' : 'none';
}

inp.addEventListener('input', filterCards);
clrBtn.addEventListener('click',()=>{ inp.value=''; filterCards(); inp.focus(); });

// 燈號篩選鈕
const LIGHT_MAP = {'hdr-bull':'🟢','hdr-neu':'🟡','hdr-bear':'🔴'};
document.querySelectorAll('.hdr-bull,.hdr-neu,.hdr-bear').forEach(btn=>{
  btn.addEventListener('click',()=>{
    const cls   = [...btn.classList].find(c=>LIGHT_MAP[c]);
    const light = LIGHT_MAP[cls];
    activeLight = (activeLight===light) ? null : light;
    document.querySelectorAll('.hdr-bull,.hdr-neu,.hdr-bear').forEach(b=>b.classList.remove('active'));
    if(activeLight) btn.classList.add('active');
    filterCards();
  });
});

// 導航：前一天
(function(){
  const d = new Date(window.__REPORT_DATE + 'T00:00:00');
  const avail = (window.__AVAILABLE_DATES || []);

  function prevTrade(dt){
    const p = new Date(dt); p.setDate(p.getDate()-1);
    while(p.getDay()===0||p.getDay()===6) p.setDate(p.getDate()-1);
    return p;
  }
  function fmt(dt){
    return dt.toISOString().slice(0,10);
  }

  const prevStr = fmt(prevTrade(d));
  const btnPrev = document.getElementById('nav-prev');

  if(avail.length && !avail.includes(prevStr)){
    btnPrev.style.display = 'none';
  } else {
    btnPrev.addEventListener('click',()=>{ location.href = prevStr+'.html'; });
  }
})();
'''

def generate(report, prev_report=None, available_dates=None):
    report_date = report['date']
    summary     = report.get('summary', {})
    stocks      = report['stocks']

    dt    = datetime.strptime(report_date, '%Y-%m-%d')
    wdays = ['一','二','三','四','五','六','日']
    date_disp = f'{dt.month}/{dt.day}（{wdays[dt.weekday()]}）'

    changed_names = []
    for sid, s in stocks.items():
        prev = (prev_report or {}).get('stocks', {}).get(sid, {})
        if prev and prev.get('light') != s.get('light'):
            changed_names.append(f'{sid} {s["name"]}')

    changes_html = ''
    if changed_names:
        changes_html = f'<div class="hdr-changes">⚡ 燈號異動：{"、".join(changed_names)}</div>'

    avail_js = json.dumps(available_dates or [])
    hdr = f'''<div class="hdr">
  <div class="hdr-nav">
    <button class="nav-btn" id="nav-prev">← 前一天</button>
    <a href="today.html" class="nav-today">今天</a>
    <div style="display:flex;gap:6px;align-items:center">
      <a href="guide.html" class="nav-today" style="color:var(--blue)">📚 指南</a>
      <button class="theme-btn" id="theme-toggle">🌙</button>
    </div>
  </div>
  <div class="hdr-title">📊 台股盤後報告 {date_disp}</div>
  <div class="hdr-lights">
    <span class="hdr-bull">▲ 可買進 {summary.get("green",0)}</span>
    <span class="hdr-neu">— 觀望 {summary.get("yellow",0)}</span>
    <span class="hdr-bear">▼ 建議賣出 {summary.get("red",0)}</span>
  </div>
  <div class="hdr-hint">多方=留意進場機會・注意=留意風險</div>
  {changes_html}
</div>
<script>window.__REPORT_DATE="{report_date}";window.__AVAILABLE_DATES={avail_js};</script>'''

    def sort_key(item):
        sid, s = item
        prev    = (prev_report or {}).get('stocks', {}).get(sid, {})
        changed = prev and prev.get('light') != s.get('light')
        order   = {'🟢': 0, '🟡': 1, '🔴': 2}
        return (0 if changed else 1, order.get(s.get('light', '🟡'), 1))

    sorted_items = sorted(stocks.items(), key=sort_key)

    etf_cards = stock_cards = ''
    for sid, s in sorted_items:
        prev_light = (prev_report or {}).get('stocks', {}).get(sid, {}).get('light')
        c = card(s, prev_light)
        if s['type'] == 'etf':
            etf_cards += c
        else:
            stock_cards += c

    lesson_title, lesson_body = get_lesson(report_date)

    return f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>台股盤後 {date_disp}</title>
<script>
(function(){{
  document.documentElement.classList.add(localStorage.getItem('theme')||'dark');
}})();
</script>
<style>{CSS}</style>
</head>
<body>
{hdr}
<div class="search-wrap">
  <div class="search-box">
    <span class="search-icon">🔍</span>
    <input id="search" type="search" placeholder="輸入代號或名稱，例如 2330 或台積電" autocomplete="off">
    <button id="search-clear" class="clear-btn" style="display:none">✕</button>
  </div>
</div>
<div id="no-result" class="no-result" style="display:none">找不到符合的股票</div>
<div id="grp-etf" class="group-label">📦 ETF</div>
<div class="card-grid" id="grid-etf">
{etf_cards}
</div>
<div id="grp-stock" class="group-label">📈 個股</div>
<div class="card-grid" id="grid-stock">
{stock_cards}
</div>
<div class="lesson">
  <div class="lesson-hd">📚 指標小學堂</div>
  <div class="lesson-title">{lesson_title}</div>
  <div class="lesson-body">{lesson_body}</div>
</div>
<div class="disc">價位與燈號為指標推算的參考值，不保證走勢，投資請自行判斷。</div>
<script>{JS}</script>
</body>
</html>'''


def generate_guide():
    """產生 public/guide.html 指標教學頁"""
    GUIDE_CSS = '''
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f2f2f7;--card:#fff;--text:#1c1c1e;--sub:#8e8e93;
  --sep:#e5e5ea;--blue:#007aff;--green:#34c759;--red:#ff3b30;
  --yellow:#ff9500;
}
@media(prefers-color-scheme:dark){
  :root{--bg:#000;--card:#1c1c1e;--text:#f5f5f7;--sub:#aeaeb2;--sep:#2c2c2e}
}
html.dark{--bg:#000;--card:#1c1c1e;--text:#f5f5f7;--sub:#aeaeb2;--sep:#2c2c2e}
html.light{--bg:#f2f2f7;--card:#fff;--text:#1c1c1e;--sub:#8e8e93;--sep:#e5e5ea}
body{
  font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;
  background:var(--bg);color:var(--text);
  max-width:480px;margin:0 auto;padding-bottom:48px;font-size:14px;
}
.hdr{
  background:var(--card);padding:12px 16px;
  border-bottom:1px solid var(--sep);position:sticky;top:0;z-index:9;
  display:flex;align-items:center;justify-content:space-between;
}
.hdr-left{display:flex;align-items:center;gap:10px}
.back-btn{
  background:var(--bg);border:1px solid var(--sep);color:var(--blue);
  font-size:13px;font-weight:600;padding:5px 12px;border-radius:8px;cursor:pointer;
  text-decoration:none;white-space:nowrap;
}
.hdr-title{font-size:17px;font-weight:700}
.theme-btn{background:none;border:none;font-size:18px;cursor:pointer;padding:4px 6px;border-radius:8px}
.theme-btn:hover{background:var(--sep)}
.section{margin:12px 10px 0;background:var(--card);border-radius:14px;overflow:hidden}
.sec-hd{
  padding:12px 14px 8px;font-size:13px;font-weight:700;
  border-bottom:1px solid var(--sep);display:flex;align-items:center;gap:6px;
}
.sec-sub{font-size:11px;color:var(--sub);font-weight:400;margin-left:4px}
.score-box{padding:12px 14px;display:flex;gap:8px;flex-wrap:wrap}
.score-pill{
  display:flex;align-items:center;gap:5px;padding:6px 12px;
  border-radius:20px;font-size:13px;font-weight:600;
}
.pill-g{background:rgba(255,59,48,.1);color:#c0392b}
.pill-y{background:rgba(255,149,0,.1);color:#d4a017}
.pill-r{background:rgba(52,199,89,.1);color:#27ae60}
html.dark .pill-g{background:rgba(192,57,43,.2)}
html.dark .pill-y{background:rgba(212,160,23,.2)}
html.dark .pill-r{background:rgba(39,174,96,.2)}
.arrow{font-size:16px}
.ind-list{padding:0 14px 10px}
.ind-item{padding:10px 0;border-bottom:1px solid var(--sep)}
.ind-item:last-child{border-bottom:none}
.ind-name{font-size:13px;font-weight:700;margin-bottom:4px;display:flex;align-items:center;gap:6px}
.ind-desc{font-size:12px;color:var(--sub);line-height:1.6;margin-bottom:6px}
.sig-row{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
.sig{font-size:11px;font-weight:600;padding:3px 10px;border-radius:12px}
.sig-pos{background:rgba(255,59,48,.1);color:#c0392b}
.sig-neg{background:rgba(52,199,89,.1);color:#27ae60}
.sig-neu{background:rgba(142,142,147,.12);color:var(--sub)}
html.dark .sig-pos{background:rgba(192,57,43,.2)}
html.dark .sig-neg{background:rgba(39,174,96,.2)}
html.dark .sig-neu{background:rgba(142,142,147,.15)}
.heat-box{padding:10px 14px 12px;display:flex;gap:8px;flex-wrap:wrap}
.heat-pill{font-size:12px;font-weight:600;padding:5px 12px;border-radius:12px;line-height:1.5}
.heat-hot{background:#fff3e0;color:#e65100}
.heat-cold{background:#e3f2fd;color:#0277bd}
html.dark .heat-hot{background:#3a2000;color:#ffa726}
html.dark .heat-cold{background:#002040;color:#64b5f6}
.heat-desc{font-size:11px;color:var(--sub);margin-top:3px}
.sig-ref{background:rgba(0,122,255,.1);color:var(--blue)}
html.dark .sig-ref{background:rgba(0,122,255,.2)}
.sec-hd-ref{padding:12px 14px 8px;font-size:13px;font-weight:700;
  border-bottom:1px solid var(--sep);display:flex;align-items:center;gap:6px;
  color:var(--blue)}
.note{margin:12px 10px;padding:12px 14px;background:var(--card);border-radius:14px;
  font-size:12px;color:var(--sub);line-height:1.7}
.note strong{color:var(--text)}
'''

    # 本系統使用的指標
    indicators_active = [
        {
            'emoji': '📊', 'name': 'MA20（20日均線）', 'term': '短期・計分',
            'desc': '計算過去 20 個交易日收盤價的平均值。股價站上均線代表短期買盤強，跌破則買盤減弱。均線方向（上彎／下彎）反映近期動能變化。',
            'pos': ['📈 股價站上 MA20（+1）', '↗ MA20 均線上彎（+1）'],
            'neg': ['📉 股價跌破 MA20（−1）', '↘ MA20 均線下彎（−1）'],
        },
        {
            'emoji': '📊', 'name': 'MA60（60日均線）', 'term': '中期・計分',
            'desc': '計算過去 60 個交易日的均價，代表中期市場趨勢。股價站上 MA60 為中期偏多，跌破則中期轉弱。新上市股或資料不足時不計此項。',
            'pos': ['🟢 股價站上 MA60（+1）'],
            'neg': ['🔴 股價跌破 MA60（−1）'],
        },
        {
            'emoji': '⚡', 'name': 'KD 指標（隨機指標）', 'term': '短期動能・過熱/超跌判斷',
            'desc': 'K 值衡量收盤在近期高低範圍內的相對位置（0～100）。本系統不計入燈號分數，但用來標記過熱／超跌狀態，影響結論文字。K 值黃金交叉（K 由下往上穿越 D）可視為買訊參考。',
            'pos': [],
            'neg': [],
            'neu': ['KD > 80 → 標記 🔥 過熱，提醒注意回調', 'KD < 20 → 標記 🧊 超跌，可留意反彈機會'],
        },
        {
            'emoji': '⚡', 'name': 'RSI（相對強弱指標）', 'term': '短期動能・過熱/超跌判斷',
            'desc': '衡量近期漲跌力道的比率，介於 0～100。配合 KD 共同決定過熱／超跌標記；任一條件成立即觸發。超買超賣需搭配其他訊號確認，避免追高殺低。',
            'pos': [],
            'neg': [],
            'neu': ['RSI > 70（且 KD > 80）→ 過熱標記', 'RSI < 30（且 KD < 20）→ 超跌標記'],
        },
        {
            'emoji': '🏦', 'name': '法人 5 日合計買賣超', 'term': '中期籌碼・計分',
            'desc': '統計外資＋投信過去 5 個交易日的合計買賣超張數。法人是台股最大資金來源，持續買超代表籌碼穩定集中，賣超則資金流出。短期避險賣出無需過度恐慌，需觀察方向是否持續。',
            'pos': ['💰 5 日合計買超（+1）'],
            'neg': ['🏃 5 日合計賣超（−1）'],
        },
        {
            'emoji': '📋', 'name': '季度收入年增率', 'term': '基本面・計分（僅個股）',
            'desc': '將本季營收與去年同期相比的成長率。正成長代表基本面向好，建議連續 2～3 季確認趨勢才能判定長期轉機。ETF 持股分散，不適用此項。',
            'pos': ['📊 年增率 > 0%（+1）'],
            'neg': ['📊 年增率 < 0%（−1）'],
        },
        {
            'emoji': '📌', 'name': '布林通道 & 標準差', 'term': '波動度・報告顯示（不計分）',
            'desc': '布林通道以 20 日均線為中心，上下各加減 2 倍標準差。標準差衡量股價偏離均值的程度：數值大代表波動劇烈，數值小代表趨於平穩。通道收窄（標準差縮小）常是大行情前的蓄勢信號。',
            'pos': [],
            'neg': [],
            'neu': ['布↑（上緣）= 短期壓力參考', '布↓（下緣）= 短期支撐參考', '通道愈窄 → 波動縮小、蓄勢待發'],
        },
        {
            'emoji': '📌', 'name': '支撐、壓力、風險警戒線', 'term': '價位參考・報告顯示（不計分）',
            'desc': '支撐是過去常見買盤進場的價位，壓力是常見賣盤出現的價位。風險警戒線為近 60 日最低點，跌破代表中期下跌趨勢確立。在報告中以進度條顯示，供判斷進出場位置參考。',
            'pos': [],
            'neg': [],
            'neu': ['⛔ 風險警戒線 = 近 60 日低點', '🔻 支撐 = 買盤常出現的價位', '🔺 壓力 = 賣盤常出現的價位'],
        },
    ]

    # 延伸學習：本系統目前尚未使用的指標
    indicators_ref = [
        {
            'emoji': '📈', 'name': 'EMA（指數平滑移動平均線）', 'term': '趨勢',
            'desc': '與 MA 相似，但對近期數據賦予更高權重，對市場變化反應更快、更靈敏。常用參數：12日、26日（短期），50日、200日（長期）。',
            'neu': ['短期 EMA 上穿長期 EMA → 黃金交叉（買訊參考）', '短期 EMA 下穿長期 EMA → 死亡交叉（賣訊參考）', '與 MA 比較：EMA 反應更快，但雜訊也更多'],
        },
        {
            'emoji': '📉', 'name': 'MACD（平滑異同移動平均線）', 'term': '動能趨勢',
            'desc': '由 12日EMA 減去 26日EMA 得到 MACD 線，再以 9日EMA 形成信號線；兩線之差形成柱狀圖。是判斷趨勢轉折的常用工具，可同時看方向與動能強度。',
            'neu': ['MACD 線上穿信號線 → 買訊參考', 'MACD 線下穿信號線 → 賣訊參考', '柱狀圖由負轉正 → 動能由空轉多', '柱狀圖持續縮小 → 趨勢可能減弱或反轉'],
        },
        {
            'emoji': '🌀', 'name': '斐波那契回調（Fibonacci Retracement）', 'term': '支撐壓力',
            'desc': '依斐波那契數列比例（23.6%、38.2%、50%、61.8%、78.6%）標示潛在的支撐與壓力價位。股價從高點下跌或從低點反彈時，常在這些比例處出現停頓或反轉。',
            'neu': ['38.2% 與 61.8% 是最常被關注的支撐/壓力位', '跌破 61.8% 回調位，常視為趨勢可能繼續走弱', '常用於設定止損位與目標價'],
        },
        {
            'emoji': '☁️', 'name': '一目均衡表（Ichimoku Cloud）', 'term': '趨勢・支撐壓力',
            'desc': '由轉換線、基準線、先行帶A、先行帶B、遲行線五條線組成的複合指標。「雲層」（先行帶A與B之間的區域）是核心，可同時呈現趨勢、支撐壓力與未來預測。',
            'neu': ['股價在雲層上方 → 偏多趨勢', '股價在雲層下方 → 偏空趨勢', '雲層由綠轉紅 → 趨勢轉弱訊號', '雲層愈厚 → 支撐／壓力愈強'],
        },
        {
            'emoji': '📐', 'name': 'ADX（平均趨向指數）', 'term': '趨勢強度',
            'desc': '衡量趨勢的強弱程度，介於 0～100，但不指示方向（多空）。需搭配 MA 或 MACD 判斷方向後，用 ADX 確認趨勢是否足夠強勁值得進場。',
            'neu': ['ADX > 25 → 趨勢明確，訊號參考性較高', 'ADX < 25 → 橫盤整理，均線訊號可靠性降低', 'ADX 持續上升 → 趨勢加速；持續下降 → 趨勢走弱'],
        },
    ]

    def build_ind_html(inds, ref=False):
        html = ''
        tag_cls = 'sig-ref' if ref else 'sig-neu'
        for ind in inds:
            pos_html = ''.join(f'<span class="sig sig-pos">{s}</span>' for s in ind.get('pos', []))
            neg_html = ''.join(f'<span class="sig sig-neg">{s}</span>' for s in ind.get('neg', []))
            neu_html = ''.join(f'<span class="sig sig-neu">{s}</span>' for s in ind.get('neu', []))
            sig_html = f'<div class="sig-row">{pos_html}{neg_html}{neu_html}</div>' if (pos_html or neg_html or neu_html) else ''
            html += f'''<div class="ind-item">
  <div class="ind-name">{ind["emoji"]} {ind["name"]} <span class="sig {tag_cls}">{ind["term"]}</span></div>
  <div class="ind-desc">{ind["desc"]}</div>
  {sig_html}
</div>'''
        return html

    ind_active_html = build_ind_html(indicators_active)
    ind_ref_html    = build_ind_html(indicators_ref, ref=True)

    html = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>指標說明 — 股哥快報</title>
<script>(function(){{document.documentElement.classList.add(localStorage.getItem('theme')||'dark');}})();</script>
<style>{GUIDE_CSS}</style>
</head>
<body>
<div class="hdr">
  <div class="hdr-left">
    <a href="today.html" class="back-btn">← Back</a>
    <div class="hdr-title">📚 指標說明</div>
  </div>
  <button class="theme-btn" id="theme-toggle">🌙</button>
</div>

<div class="section">
  <div class="sec-hd">🚦 燈號判斷規則<span class="sec-sub">每個訊號加減 1 分，累計決定燈號</span></div>
  <div class="score-box">
    <div class="score-pill pill-g"><span class="arrow">▲</span> 可買進：總分 ≥ 2</div>
    <div class="score-pill pill-y"><span>—</span> 觀望：總分 −1 ～ 1</div>
    <div class="score-pill pill-r"><span class="arrow">▼</span> 建議賣出：總分 ≤ −2</div>
  </div>
</div>

<div class="section">
  <div class="sec-hd">🔥🧊 過熱／超跌標記<span class="sec-sub">不影響燈號，但改變結論文字</span></div>
  <div class="heat-box">
    <div>
      <div class="heat-pill heat-hot">🔥 過熱：KD &gt; 80 或 RSI &gt; 70</div>
      <div class="heat-desc">即使分數為正，也建議觀察是否有回調再進場</div>
    </div>
    <div>
      <div class="heat-pill heat-cold">🧊 超跌：KD &lt; 20 或 RSI &lt; 30</div>
      <div class="heat-desc">即使分數為負，若基本面無惡化，可留意反彈機會</div>
    </div>
  </div>
</div>

<div class="section">
  <div class="sec-hd">📋 本系統使用的指標</div>
  <div class="ind-list">{ind_active_html}</div>
</div>

<div class="section">
  <div class="sec-hd-ref">📖 延伸學習（本系統目前尚未使用）</div>
  <div class="ind-list">{ind_ref_html}</div>
</div>

<div class="note">
  <strong>使用提醒</strong><br>
  本系統以技術面為主，分數只是量化參考，不代表必漲必跌。<br>
  遇到多個指標同向（如股價跌破 MA20＋MA60＋法人賣超），訊號較強；訊號分歧時建議觀望。<br>
  基本面（季度收入）僅個股適用，ETF 以法人籌碼和均線為主要判斷依據。
</div>

<script>
(function(){{
  const btn = document.getElementById('theme-toggle');
  const html = document.documentElement;
  function apply(t){{
    html.classList.remove('dark','light');
    html.classList.add(t);
    btn.textContent = t==='dark' ? '🌙' : '☀️';
    localStorage.setItem('theme', t);
  }}
  btn.addEventListener('click',()=>{{
    apply((localStorage.getItem('theme')||'dark')==='dark' ? 'light' : 'dark');
  }});
  btn.textContent = (localStorage.getItem('theme')||'dark')==='dark' ? '🌙' : '☀️';
}})();
</script>
</body>
</html>'''

    out = os.path.join(PUBLIC_DIR, 'guide.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'寫出：{out}')


def main(report_date=None):
    if not report_date:
        report_date = date.today().isoformat()

    json_path = os.path.join(DATA_DIR, f'{report_date}.json')
    if not os.path.exists(json_path):
        print(f'找不到 {json_path}，請先執行 main.py')
        sys.exit(1)

    with open(json_path, encoding='utf-8') as f:
        report = json.load(f)

    prev_report = None
    for i in range(1, 7):
        c  = (datetime.strptime(report_date, '%Y-%m-%d') - timedelta(days=i)).date().isoformat()
        cp = os.path.join(DATA_DIR, f'{c}.json')
        if os.path.exists(cp):
            with open(cp, encoding='utf-8') as f:
                prev_report = json.load(f)
            break

    available_dates = sorted([
        f[:-5] for f in os.listdir(DATA_DIR)
        if f.endswith('.json') and len(f) == 15
    ])

    html = generate(report, prev_report, available_dates)

    out = os.path.join(PUBLIC_DIR, f'{report_date}.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'寫出：{out}')

    today_p = os.path.join(PUBLIC_DIR, 'today.html')
    with open(today_p, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'複製：{today_p}')

    generate_guide()


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
