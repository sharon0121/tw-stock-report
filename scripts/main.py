"""
台股盤後報告 — 主分析腳本
資料來源：yfinance（K線）、TWSE T86（法人）、TWSE OpenAPI（殖利率）
輸出：data/YYYY-MM-DD.json
"""
import json, sys, os, warnings
from datetime import date, timedelta, datetime
import requests
import yfinance as yf
import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8')

# ── 設定 ──────────────────────────────────────────────────────────────────────
WATCHLIST_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'watchlist.json')
DATA_DIR       = os.path.join(os.path.dirname(__file__), '..', 'data', 'history')
os.makedirs(DATA_DIR, exist_ok=True)

SIGNAL_RULES = {
    'above_ma20':   +1,
    'below_ma20':   -1,
    'above_ma60':   +1,
    'below_ma60':   -1,
    'ma20_up':      +1,
    'ma20_down':    -1,
    'inst_buy':     +1,
    'inst_sell':    -1,
    'rev_positive': +1,
    'rev_negative': -1,
}

# ── 載入清單 ───────────────────────────────────────────────────────────────────
def load_watchlist():
    with open(WATCHLIST_PATH, encoding='utf-8') as f:
        wl = json.load(f)
    return wl['etf'] + wl['stock']

# ── 判斷今天是否交易日（用 FinMind 免費的 TradingDate API）─────────────────────
def is_trading_day(target_date: str) -> bool:
    url = (
        'https://api.finmindtrade.com/api/v4/data'
        f'?dataset=TaiwanStockTradingDate&start_date={target_date}&end_date={target_date}'
        f'&token={os.environ.get("FINMIND_TOKEN","")}'
    )
    try:
        r = requests.get(url, timeout=10)
        d = r.json()
        return d.get('status') == 200 and len(d.get('data', [])) > 0
    except Exception:
        # 備援：若 API 失敗，假設今天是交易日（Actions 只在週一～五觸發）
        return True

# ── 從 TWSE 抓最新月份 K 線（備援：yfinance 有隔日延遲）──────────────────────────
def fetch_twse_latest_close(stock_id: str, year_month: str) -> dict | None:
    """
    year_month: 'YYYYMM'，例如 '202611'
    回傳 {date: 'YYYY-MM-DD', open, high, low, close, volume} 或 None
    """
    url = (f'https://www.twse.com.tw/exchangeReport/STOCK_DAY'
           f'?response=json&date={year_month}01&stockNo={stock_id}')
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'},
                         timeout=10, verify=False)
        d = r.json()
        if d.get('stat') != 'OK' or not d.get('data'):
            return None
        last = d['data'][-1]
        # 民國年轉西元：'115/11/06' → '2026-11-06'
        roc = last[0]
        parts = roc.split('/')
        year  = int(parts[0]) + 1911
        month = parts[1].zfill(2)
        day   = parts[2].zfill(2)
        def to_f(s):
            try: return float(s.replace(',', ''))
            except: return None
        return {
            'date':   f'{year}-{month}-{day}',
            'open':   to_f(last[3]),
            'high':   to_f(last[4]),
            'low':    to_f(last[5]),
            'close':  to_f(last[6]),
            'volume': to_f(last[1]),
        }
    except Exception:
        return None

