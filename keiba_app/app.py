# V12.0 - Ultimate Bulletproof JRA & Netkeiba Race Fetcher
import re
import requests
from bs4 import BeautifulSoup
import urllib3
import streamlit as st
import datetime
import pandas as pd
import numpy as np

JST = datetime.timezone(datetime.timedelta(hours=9))

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# JRA 10 Venues Map
VENUE_MAP = {
    "札幌": "01", "函館": "02", "福島": "03", "新潟": "04",
    "東京": "05", "中山": "06", "中京": "07", "京都": "08",
    "阪神": "09", "小倉": "10"
}
VENUE_CODE_TO_NAME = {v: k for k, v in VENUE_MAP.items()}

TOP_JOCKEYS_S = ["ルメール", "川田", "武豊", "坂井", "横山武", "戸崎", "モレイラ", "レーン"]
TOP_JOCKEYS_A = ["松山", "鮫島克", "岩田望", "西村淳", "菅原明", "津村", "田辺", "デムーロ", "丹内"]

# ---------------------------------------------------------
# Streamlit Page Config & High-Contrast Light Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="Kuina AI Racing Pro (JRA直結版)",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    
    .stApp {
        background-color: #f8fafc;
        color: #0f172a;
        font-family: 'Inter', 'Helvetica Neue', Arial, 'Hiragino Sans', sans-serif;
    }
    
    .hero-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #1e3a8a;
        margin-bottom: 1rem;
        letter-spacing: -0.02em;
    }

    .horse-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 20px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        margin-bottom: 16px;
        height: auto !important;
        min-height: 260px;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        white-space: normal !important;
    }
    
    .card-honmei { border-left: 6px solid #dc2626; background: #fff5f5; }
    .card-taikou { border-left: 6px solid #059669; background: #f0fdf4; }
    .card-tanana { border-left: 6px solid #2563eb; background: #eff6ff; }

    .badge-honmei { background: #dc2626; color: #ffffff; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 0.85rem; }
    .badge-taikou { background: #059669; color: #ffffff; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 0.85rem; }
    .badge-tanana { background: #2563eb; color: #ffffff; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 0.85rem; }

    .horse-name-title {
        font-size: 1.4rem;
        font-weight: 800;
        color: #0f172a;
        margin: 10px 0 6px 0;
        line-height: 1.3;
        word-break: break-word !important;
        white-space: normal !important;
    }

    .bet-card {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 16px;
        height: 100%;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
    }
    .bet-title {
        font-weight: 700;
        font-size: 1.05rem;
        color: #1e40af;
        margin-bottom: 8px;
    }
    .bet-code {
        font-family: monospace;
        font-size: 1.05rem;
        background: #f1f5f9;
        padding: 8px 12px;
        border-radius: 8px;
        color: #0f172a;
        font-weight: 700;
        border: 1px solid #cbd5e1;
        margin: 8px 0;
        white-space: pre-line;
        word-break: break-all;
    }

    .calc-card {
        background: #ffffff;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #3b82f6;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.08);
        margin-top: 15px;
    }
    .sim-card {
        background: #f0fdf4;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #10b981;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.08);
        margin-bottom: 15px;
    }
</style>
""", unsafe_allow_html=True)

def parse_horse_weight_str(txt):
    if not txt: return "計不", 0
    clean_txt = str(txt).strip().replace(' ', '')
    if not clean_txt or clean_txt in ['--', '計不', '前計不']: return "計不", 0
    m = re.search(r'(\d{3,4})\s*\(\s*([+-]?\d+)\s*\)', clean_txt)
    if m:
        w_val = m.group(1)
        d_val = int(m.group(2))
        d_str = f"+{d_val}" if d_val > 0 else str(d_val)
        return f"{w_val}kg ({d_str})", d_val
    m_plain = re.search(r'(\d{3,4})', clean_txt)
    if m_plain: return f"{m_plain.group(1)}kg", 0
    return "計不", 0

def fetch_html(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://race.netkeiba.com/'
    }
    try:
        session = requests.Session()
        session.headers.update(headers)
        res = session.get(url, verify=False, timeout=15)
        if res.status_code != 200:
            return None, f"アクセスエラー ({res.status_code})"
        html_text = None
        for enc in ['euc-jp', 'euc_jp', 'cp932', 'shift_jis', 'utf-8']:
            try:
                html_text = res.content.decode(enc)
                if 'netkeiba' in html_text or '馬名' in html_text or '出馬' in html_text:
                    break
            except Exception:
                continue
        if not html_text:
            html_text = res.content.decode('euc-jp', errors='replace')
        return BeautifulSoup(html_text, 'html.parser'), None
    except Exception as e:
        return None, f"通信エラー: {e}"

def fetch_race_list_by_date(dt_str):
    clean_date = re.sub(r'\D', '', str(dt_str))
    if len(clean_date) != 8:
        return [], "日付は8桁の数字(YYYYMMDD)で指定してください。"

    races_dict = {}

    # Target live race list URLs
    urls = [
        f"https://race.netkeiba.com/top/race_list.html?kaisai_date={clean_date}",
        f"https://race.netkeiba.com/top/?kaisai_date={clean_date}",
        f"https://race.netkeiba.com/top/race_list.html?kaijo_date={clean_date}"
    ]

    for target_url in urls:
        soup, _ = fetch_html(target_url)
        if not soup: continue

        # Decompose noisy elements BEFORE selecting
        for noisy in soup.select('#SideBar, .PickupRace, .Orepro, #Header, .Header, .Sidebar_Box'):
            noisy.decompose()

        main_box = soup.select_one('div.RaceList_Data') or soup.select_one('div.Race_List') or soup.select_one('div#RaceTopRace') or soup

        for a in main_box.find_all('a'):
            href = a.get('href', '')
            m = re.search(r'race_id=(\d{12})', href) or re.search(r'/race/(\d{12})', href)
            if not m: continue

            r_id = m.group(1)
            v_code = r_id[4:6]
            if v_code not in VENUE_CODE_TO_NAME: continue

            venue_name = VENUE_CODE_TO_NAME[v_code]
            r_num = int(r_id[10:12])

            raw_text = a.text.strip().replace('\n', ' ')
            raw_text = re.sub(r'\s+', ' ', raw_text)

            clean_name = re.sub(r'^(📍|【.*?】|\d+R)\s*', '', raw_text).strip()
            clean_name = re.sub(r'(出馬表|オッズ|結果|映像|払戻|掲示板|データ|競馬新聞|予想|俺プロ)', '', clean_name).strip()

            display_title = f"📍【{venue_name} {r_num}R】 {clean_name}" if clean_name and len(clean_name) >= 2 else f"📍【{venue_name} {r_num}R】"

            if r_id not in races_dict or len(display_title) > len(races_dict[r_id]['name']):
                races_dict[r_id] = {
                    'id': r_id,
                    'name': display_title,
                    'venue': venue_name,
                    'r_num': r_num,
                    'v_code': v_code
                }

    if not races_dict:
        db_url = f"https://db.netkeiba.com/race/list/{clean_date}/"
        soup, _ = fetch_html(db_url)
        if soup:
            main_box = soup.select_one('div.db_main_race_list') or soup.select_one('div#main') or soup
            for a in main_box.find_all('a'):
                href = a.get('href', '')
                m = re.search(r'/race/(\d{12})', href)
                if m:
                    r_id = m.group(1)
                    v_code = r_id[4:6]
                    if v_code not in VENUE_CODE_TO_NAME: continue
                    venue_name = VENUE_CODE_TO_NAME[v_code]
                    r_num = int(r_id[10:12])

                    raw_text = a.text.strip().replace('\n', ' ')
                    raw_text = re.sub(r'\s+', ' ', raw_text)
                    clean_name = re.sub(r'^(📍|【.*?】|\d+R)\s*', '', raw_text).strip()
                    clean_name = re.sub(r'(出馬表|オッズ|結果|映像|払戻|掲示板|データ|競馬新聞|予想|俺プロ)', '', clean_name).strip()

                    display_title = f"📍【{venue_name} {r_num}R】 {clean_name}" if clean_name and len(clean_name) >= 2 else f"📍【{venue_name} {r_num}R】"

                    if r_id not in races_dict:
                        races_dict[r_id] = {
                            'id': r_id,
                            'name': display_title,
                            'venue': venue_name,
                            'r_num': r_num,
                            'v_code': v_code
                        }

    if not races_dict:
        return [], f"指定された日付 ({clean_date}) の中央競馬(JRA)レースデータは見つかりませんでした。"

    races = list(races_dict.values())
    races.sort(key=lambda x: (x['v_code'], x['r_num']))
    return races, None

def parse_race_netkeiba(soup):
    rows = soup.select('tr.HorseList') or soup.select('table.ShutubaTable tr') or soup.select('table.Shutuba_Table tr') or soup.select('table.ResultTable tr')
    if not rows:
        all_trs = soup.find_all('tr')
        rows = [tr for tr in all_trs if tr.select_one('a[href*="/horse/"]')]

    if not rows: return []

    data_list = []
    for idx, r in enumerate(rows, start=1):
        td_list = r.find_all(['td', 'th'])
        if len(td_list) < 2: continue

        horse_a = r.select_one('a[href*="/horse/"]') or r.select_one('.HorseName a')
        if not horse_a: continue
        horse_name = horse_a.text.strip()
        if not horse_name or horse_name in ['馬名', '競走馬']: continue

        jockey_a = r.select_one('a[href*="/jockey/"]') or r.select_one('.Jockey a')
        jockey_name = jockey_a.text.strip() if jockey_a else "未定義"

        wakaban = None
        umaban = None
        odds_val = None
        pop_val = None
        weight_val = 55.0
        hw_str = "計不"
        hw_diff = 0

        for td in td_list:
            classes = [c.lower() for c in td.get('class', [])]
            cls_str = ' '.join(classes)
            text = td.text.strip()

            m_w = re.search(r'waku(\d)', cls_str)
            if m_w: wakaban = int(m_w.group(1))

            m_u = re.search(r'umaban(\d+)', cls_str)
            if m_u: umaban = int(m_u.group(1))

            m_wt = re.search(r'^(4\d|5\d|6\d)(?:\.\d)?$', text)
            if m_wt:
                try: weight_val = float(m_wt.group(0))
                except ValueError: pass

            if 'odds' in cls_str or 'odds' in (td.get('id') or '').lower():
                m_o = re.search(r'(\d+\.\d+)', text)
                if m_o:
                    try: odds_val = float(m_o.group(1))
                    except ValueError: pass

            if 'popular' in cls_str or 'pop' in cls_str or 'ninki' in cls_str:
                m_p = re.search(r'(\d+)', text)
                if m_p:
                    try: pop_val = int(m_p.group(1))
                    except ValueError: pass

            if 'weight' in cls_str or 'weight' in (td.get('id') or '').lower() or re.search(r'\d{3,4}\s*\(', text):
                p_str, p_diff = parse_horse_weight_str(text)
                if p_str != "計不":
                    hw_str = p_str
                    hw_diff = p_diff

        if wakaban is None and len(td_list) > 0:
            txt = td_list[0].text.strip()
            if txt.isdigit() and 1 <= int(txt) <= 8: wakaban = int(txt)

        if umaban is None and len(td_list) > 1:
            txt = td_list[1].text.strip()
            if txt.isdigit(): umaban = int(txt)

        if umaban is None: umaban = idx
        if wakaban is None: wakaban = (umaban - 1) // 2 + 1 if umaban <= 16 else 8

        data_list.append({
            '枠番': wakaban, '馬番': umaban, '馬名': horse_name,
            '騎手': jockey_name,
            '斤量': weight_val, '単勝オッズ': odds_val if odds_val is not None else "未確定",
            '人気': pop_val if pop_val is not None else "未確定",
            '馬体重': hw_str, '体重増減': hw_diff
        })

    return data_list

def fetch_odds_data(clean_id):
    odds_url = f"https://race.netkeiba.com/odds/index.html?type=b1&race_id={clean_id}"
    soup, _ = fetch_html(odds_url)
    if not soup: return {}

    odds_map = {}
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for r in rows:
            tds = r.find_all(['td', 'th'])
            if len(tds) >= 4:
                uma_txt = tds[1].text.strip() if len(tds) > 1 else (tds[0].text.strip() if len(tds) > 0 else '')
                odds_txt = tds[-2].text.strip() if len(tds) > 2 else ''
                pop_txt = tds[-1].text.strip() if len(tds) > 3 else ''
                m_uma = re.search(r'(\d+)', uma_txt)
                m_odds = re.search(r'(\d+\.\d+|\d+)', odds_txt)
                m_pop = re.search(r'(\d+)', pop_txt)
                if m_uma and m_odds:
                    try:
                        uma = int(m_uma.group(1))
                        odds = float(m_odds.group(1))
                        pop = int(m_pop.group(1)) if m_pop else "未確定"
                        odds_map[uma] = {'odds': odds, 'pop': pop}
                    except ValueError: pass
    return odds_map

def calculate_ai_scores(data_list, paddock_status_map=None, race_env=None):
    if not data_list: return data_list
    if paddock_status_map is None: paddock_status_map = {}
    if race_env is None:
        race_env = {'weather': '晴', 'condition': '良', 'bias': '⚪ フラット', 'pace': 'ミドルペース'}

    scored_items = []
    for d in data_list:
        odds = d.get('単勝オッズ')
        pop = d.get('人気')
        weight = d.get('斤量', 55.0)
        hw_diff = d.get('体重増減', 0)
        uma = d.get('馬番')
        waku = d.get('枠番', 1)
        jockey = d.get('騎手', '')
        horse_name = d.get('馬名', '')

        try: o_val = float(odds)
        except (ValueError, TypeError): o_val = 20.0

        try: p_val = float(pop)
        except (ValueError, TypeError): p_val = 8.0

        pop_score = max(0, 40 - (p_val - 1) * 3.5)
        odds_score = max(0, 30 - (o_val * 0.6))
        weight_bonus = max(0, (56.0 - weight) * 2)

        j_score = 1.0
        j_comment = f"【鞍上】{jockey}"
        if any(tj in jockey for tj in TOP_JOCKEYS_S):
            j_score = 7.0
            j_comment = f"【トップ騎手】{jockey}"
        elif any(tj in jockey for tj in TOP_JOCKEYS_A):
            j_score = 4.0
            j_comment = f"【有力騎手】{jockey}"

        blood_score = 5.0
        blood_comment = "【血統】良馬場適性"
        if race_env['condition'] in ['重', '不良', '稍重']:
            if any(kw in horse_name for kw in ["キング", "ゴールド", "ダノン", "ボルド", "パワー"]):
                blood_score = 6.0
                blood_comment = f"【血統】道悪・{race_env['condition']}パワー血統"

        bias_score = 2.0
        bias_comment = "馬場フラット"
        if "内伸び・前残り" in race_env['bias']:
            if waku in [1, 2, 3]:
                bias_score = 6.0
                bias_comment = f"【バイアス好走】内枠{waku}枠"
        elif "外伸び・差し" in race_env['bias']:
            if waku in [6, 7, 8]:
                bias_score = 6.0
                bias_comment = f"【バイアス好走】外枠{waku}枠"

        raw_score = pop_score + odds_score + weight_bonus + j_score + blood_score + bias_score + 5
        score = round(min(99.9, max(10.0, raw_score)), 1)

        d_copy = dict(d)
        d_copy['_raw_score'] = score
        d_copy['パドック評価'] = paddock_status_map.get(uma, "⚪ 普通 (0pt)")
        d_copy['騎手評価'] = j_comment
        d_copy['血統適性'] = blood_comment
        d_copy['バイアス展開'] = bias_comment
        scored_items.append(d_copy)

    scored_items.sort(key=lambda x: x['_raw_score'], reverse=True)
    mark_list = ['◎ 本命', '◯ 対抗', '▲ 単穴', '△ 連下', '△ 連下', '☆ 穴馬']
    for idx, item in enumerate(scored_items):
        item['予想印'] = mark_list[idx] if idx < len(mark_list) else 'ー'
        item['AI予想スコア'] = item['_raw_score']

    return scored_items

def generate_betting_recommendations(data_list, strategy_mode, selected_tickets):
    if not data_list: return {}
    top = sorted(data_list, key=lambda x: x.get('AI予想スコア', 0), reverse=True)
    honmei = next((d for d in top if '◎' in d.get('予想印', '')), top[0])
    taikou = next((d for d in top if '◯' in d.get('予想印', '')), top[1] if len(top)>1 else top[0])
    tanana = next((d for d in top if '▲' in d.get('予想印', '')), top[2] if len(top)>2 else top[0])

    h_num = honmei['馬番']
    o_num = taikou['馬番']
    a_num = tanana['馬番']

    bets = {}
    bets['馬連'] = {
        '方式': '流し',
        '点数': '2点',
        '買い目': f'{h_num} - {o_num}, {a_num}',
        '解説': f'本命 {h_num}番 から対抗・単穴へ本線流し',
        '想定オッズ': 12.5
    }
    bets['3連複'] = {
        '方式': '1頭軸流し',
        '点数': '3点',
        '買い目': f'{h_num} - {o_num}, {a_num}',
        '解説': f'本命 {h_num}番 を軸にした安定フォーメーション',
        '想定オッズ': 28.0
    }
    return bets

def calculate_capital_allocation(tickets, total_budget):
    if not tickets or total_budget <= 0: return [], 0, 0
    valid_tickets = [t for t in tickets if t.get('odds', 0) > 1.0]
    if not valid_tickets: return [], 0, 0

    inv_sum = sum(1.0 / t['odds'] for t in valid_tickets)
    syn_odds = round(1.0 / inv_sum, 2) if inv_sum > 0 else 0

    alloc_list = []
    total_alloc = 0
    for t in valid_tickets:
        raw_alloc = (total_budget / (t['odds'] * inv_sum)) if inv_sum > 0 else 0
        alloc_amt = max(100, int(round(raw_alloc / 100.0) * 100))
        expected_payout = int(alloc_amt * t['odds'])
        total_alloc += alloc_amt
        alloc_list.append({
            '買い目・券種': t['name'],
            '想定オッズ': f"{t['odds']} 倍",
            '推奨購入額': f"{alloc_amt:,} 円",
            '的中時想定払戻': f"{expected_payout:,} 円"
        })
    return alloc_list, syn_odds, total_alloc

def get_race_data(input_id, paddock_status_map=None, race_env=None):
    clean_id = re.sub(r'\D', '', str(input_id))
    if len(clean_id) == 10 and clean_id.startswith(('20', '21', '22', '23', '24', '25', '26')):
        clean_id = '20' + clean_id

    if not clean_id or len(clean_id) != 12:
        return None, "有効な12桁のJRAレースIDを入力してください。"

    data_list = []
    errors = []

    race_urls = [
        f"https://race.netkeiba.com/race/shutuba.html?race_id={clean_id}",
        f"https://race.netkeiba.com/race/result.html?race_id={clean_id}"
    ]
    for url in race_urls:
        soup, err = fetch_html(url)
        if soup:
            data_list = parse_race_netkeiba(soup)
            if data_list: break
        elif err: errors.append(f"Race: {err}")

    if not data_list:
        db_url = f"https://db.netkeiba.com/race/{clean_id}/"
        soup, err = fetch_html(db_url)
        if soup:
            # simple parse
            pass

    if not data_list:
        return None, f"レースデータが見つかりませんでした。(ID: {clean_id})"

    has_missing = any(d['単勝オッズ'] == "未確定" for d in data_list)
    if has_missing:
        odds_map = fetch_odds_data(clean_id)
        if odds_map:
            for d in data_list:
                uma = d['馬番']
                if d['単勝オッズ'] == "未確定" and uma in odds_map:
                    d['単勝オッズ'] = odds_map[uma]['odds']
                    d['人気'] = odds_map[uma]['pop']

    data_list = calculate_ai_scores(data_list, paddock_status_map, race_env)
    return data_list, None

# ---------------------------------------------------------
# UI Core Component
# ---------------------------------------------------------
st.markdown('<div class="hero-title">🏇 Kuina AI Racing Pro (JRA直結版)</div>', unsafe_allow_html=True)

now_jst = datetime.datetime.now(JST)
today_jst = now_jst.date()
weekday = today_jst.weekday()

if weekday == 6:
    this_saturday = today_jst - datetime.timedelta(days=1)
    this_sunday = today_jst
else:
    this_saturday = today_jst + datetime.timedelta(days=(5 - weekday))
    this_sunday = today_jst + datetime.timedelta(days=(6 - weekday))

tab1, tab2, tab3 = st.tabs(["📅 JRA日程・出馬表検索", "⚙️ 競馬場・レース指定", "🔢 12桁ID直接入力"])

if 'active_race_id' not in st.session_state:
    st.session_state['active_race_id'] = None

with tab1:
    st.markdown("#### 📅 今週の中央競馬 (JRA全10場：中山・阪神・中京等)")
    q_col1, q_col2, q_col3 = st.columns(3)
    with q_col1:
        if st.button(f"🏇 今週の土曜日 ({this_saturday.strftime('%m/%d')})", use_container_width=True):
            st.session_state['selected_date_val'] = this_saturday
            st.session_state['trigger_fetch'] = True
    with q_col2:
        if st.button(f"🏇 今週の日曜日 ({this_sunday.strftime('%m/%d')})", use_container_width=True):
            st.session_state['selected_date_val'] = this_sunday
            st.session_state['trigger_fetch'] = True
    with q_col3:
        if st.button(f"📅 本日 ({today_jst.strftime('%m/%d')})", use_container_width=True):
            st.session_state['selected_date_val'] = today_jst
            st.session_state['trigger_fetch'] = True

    if 'selected_date_val' not in st.session_state:
        st.session_state['selected_date_val'] = this_saturday if weekday not in [5, 6] else today_jst

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        selected_date = st.date_input("開催日を選択 (JRA中央競馬):", value=st.session_state['selected_date_val'])
        if st.button("🔍 JRA全レース一覧を取得", use_container_width=True) or st.session_state.get('trigger_fetch'):
            st.session_state['trigger_fetch'] = False
            st.session_state['selected_date_val'] = selected_date
            dt_str = selected_date.strftime("%Y%m%d")
            with st.spinner(f"JRAレース情報（{selected_date.strftime('%Y/%m/%d')}）を取得中..."):
                races, err = fetch_race_list_by_date(dt_str)
                if err: st.error(err)
                else:
                    st.session_state['fetched_races'] = races
                    st.session_state['fetched_date_str'] = selected_date.strftime('%Y/%m/%d')

    if 'fetched_races' not in st.session_state:
        dt_str = st.session_state['selected_date_val'].strftime("%Y%m%d")
        races, _ = fetch_race_list_by_date(dt_str)
        if races:
            st.session_state['fetched_races'] = races
            st.session_state['fetched_date_str'] = st.session_state['selected_date_val'].strftime('%Y/%m/%d')

    with col_d2:
        if 'fetched_races' in st.session_state and st.session_state['fetched_races']:
            st.success(f"✅ {st.session_state.get('fetched_date_str', '')} JRA全{len(st.session_state['fetched_races'])}レース 取得完了")
            race_options = {f"{r['name']} (ID: {r['id']})": r['id'] for r in st.session_state['fetched_races']}
            selected_race_label = st.selectbox("対象レースを選択してください:", list(race_options.keys()))
            if selected_race_label:
                st.session_state['active_race_id'] = race_options[selected_race_label]
        elif 'fetched_races' in st.session_state and not st.session_state['fetched_races']:
            st.warning("指定された日付の中央競馬(JRA)レースは見つかりませんでした。今週の土曜日または日曜日のボタンをお試しください。")
        else:
            st.info("上の「今週の土曜日」「今週の日曜日」ボタンを押すと、全JRAレースが一括取得されます。")

with tab2:
    st.markdown("#### ⚙️ 競馬場・レース番号 直接選択 (いつでも全レース解析可能)")
    st.caption("一覧が混雑している場合でも、会場とレース番号を選んで一発解析できます。")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: year_sel = st.number_input("年", 2000, 2026, today_jst.year)
    with c2: venue_sel = st.selectbox("競馬場(JRA)", list(VENUE_MAP.keys()), index=5) # default 中山
    with c3: kai_sel = st.number_input("回", 1, 12, 4)
    with c4: nichi_sel = st.number_input("日目", 1, 12, 7)
    with c5: race_num_sel = st.number_input("R", 1, 12, 11)
    generated_id = f"{year_sel}{VENUE_MAP[venue_sel]}{kai_sel:02d}{nichi_sel:02d}{race_num_sel:02d}"
    st.caption(f"自動生成12桁ID: `{generated_id}`")
    if st.button("🚀 条件指定で直結解析", use_container_width=True):
        st.session_state['active_race_id'] = generated_id

with tab3:
    st.markdown("#### 🔢 12桁ID直接入力")
    col_a, col_b = st.columns(2)
    with col_a:
        manual_id = st.text_input("12桁レースID:", value="202405021211")
    with col_b:
        st.write("サンプル:")
        if st.button("📌 日本ダービー (202405021211)"):
            st.session_state["active_race_id"] = "202405021211"
    if manual_id and st.button('🚀 IDで解析'):
        st.session_state['active_race_id'] = manual_id

# Results Area
target_race_id = st.session_state.get('active_race_id')

if not target_race_id:
    st.markdown("---")
    st.info("💡 画面上の「今週の土曜日」「今週の日曜日」ボタンを押すと、JRA全レースの一覧からAI予想が表示されます。")

if target_race_id:
    st.markdown("---")
    if 'paddock_map' not in st.session_state:
        st.session_state['paddock_map'] = {}

    st.markdown("### 🌦️ トラックバイアス・天候・展開ペルソナ調整")
    env_c1, env_c2, env_c3, env_c4 = st.columns(4)
    with env_c1: sel_weather = st.selectbox("☀️ 天候", ["晴", "曇", "雨", "小雨"], index=0)
    with env_c2: sel_condition = st.selectbox("🌿 馬場状態", ["良", "稍重", "重", "不良"], index=0)
    with env_c3: sel_bias = st.selectbox("🚧 トラックバイアス", ["⚪ フラット", "🟩 内伸び・前残り有利", "🟨 外伸び・差し有利"], index=0)
    with env_c4: sel_pace = st.selectbox("🏃 展開・ペース予想", ["ミドルペース", "スローペース（前残り）", "ハイペース（差し有利）"], index=0)

    current_race_env = {'weather': sel_weather, 'condition': sel_condition, 'bias': sel_bias, 'pace': sel_pace}

    with st.spinner("🤖 AI多角分析エンジン実行中..."):
        data, error = get_race_data(target_race_id, st.session_state['paddock_map'], current_race_env)

        if error:
            st.error(error)
        else:
            df = pd.DataFrame(data)
            honmei = next((d for d in data if '◎' in d.get('予想印', '')), None)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("対象レースID", target_race_id)
            m2.metric("出走頭数", f"{len(data)} 頭")
            m3.metric("AI最有力 本命馬", f"{honmei['馬番']}番 {honmei['馬名']}" if honmei else "ー")
            m4.metric("本命単勝オッズ", f"{honmei['単勝オッズ']} 倍" if honmei else "ー")

            st.markdown("### 🎯 AI選定・上位評価馬")
            top_3 = sorted(data, key=lambda x: x.get('AI予想スコア', 0), reverse=True)[:3]
            c_h1, c_h2, c_h3 = st.columns(3)
            card_styles = ["card-honmei", "card-taikou", "card-tanana"]
            badges = ["badge-honmei", "badge-taikou", "badge-tanana"]
            mark_names = ["◎ 本命馬", "◯ 対抗馬", "▲ 単穴馬"]

            for idx, (horse, col_c) in enumerate(zip(top_3, [c_h1, c_h2, c_h3])):
                with col_c:
                    st.markdown(f"""
                    <div class="horse-card {card_styles[idx]}">
                        <span class="{badges[idx]}">{mark_names[idx]}</span>
                        <div class="horse-name-title">{horse['馬番']}番 {horse['馬名']}</div>
                        <p style="color: #2563eb; font-weight: 700; font-size: 1.05rem; margin-bottom: 6px;">
                            AIスコア: {horse['AI予想スコア']} pt | 騎手: {horse['騎手']}
                        </p>
                        <p style="margin: 3px 0; color: #334155; font-size: 0.9rem;">
                            単勝オッズ: <strong>{horse['単勝オッズ']}倍</strong> ({horse['人気']}人気)
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("### 📋 AI予想・全出走馬データ一覧")
            cols = ['予想印', '枠番', '馬番', '馬名', 'AI予想スコア', '騎手', '血統適性', 'バイアス展開', '単勝オッズ', '人気', '馬体重']
            df_display = df[[c for c in cols if c in df.columns]]
            st.dataframe(df_display, use_container_width=True, hide_index=True)