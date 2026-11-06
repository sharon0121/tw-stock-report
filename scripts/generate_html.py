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
    return f'''<div class="{card_cls}" data-sid="{sid}" data-name="{name}">
  <div class="card-top">
    <div class="ct-left">
      {light_disp(light)}
      <div class="name-row">
        {type_badge}<span class="sid">{sid}</span><span class="sname">{name}</span>
        {chg_badge}{heat_badge}
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
  :root{--bg:#000;--card:#1c1c1e;--text:#f5f5f7;--sub:#636366;--sep:#2c2c2e}
}
/* 強制深/淺色（覆蓋 media query） */
html.dark{--bg:#000;--card:#1c1c1e;--text:#f5f5f7;--sub:#636366;--sep:#2c2c2e}
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
.hdr-lights{display:flex;gap:16px;font-size:14px;font-weight:600}
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
// 展開/收合（鎖住捲軸位置，右側卡片展開不跳位）
document.querySelectorAll('.card-top').forEach(el=>{
  el.addEventListener('click',()=>{
    const y = window.scrollY;
    el.closest('.card').classList.toggle('open');
    requestAnimationFrame(()=>window.scrollTo(0, y));
  });
});
document.querySelectorAll('.card.changed').forEach(c=>c.classList.add('open'));

// 深淺色切換
(function(){
  const btn  = document.getElementById('theme-toggle');
  const html = document.documentElement;
  const ICONS = {dark:'🌙', light:'☀️', system:'🌓'};
  const ORDER = ['dark','light','system'];

  function apply(t){
    html.classList.remove('dark','light');
    if(t!=='system') html.classList.add(t);
    btn.textContent = ICONS[t];
    localStorage.setItem('theme', t);
  }
  btn.addEventListener('click',()=>{
    const cur = localStorage.getItem('theme')||'dark';
    apply(ORDER[(ORDER.indexOf(cur)+1)%ORDER.length]);
  });
  // 初始圖示同步（class 已由 head script 設好）
  btn.textContent = ICONS[localStorage.getItem('theme')||'dark'];
})();

// 搜尋
const inp   = document.getElementById('search');
const clrBtn= document.getElementById('search-clear');
const noRes = document.getElementById('no-result');
const grpE  = document.getElementById('grp-etf');
const grpS  = document.getElementById('grp-stock');

function doSearch(){
  const q = inp.value.trim().toLowerCase();
  clrBtn.style.display = q ? 'block' : 'none';
  document.querySelectorAll('.card').forEach(c=>{
    const match = !q
      || (c.dataset.sid  ||'').toLowerCase().includes(q)
      || (c.dataset.name ||'').toLowerCase().includes(q);
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

inp.addEventListener('input', doSearch);
clrBtn.addEventListener('click',()=>{ inp.value=''; doSearch(); inp.focus(); });

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
    <button class="theme-btn" id="theme-toggle">🌙</button>
  </div>
  <div class="hdr-title">📊 台股盤後報告 {date_disp}</div>
  <div class="hdr-lights">
    <span class="hdr-bull">▲ 多方 {summary.get("green",0)}</span>
    <span class="hdr-neu">— 觀望 {summary.get("yellow",0)}</span>
    <span class="hdr-bear">▼ 注意 {summary.get("red",0)}</span>
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
  var t=localStorage.getItem('theme')||'dark';
  if(t!=='system') document.documentElement.classList.add(t);
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


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