# ── 抓 K 線（yfinance 主力 + TWSE 備援當日收盤）──────────────────────────────────
def fetch_ohlcv(stock_id: str) -> pd.DataFrame:
    ticker = f'{stock_id}.TW'
    df = yf.download(ticker, period='120d', progress=False, auto_adjust=True)
    if df.empty:
        return pd.DataFrame()
    df.index = pd.to_datetime(df.index)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]

    # 若最後一列 Close 是 NaN，用 TWSE 補充
    if df['Close'].iloc[-1] != df['Close'].iloc[-1]:  # NaN check
        from datetime import date
        ym = date.today().strftime('%Y%m')
        twse = fetch_twse_latest_close(stock_id, ym)
        if twse and twse['close']:
            ts = pd.Timestamp(twse['date'])
            df.loc[ts, 'Open']   = twse['open']
            df.loc[ts, 'High']   = twse['high']
            df.loc[ts, 'Low']    = twse['low']
            df.loc[ts, 'Close']  = twse['close']
            df.loc[ts, 'Volume'] = twse['volume']

    # 若 yfinance 最新日期落後超過 1 個交易日，整列插入 TWSE 當日數據
    from datetime import date, timedelta
    today = date.today()
    latest_date = df.dropna(subset=['Close']).index[-1].date() if not df.dropna(subset=['Close']).empty else None
    if latest_date and (today - latest_date).days >= 2 and today.weekday() < 5:
        ym = today.strftime('%Y%m')
        twse = fetch_twse_latest_close(stock_id, ym)
        if twse and twse['close']:
            ts = pd.Timestamp(twse['date'])
            if ts not in df.index:
                df.loc[ts] = [twse['open'], twse['high'], twse['low'],
                              twse['close'], twse['volume']]
                df = df.sort_index()

    return df.dropna(subset=['Close'])

# ── 計算技術指標 ───────────────────────────────────────────────────────────────
def calc_indicators(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 10:
        return {}

    close = df['Close']
    n = len(close)

    # 均線
    ma5  = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    last_close = float(close.iloc[-1])
    last_ma5   = float(ma5.iloc[-1])  if n >= 5  else None
    last_ma20  = float(ma20.iloc[-1]) if n >= 20 else None
    last_ma60  = float(ma60.iloc[-1]) if n >= 60 else None

    # 20 日線方向（比較最近 3 天的 MA20 斜率）
    ma20_direction = None
    if n >= 23:
        slope = float(ma20.iloc[-1]) - float(ma20.iloc[-4])
        ma20_direction = 'up' if slope > 0 else 'down'

    # KD（9 日）
    low9  = df['Low'].rolling(9).min()
    high9 = df['High'].rolling(9).max()
    rsv = ((close - low9) / (high9 - low9).replace(0, 1)) * 100
    k_series = rsv.ewm(com=2, adjust=False).mean()
    d_series = k_series.ewm(com=2, adjust=False).mean()
    last_k = float(k_series.iloc[-1]) if n >= 9 else None
    last_d = float(d_series.iloc[-1]) if n >= 9 else None

    # RSI（14 日）
    delta  = close.diff()
    gain   = delta.clip(lower=0).rolling(14).mean()
    loss   = (-delta.clip(upper=0)).rolling(14).mean()
    rs     = gain / loss.replace(0, 1e-9)
    rsi    = 100 - (100 / (1 + rs))
    last_rsi = float(rsi.iloc[-1]) if n >= 14 else None

    # 布林通道（20 日）
    bb_mid  = ma20
    bb_std  = close.rolling(20).std()
    bb_up   = bb_mid + 2 * bb_std
    bb_low  = bb_mid - 2 * bb_std
    last_bb_up  = float(bb_up.iloc[-1])  if n >= 20 else None
    last_bb_low = float(bb_low.iloc[-1]) if n >= 20 else None

    # 近 20 日高低（壓力 / 支撐 / 風險警戒）
    recent20_high = float(df['High'].iloc[-20:].max()) if n >= 20 else None
    recent20_low  = float(df['Low'].iloc[-20:].min())  if n >= 20 else None
    recent60_low  = float(df['Low'].iloc[-60:].min())  if n >= 60 else None

    # 漲跌幅
    prev_close    = float(close.iloc[-2]) if n >= 2 else last_close
    change_pct    = round((last_close - prev_close) / prev_close * 100, 2)

    return {
        'close':         round(last_close, 2),
        'change_pct':    change_pct,
        'ma5':           round(last_ma5,  2) if last_ma5  else None,
        'ma20':          round(last_ma20, 2) if last_ma20 else None,
        'ma60':          round(last_ma60, 2) if last_ma60 else '資料不足',
        'ma20_direction': ma20_direction,
        'kd_k':          round(last_k,   1) if last_k   else None,
        'kd_d':          round(last_d,   1) if last_d   else None,
        'rsi':           round(last_rsi, 1) if last_rsi else None,
        'bb_up':         round(last_bb_up,  2) if last_bb_up  else None,
        'bb_low':        round(last_bb_low, 2) if last_bb_low else None,
        'resistance':    round(max(recent20_high, last_bb_up)  / 2 + min(recent20_high, last_bb_up)  / 2, 2) if recent20_high and last_bb_up  else recent20_high,
        'support':       round(max(last_ma60 or 0, recent20_low or 0) / 2 + min(last_ma60 or last_close, recent20_low or last_close) / 2, 2) if last_ma60 and last_ma60 != '資料不足' and recent20_low else recent20_low,
        'risk_level':    round(recent60_low, 2) if recent60_low else None,
        'ma60_enough':   n >= 60,
    }

# ── 抓三大法人（TWSE T86）─────────────────────────────────────────────────────
def fetch_institutional(target_date: str) -> dict:
    """
    回傳 {stock_id: {'foreign_net': int, 'trust_net': int, 'total_net': int}}
    target_date: YYYYMMDD
    """
    url = (
        f'https://www.twse.com.tw/rwd/zh/fund/T86'
        f'?date={target_date}&selectType=ALLBUT0999&response=json'
    )
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'},
                         timeout=15, verify=False)
        d = r.json()
        if d.get('stat') != 'OK':
            return {}
        result = {}
        for row in d.get('data', []):
            sid = row[0]
            def parse_num(s):
                try:
                    return int(s.replace(',', '').replace('+', ''))
                except Exception:
                    return 0
            result[sid] = {
                'foreign_net': parse_num(row[4]),
                'trust_net':   parse_num(row[10]),
                'total_net':   parse_num(row[-1]),
            }
        return result
    except Exception as e:
        print(f'[WARN] 法人 API 失敗: {e}')
        return {}

def fetch_institutional_5d(today_str: str) -> dict:
    """
    抓最近 5 個交易日的法人數據並加總
    today_str: YYYY-MM-DD
    """
    today = datetime.strptime(today_str, '%Y-%m-%d').date()
    combined = {}
    fetched = 0
    delta = 0
    while fetched < 5 and delta < 14:
        d = today - timedelta(days=delta)
        delta += 1
        if d.weekday() >= 5:
            continue
        ds = d.strftime('%Y%m%d')
        daily = fetch_institutional(ds)
        if not daily:
            continue
        fetched += 1
        for sid, v in daily.items():
            if sid not in combined:
                combined[sid] = {'foreign_net': 0, 'trust_net': 0, 'total_net': 0}
            combined[sid]['foreign_net'] += v['foreign_net']
            combined[sid]['trust_net']   += v['trust_net']
            combined[sid]['total_net']   += v['total_net']
    return combined

# ── 抓殖利率（TWSE OpenAPI BWIBBU_d）─────────────────────────────────────────
def fetch_dividend_yield() -> dict:
    """回傳 {stock_id: {'yield': float, 'per': float}}"""
    try:
        r = requests.get(
            'https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_d',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=15, verify=False
        )
        d = r.json()
        result = {}
        for item in d:
            sid = item.get('Code', '')
            try:
                dy  = float(item.get('DividendYield', 0) or 0)
                per = float(item.get('PEratio', 0) or 0)
                result[sid] = {'yield': dy, 'per': per}
            except Exception:
                pass
        return result
    except Exception as e:
        print(f'[WARN] 殖利率 API 失敗: {e}')
        return {}

# ── 抓收入年增率（yfinance info）──────────────────────────────────────────────
def fetch_revenue_growth(stock_id: str, is_etf: bool) -> float | None:
    if is_etf:
        return None
    try:
        info = yf.Ticker(f'{stock_id}.TW').info
        return info.get('revenueGrowth')
    except Exception:
        return None

# ── 計算燈號分數 ───────────────────────────────────────────────────────────────
def calc_signal(ind: dict, inst_5d: dict, stock_id: str, is_etf: bool) -> dict:
    score = 0
    signals = []

    close  = ind.get('close', 0)
    ma20   = ind.get('ma20')
    ma60   = ind.get('ma60')
    ma60_ok = ind.get('ma60_enough', False)

    # 股價 vs MA20
    if ma20:
        if close > ma20:
            score += 1; signals.append({'key': 'above_ma20', 'score': +1,
                'label': '📈 站上 20 日均線', 'desc': f'收盤 {close} > MA20 {ma20:.0f}，短期買盤強'})
        else:
            score -= 1; signals.append({'key': 'below_ma20', 'score': -1,
                'label': '📉 跌破 20 日均線', 'desc': f'收盤 {close} < MA20 {ma20:.0f}，短期買盤變弱'})

    # 股價 vs MA60
    if ma60_ok and isinstance(ma60, (int, float)):
        if close > ma60:
            score += 1; signals.append({'key': 'above_ma60', 'score': +1,
                'label': '🟢 站上 60 日均線', 'desc': f'收盤 {close} > MA60 {ma60:.0f}，中期趨勢偏多'})
        else:
            score -= 1; signals.append({'key': 'below_ma60', 'score': -1,
                'label': '🔴 跌破 60 日均線', 'desc': f'收盤 {close} < MA60 {ma60:.0f}，中期趨勢轉弱'})

    # MA20 方向
    ma20_dir = ind.get('ma20_direction')
    if ma20_dir == 'up':
        score += 1; signals.append({'key': 'ma20_up', 'score': +1,
            'label': '↗ 20 日均線上彎', 'desc': '均線向上，代表短期動能增強'})
    elif ma20_dir == 'down':
        score -= 1; signals.append({'key': 'ma20_down', 'score': -1,
            'label': '↘ 20 日均線下彎', 'desc': '均線向下，代表短期動能減弱'})

    # 法人 5 日合計
    inst = inst_5d.get(stock_id, {})
    total_net = inst.get('total_net', 0)
    if total_net > 0:
        score += 1; signals.append({'key': 'inst_buy', 'score': +1,
            'label': '💰 法人 5 日合計買超', 'desc': f'外資+投信合計買超 {total_net:,} 股，籌碼偏多'})
    elif total_net < 0:
        score -= 1; signals.append({'key': 'inst_sell', 'score': -1,
            'label': '🏃 法人 5 日合計賣超', 'desc': f'外資+投信合計賣超 {abs(total_net):,} 股，籌碼偏空'})

    # 收入年增率（僅個股）
    if not is_etf:
        rev_growth = ind.get('rev_growth')
        if rev_growth is not None:
            if rev_growth > 0:
                score += 1; signals.append({'key': 'rev_positive', 'score': +1,
                    'label': f'📊 季度收入年增 {rev_growth*100:.1f}%', 'desc': '營收年增率為正，基本面向好'})
            else:
                score -= 1; signals.append({'key': 'rev_negative', 'score': -1,
                    'label': f'📊 季度收入年減 {abs(rev_growth)*100:.1f}%', 'desc': '營收年增率為負，基本面偏弱'})

    # 過熱 / 超跌標示
    kd_k = ind.get('kd_k')
    rsi  = ind.get('rsi')
    heat_flag = None
    if kd_k and rsi:
        if kd_k > 80 or rsi > 70:
            heat_flag = 'overbought'
        elif kd_k < 20 or rsi < 30:
            heat_flag = 'oversold'

    if score >= 2:
        light = '🟢'
    elif score <= -2:
        light = '🔴'
    else:
        light = '🟡'

    return {
        'score':     score,
        'light':     light,
        'signals':   signals,
        'heat_flag': heat_flag,
        'inst':      inst,
    }

# ── 產生一句話結論 ─────────────────────────────────────────────────────────────
def gen_conclusion(ind: dict, sig: dict, is_etf: bool) -> str:
    light = sig['light']
    score = sig['score']
    heat  = sig.get('heat_flag')
    ma20_dir = ind.get('ma20_direction', '')
    close = ind.get('close', 0)
    ma20  = ind.get('ma20')
    ma60  = ind.get('ma60')
    ma60_ok = ind.get('ma60_enough', False)

    if heat == 'overbought':
        return f'技術面短期過熱，建議觀察是否有回調，中期趨勢{"偏多" if score > 0 else "仍需確認"}。'
    if heat == 'oversold':
        return f'技術面短期超跌，若基本面無惡化，可留意反彈機會。'

    if light == '🟢':
        if ma20_dir == 'up':
            return f'多項指標偏強，均線向上，趨勢明確，但留意追高風險。'
        return f'整體偏強，法人與均線均支撐，短期可偏樂觀。'

    if light == '🔴':
        if ma60_ok and isinstance(ma60, (int, float)) and close < ma60:
            return f'跌破中期均線，中期趨勢轉弱，宜觀望為主。'
        return f'短期走弱，但中期均線尚未破，建議等待訊號穩定。'

    # 中性
    if ma20 and close > ma20:
        return f'短線站上均線，但訊號分歧，需更多確認方向。'
    return f'多空訊號分歧，目前處於整理狀態，等待方向明確。'

# ── 產生兩個情境 ───────────────────────────────────────────────────────────────
def gen_scenarios(ind: dict, sig: dict) -> list[str]:
    close    = ind.get('close', 0)
    support  = ind.get('support')
    resist   = ind.get('resistance')
    risk     = ind.get('risk_level')
    ma20     = ind.get('ma20')

    up_ref   = f'{resist:.0f}' if resist else '壓力區'
    down_ref = f'{support:.0f}' if support else '支撐區'
    risk_ref = f'{risk:.0f}' if risk else '風險警戒'

    s1 = f'① 若守住 {down_ref} 支撐 → 有機會嘗試挑戰 {up_ref} 壓力區'
    s2 = f'② 若跌破 {down_ref} → 下一支撐看 {risk_ref}，中期趨勢可能轉弱'
    return [s1, s2]

# ── 產生觀察點 ─────────────────────────────────────────────────────────────────
def gen_observations(ind: dict, sig: dict, stock_id: str) -> list[str]:
    obs = []
    close = ind.get('close', 0)
    ma20  = ind.get('ma20')
    ma60  = ind.get('ma60')
    ma60_ok = ind.get('ma60_enough', False)
    kd_k  = ind.get('kd_k')
    support = ind.get('support')
    inst = sig.get('inst', {})
    foreign = inst.get('foreign_net', 0)

    if ma20:
        if close < ma20:
            obs.append(f'近 3 天能否站回 20 日均線（{ma20:.0f}）')
        else:
            obs.append(f'20 日均線（{ma20:.0f}）能否持續支撐')

    if support:
        obs.append(f'支撐區 {support:.0f} 是否守住')

    if kd_k and kd_k > 70:
        obs.append(f'KD 偏高（{kd_k:.0f}），觀察是否出現死叉')
    elif kd_k and kd_k < 30:
        obs.append(f'KD 偏低（{kd_k:.0f}），觀察是否出現黃金交叉')

    if abs(foreign) > 0:
        direction = '買超' if foreign > 0 else '賣超'
        obs.append(f'外資連續{direction}是否改變方向')

    return obs[:3]

# ── 主流程 ─────────────────────────────────────────────────────────────────────
def main():
    today = date.today().isoformat()
    today_no_dash = today.replace('-', '')

    print(f'\n========== 台股盤後報告：{today} ==========\n')

    watchlist = load_watchlist()

    # 抓法人數據（全市場，一次性）
    print('抓取三大法人數據...')
    inst_5d = fetch_institutional_5d(today)

    # 抓殖利率
    print('抓取殖利率數據...')
    div_yield = fetch_dividend_yield()

    report = {
        'date':   today,
        'stocks': {}
    }

    for item in watchlist:
        sid   = item['id']
        name  = item['name']
        is_etf = item['type'] == 'etf'
        print(f'\n--- {sid} {name} ---')

        # K 線
        df = fetch_ohlcv(sid)
        if df.empty:
            print(f'  [跳過] 無 K 線數據')
            continue

        # 指標
        ind = calc_indicators(df)
        if not ind:
            print(f'  [跳過] 資料不足')
            continue

        # 收入年增率（個股）
        if not is_etf:
            ind['rev_growth'] = fetch_revenue_growth(sid, is_etf)

        # 殖利率（ETF + 個股）
        dy_info = div_yield.get(sid, {})
        ind['div_yield'] = dy_info.get('yield')
        ind['per']       = dy_info.get('per')

        # 燈號
        sig = calc_signal(ind, inst_5d, sid, is_etf)

        # 結論 / 情境 / 觀察
        conclusion   = gen_conclusion(ind, sig, is_etf)
        scenarios    = gen_scenarios(ind, sig)
        observations = gen_observations(ind, sig, sid)

        entry = {
            'id':           sid,
            'name':         name,
            'type':         item['type'],
            'close':        ind['close'],
            'change_pct':   ind['change_pct'],
            'ma5':          ind.get('ma5'),
            'ma20':         ind.get('ma20'),
            'ma60':         ind.get('ma60'),
            'ma20_direction': ind.get('ma20_direction'),
            'kd_k':         ind.get('kd_k'),
            'kd_d':         ind.get('kd_d'),
            'rsi':          ind.get('rsi'),
            'bb_up':        ind.get('bb_up'),
            'bb_low':       ind.get('bb_low'),
            'resistance':   ind.get('resistance'),
            'support':      ind.get('support'),
            'risk_level':   ind.get('risk_level'),
            'div_yield':    ind.get('div_yield'),
            'per':          ind.get('per'),
            'rev_growth':   ind.get('rev_growth'),
            'inst_5d':      sig.get('inst', {}),
            'score':        sig['score'],
            'light':        sig['light'],
            'signals':      sig['signals'],
            'heat_flag':    sig.get('heat_flag'),
            'conclusion':   conclusion,
            'scenarios':    scenarios,
            'observations': observations,
        }
        report['stocks'][sid] = entry

        # 終端機輸出
        heat_str = f' ⚠️ {sig["heat_flag"]}' if sig.get("heat_flag") else ''
        print(f'  收盤 {ind["close"]:>8.2f}  {ind["change_pct"]:+.2f}%  {sig["light"]}{heat_str}')
        print(f'  MA5={ind.get("ma5","--")}  MA20={ind.get("ma20","--")}  MA60={ind.get("ma60","--")}')
        print(f'  KD={ind.get("kd_k","--")}/{ind.get("kd_d","--")}  RSI={ind.get("rsi","--")}')
        print(f'  壓力區={ind.get("resistance","--")}  支撐區={ind.get("support","--")}  風險警戒={ind.get("risk_level","--")}')
        inst = sig.get('inst', {})
        print(f'  法人5日: 外資={inst.get("foreign_net",0):+,}  投信={inst.get("trust_net",0):+,}')
        print(f'  → {conclusion}')
        print(f'  情境: {scenarios[0]}')
        print(f'       {scenarios[1]}')

    # 統計燈號
    lights = [v['light'] for v in report['stocks'].values()]
    green  = lights.count('🟢')
    yellow = lights.count('🟡')
    red    = lights.count('🔴')
    report['summary'] = {'green': green, 'yellow': yellow, 'red': red}

    print(f'\n========== 匯總 ==========')
    print(f'🟢 偏強 {green} 檔  🟡 中性 {yellow} 檔  🔴 偏弱 {red} 檔')

    # 寫出 JSON
    out_path = os.path.join(DATA_DIR, f'{today}.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'\n已寫出：{out_path}')

if __name__ == '__main__':
    main()
