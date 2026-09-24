import re
import requests
from bs4 import BeautifulSoup
import urllib3
import streamlit as st
import datetime
import pandas as pd

# SSL証明書警告の非表示化
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 全国10競馬場 (中央競馬 JRA) の完全コードマップ
JRA_VENUES = {
    "札幌": "01", "函館": "02", "福島": "03", "新潟": "04",
    "東京": "05", "中山": "06", "中京": "07", "京都": "08",
    "阪神": "09", "小倉": "10"
}

VENUE_MAP = JRA_VENUES
VENUE_CODE_TO_NAME = {v: k for k, v in JRA_VENUES.items()}

ALL_TICKET_TYPES = ["単勝", "複勝", "枠連", "馬連", "ワイド", "馬単", "3連複", "3連単"]

TOP_JOCKEYS_S = ["ルメール", "川田", "武豊", "坂井", "横山武", "戸崎", "モレイラ", "レーン", "レーン"]
TOP_JOCKEYS_A = ["松山", "鮫島克", "岩田望", "西村淳", "菅原明", "津村", "田辺", "デムーロ", "丹内", "佐々木"]

# ---------------------------------------------------------
# Streamlit Page Config & Mobile-First High-Contrast Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="Kuina AI Racing Pro (JRA中央競馬)",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    /* グローバルスタイル */
    .stApp {
        background: #f8fafc;
        color: #0f172a;
        font-family: 'Helvetica Neue', Arial, 'Hiragino Kaku Gothic ProN', 'Hiragino Sans', sans-serif;
    }
    
    /* ヒーローヘッダー */
    .hero-container {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
        border-radius: 16px;
        padding: 22px 24px;
        color: #ffffff;
        margin-bottom: 16px;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.25);
    }
    .hero-title {
        font-size: 2.2rem;
        font-weight: 900;
        color: #ffffff;
        margin: 0;
        letter-spacing: 0.02em;
    }
    .hero-sub {
        font-size: 0.88rem;
        color: #bfdbfe;
        font-weight: 700;
        letter-spacing: 0.06em;
        margin-top: 4px;
    }

    /* 予想馬カード */
    .horse-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 18px;
        border: 1px solid #cbd5e1;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        margin-bottom: 14px;
        height: auto !important;
        word-break: break-word !important;
        white-space: normal !important;
        overflow: visible !important;
    }
    .horse-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 18px rgba(0, 0, 0, 0.08);
    }
    .card-honmei { border-left: 6px solid #dc2626; background: #fff5f5; }
    .card-taikou { border-left: 6px solid #059669; background: #f0fdf4; }
    .card-tanana { border-left: 6px solid #2563eb; background: #eff6ff; }

    .badge-honmei { background: #dc2626; color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.85rem; }
    .badge-taikou { background: #059669; color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.85rem; }
    .badge-tanana { background: #2563eb; color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.85rem; }

    /* 買い目・指標カード */
    .bet-card {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 16px;
        height: 100%;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
        margin-bottom: 10px;
    }
    .bet-title {
        font-weight: 800;
        font-size: 1.05rem;
        color: #1e40af;
        margin-bottom: 6px;
    }
    .bet-code {
        font-family: monospace;
        font-size: 1.05rem;
        background: #f1f5f9;
        padding: 8px 12px;
        border-radius: 8px;
        color: #0f172a;
        font-weight: bold;
        border: 1px solid #cbd5e1;
        margin: 6px 0;
        white-space: pre-line;
        word-break: break-all;
    }
    .calc-card {
        background: #ffffff;
        border-radius: 12px;
        padding: 16px;
        border: 1px solid #3b82f6;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.08);
        margin-top: 12px;
    }
    .sim-card {
        background: #f0fdf4;
        border-radius: 12px;
        padding: 16px;
        border: 1px solid #10b981;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.08);
        margin-bottom: 12px;
    }
    .metric-container {
        background: #ffffff;
        border-radius: 12px;
        padding: 14px;
        border: 1px solid #cbd5e1;
        box-shadow: 0 2px 6px rgba(0,0,0,0.03);
        min-height: 80px;
        margin-bottom: 8px;
    }
    .metric-label {
        font-size: 0.82rem;
        color: #475569;
        font-weight: 800;
    }
    .metric-value {
        font-size: 1.2rem;
        font-weight: 800;
        color: #0f172a;
        margin-top: 2px;
        word-break: break-all !important;
        white-space: normal !important;
        overflow: visible !important;
    }
    div[data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        border: 1px solid #cbd5e1;
        background: #ffffff;
    }

    /* ----------------------------------------------------- */
    /* スマートフォン・モバイルボタン＆フォーム視認性完全強化 */
    /* ----------------------------------------------------- */
    div.stButton > button, .stButton > button {
        background: linear-gradient(135deg, #1e40af 0%, #2563eb 100%) !important;
        color: #ffffff !important;
        border: 2px solid #1d4ed8 !important;
        border-radius: 12px !important;
        font-weight: 800 !important;
        padding: 12px 18px !important;
        font-size: 1.02rem !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3) !important;
        width: 100% !important;
        text-shadow: 0 1px 2px rgba(0,0,0,0.2) !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button:hover, div.stButton > button:active, div.stButton > button:focus {
        background: linear-gradient(135deg, #1d4ed8 0%, #1e3a8a 100%) !important;
        color: #ffffff !important;
        border-color: #1e3a8a !important;
        box-shadow: 0 6px 16px rgba(30, 64, 175, 0.4) !important;
    }

    /* ダウンロードボタン & サブボタン */
    div[data-testid="stDownloadButton"] > button, button[data-testid="baseButton-secondary"] {
        background: linear-gradient(135deg, #059669 0%, #10b981 100%) !important;
        color: #ffffff !important;
        border: 2px solid #047857 !important;
        font-weight: 800 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25) !important;
        text-shadow: 0 1px 2px rgba(0,0,0,0.2) !important;
    }

    /* ラベルとセレクトボックスの文字をくっきり視認 */
    .stSelectbox label, .stRadio label, .stTextInput label, .stNumberInput label, .stMultiSelect label {
        color: #0f172a !important;
        font-weight: 800 !important;
        font-size: 0.95rem !important;
    }
    div[data-baseweb="select"] {
        background-color: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 10px !important;
    }
    div[data-baseweb="select"] * {
        color: #0f172a !important;
        font-weight: 700 !important;
    }

    /* レスポンシブ調整 */
    @media (max-width: 768px) {
        .hero-container {
            padding: 16px 18px !important;
            border-radius: 12px !important;
            margin-bottom: 12px !important;
        }
        .hero-title {
            font-size: 1.55rem !important;
        }
        .hero-sub {
            font-size: 0.72rem !important;
        }
        .horse-card {
            padding: 14px !important;
            margin-bottom: 12px !important;
            min-height: auto !important;
        }
        .bet-card, .calc-card, .sim-card, .metric-container {
            padding: 12px !important;
            margin-bottom: 8px !important;
        }
        .metric-value {
            font-size: 1.05rem !important;
        }
        div[data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 100% !important;
            margin-bottom: 8px !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Parsing Utility
# ---------------------------------------------------------
def parse_horse_weight_str(txt):
    if not txt:
        return "計不", 0
    clean_txt = str(txt).strip().replace(' ', '')
    if not clean_txt or clean_txt in ['--', '計不', '前計不']:
        return "計不", 0
    m = re.search(r'(\d{3,3})\(([-+]?\d+|\d+)\)', clean_txt)
    if m:
        w_val = m.group(1)
        d_val = int(m.group(2))
        return f"{w_val}kg", d_val
    m_single = re.search(r'(\d{3,3})', clean_txt)
    if m_single:
        return f"{m_single.group(1)}kg", 0
    return "計不", 0

def fetch_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=12, verify=False)
        res.raise_for_status()

        try:
            html_text = res.content.decode('utf-8')
        except UnicodeDecodeError:
            html_text = res.content.decode('euc-jp', errors='replace')

        if not html_text:
            html_text = res.content.decode('euc-jp', errors='replace')

        return BeautifulSoup(html_text, 'html.parser'), None
    except Exception as e:
        return None, f"通信エラーが発生しました: {e}"

# ---------------------------------------------------------
# JRA全12R完全網羅の全自動取得ロジック
# ---------------------------------------------------------
def fetch_race_list_by_date(dt_str):
    clean_date = re.sub(r'\D', '', str(dt_str))
    if len(clean_date) != 8:
        return [], "日付は8桁の数字(YYYYMMDD)で指定してください。"

    races_dict = {}
    venue_meetings = set() # (venue_code, prefix10, venue_name)

    urls = [
        f"https://race.netkeiba.com/top/race_list.html?kaijo_date={clean_date}",
        f"https://race.netkeiba.com/top/?kaijo_date={clean_date}",
        f"https://db.netkeiba.com/race/list/{clean_date}/",
        f"https://race.sp.netkeiba.com/?kaijo_date={clean_date}"
    ]

    for target_url in urls:
        soup, _ = fetch_html(target_url)
        if not soup:
            continue

        for a in soup.find_all('a'):
            href = a.get('href', '')
            m = re.search(r'race_id=(\d{12})', href) or re.search(r'/race/(\d{12})', href)
            if not m:
                continue

            r_id = m.group(1)
            v_code = r_id[4:6]

            # 中央競馬 (JRA: 会場コード 01〜10) のみに厳格限定
            if v_code not in VENUE_CODE_TO_NAME:
                continue

            venue_name = VENUE_CODE_TO_NAME[v_code]
            r_num = int(r_id[10:12])  # 01〜12R
            prefix10 = r_id[:10]      # 10桁の開催キー (例: 2026050201)

            venue_meetings.add((v_code, prefix10, venue_name))

            raw_text = a.text.strip().replace('\n', ' ')
            raw_text = re.sub(r'\s+', ' ', raw_text)

            clean_name = re.sub(r'^(📍|【.*?】|\d+R)\s*', '', raw_text).strip()
            clean_name = re.sub(r'(出馬表|オッズ|結果|映像|払戻|掲示板|データ)', '', clean_name).strip()

            if clean_name and len(clean_name) >= 2:
                display_title = f"📍【{venue_name}】 {r_num}R {clean_name}"
            else:
                display_title = f"📍【{venue_name}】 {r_num}R"

            if r_id not in races_dict or len(display_title) > len(races_dict[r_id]['name']):
                races_dict[r_id] = {
                    'id': r_id,
                    'name': display_title,
                    'venue': venue_name,
                    'r_num': r_num
                }

    # 補完ロジック: 検出された開催地(例: 東京, 中山)の全12R(1R〜12R)を確定補完生成
    for v_code, prefix10, venue_name in venue_meetings:
        for r_num in range(1, 13):
            full_r_id = f"{prefix10}{r_num:02d}"
            if full_r_id not in races_dict:
                races_dict[full_r_id] = {
                    'id': full_r_id,
                    'name': f"📍【{venue_name}】 {r_num}R",
                    'venue': venue_name,
                    'r_num': r_num
                }

    if not races_dict:
        return [], f"指定された日付 ({clean_date}) の中央競馬(JRA)レースデータは見つかりませんでした。"

    races = list(races_dict.values())
    races.sort(key=lambda x: x['id'])  # レースID順 (競馬場順・1R〜12R順) に並び替え
    return races, None

# ---------------------------------------------------------
# Netkeiba HTML Parsers
# ---------------------------------------------------------
def parse_db_netkeiba(soup):
    table = soup.select_one('table.race_table_01')
    if not table:
        return []

    header_tr = table.find('tr')
    if not header_tr:
        return []

    headers = [th.text.strip() for th in header_tr.find_all(['th', 'td'])]
    col_map = {}
    for idx, h in enumerate(headers):
        if '枠' in h: col_map['waku'] = idx
        elif '馬番' in h: col_map['uma'] = idx
        elif '馬名' in h: col_map['name'] = idx
        elif '騎手' in h: col_map['jockey'] = idx
        elif '斤量' in h: col_map['weight'] = idx
        elif '単勝' in h or 'オッズ' in h: col_map['odds'] = idx
        elif '人気' in h: col_map['pop'] = idx
        elif '体重' in h or '馬体重' in h: col_map['horse_weight'] = idx

    rows = table.find_all('tr')[1:]
    data_list = []
    for r in rows:
        tds = r.find_all('td')
        if len(tds) < 8: continue

        name_idx = col_map.get('name')
        if name_idx is None or name_idx >= len(tds):
            horse_a = r.select_one('a[href*="/horse/"]')
            if not horse_a: continue
            horse_name = horse_a.text.strip()
        else:
            horse_a = tds[name_idx].find('a')
            horse_name = horse_a.text.strip() if horse_a else tds[name_idx].text.strip()

        if not horse_name: continue

        jockey_name = "未定義"
        j_idx = col_map.get('jockey')
        if j_idx is not None and j_idx < len(tds):
            j_a = tds[j_idx].find('a')
            jockey_name = j_a.text.strip() if j_a else tds[j_idx].text.strip()

        wakaban = 1
        w_idx = col_map.get('waku')
        if w_idx is not None and w_idx < len(tds):
            try: wakaban = int(tds[w_idx].text.strip())
            except ValueError: pass

        umaban = 1
        u_idx = col_map.get('uma')
        if u_idx is not None and u_idx < len(tds):
            try: umaban = int(tds[u_idx].text.strip())
            except ValueError: pass

        weight_val = 55.0
        wt_idx = col_map.get('weight')
        if wt_idx is not None and wt_idx < len(tds):
            try: weight_val = float(tds[wt_idx].text.strip())
            except ValueError: pass

        odds_val = "未確定"
        o_idx = col_map.get('odds')
        if o_idx is not None and o_idx < len(tds):
            o_txt = tds[o_idx].text.strip()
            try: odds_val = float(o_txt)
            except ValueError: pass

        pop_val = "未確定"
        p_idx = col_map.get('pop')
        if p_idx is not None and p_idx < len(tds):
            p_txt = tds[p_idx].text.strip()
            try: pop_val = int(p_txt)
            except ValueError: pass

        hw_str = "計不"
        hw_diff = 0
        hw_idx = col_map.get('horse_weight')
        if hw_idx is not None and hw_idx < len(tds):
            hw_raw = tds[hw_idx].text.strip()
            hw_str, hw_diff = parse_horse_weight_str(hw_raw)

        data_list.append({
            '枠番': wakaban, '馬番': umaban, '馬名': horse_name,
            '騎手': jockey_name, '斤量': weight_val,
            '単勝オッズ': odds_val, '人気': pop_val,
            '馬体重': hw_str, '体重増減': hw_diff
        })

    return data_list

def parse_race_netkeiba(soup):
    table = soup.select_one('table.RaceTable01') or soup.select_one('table.RaceTable')
    if not table:
        return []

    rows = table.find_all('tr', class_=re.compile(r'HorseList|TrData'))
    if not rows:
        rows = [tr for tr in table.find_all('tr') if tr.find('td')]

    data_list = []
    for r in rows:
        tds = r.find_all('td')
        if len(tds) < 5: continue

        horse_td = r.select_one('td.HorseInfo') or r.select_one('td.Horse_Info') or r.select_one('td.HorseName')
        if not horse_td:
            horse_a = r.select_one('a[href*="/horse/"]')
            if horse_a: horse_name = horse_a.text.strip()
            else: continue
        else:
            h_a = horse_td.find('a')
            horse_name = h_a.text.strip() if h_a else horse_td.text.strip()

        if not horse_name: continue

        waku_td = r.select_one('td[class*="Waku"]') or r.select_one('td.waku')
        try: wakaban = int(waku_td.text.strip()) if waku_td else 1
        except ValueError: wakaban = 1

        uma_td = r.select_one('td[class*="Umaban"]') or r.select_one('td.umaban')
        try: umaban = int(uma_td.text.strip()) if uma_td else 1
        except ValueError: umaban = 1

        jockey_td = r.select_one('td.Jockey') or r.select_one('td.JockeyName')
        jockey_name = "未定義"
        if jockey_td:
            j_a = jockey_td.find('a')
            jockey_name = j_a.text.strip() if j_a else jockey_td.text.strip()

        weight_td = r.select_one('td.Weight')
        try: weight_val = float(weight_td.text.strip()) if weight_td else 55.0
        except ValueError: weight_val = 55.0

        odds_td = r.select_one('td.Odds') or r.select_one('td[id*="odds"]')
        odds_val = "未確定"
        if odds_td:
            try: odds_val = float(re.search(r'(\d+\.\d+|\d+)', odds_td.text.strip()).group(1))
            except (AttributeError, ValueError): pass

        pop_td = r.select_one('td.Popular') or r.select_one('td[id*="popularity"]')
        pop_val = "未確定"
        if pop_td:
            try: pop_val = int(re.search(r'(\d+)', pop_td.text.strip()).group(1))
            except (AttributeError, ValueError): pass

        hw_td = r.select_one('td.Weight_Info') or r.select_one('td.Horse_Weight')
        hw_str = "計不"
        hw_diff = 0
        if hw_td:
            hw_str, hw_diff = parse_horse_weight_str(hw_td.text.strip())

        data_list.append({
            '枠番': wakaban, '馬番': umaban, '馬名': horse_name,
            '騎手': jockey_name, '斤量': weight_val,
            '単勝オッズ': odds_val if odds_val is not None else "未確定",
            '人気': pop_val if pop_val is not None else "未確定",
            '馬体重': hw_str, '体重増減': hw_diff
        })

    return data_list

# ---------------------------------------------------------
# リアルタイムオッズ取得関数
# ---------------------------------------------------------
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
                uma_txt = tds[1].text.strip() if len(tds) > 1 else ''
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

# ---------------------------------------------------------
# AI Score Engine (5 Factor + 脚質展開 & 血統強化)
# ---------------------------------------------------------
def calculate_ai_scores(data_list, paddock_status_map=None, race_env=None):
    if not data_list: return data_list
    if paddock_status_map is None: paddock_status_map = {}
    if race_env is None:
        race_env = {
            'weather': '晴',
            'condition': '良',
            'track_type': '芝',
            'distance': 'マイル (1400-1600m)',
            'bias': '⚪ フラット',
            'pace': 'ミドルペース'
        }

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

        # 基本人気・オッズ評価
        pop_score = max(0, 40 - (p_val - 1) * 3.5)
        odds_score = max(0, 30 - (o_val * 0.6))
        weight_bonus = max(0, (56.0 - weight) * 2)

        # 1. 騎手評価
        j_score = 0.0
        j_comment = "鞍上標準"
        if any(tj in jockey for tj in TOP_JOCKEYS_S):
            j_score = 7.0
            j_comment = f"【トップ騎手】{jockey} (勝率・連対率特筆)"
        elif any(tj in jockey for tj in TOP_JOCKEYS_A):
            j_score = 4.0
            j_comment = f"【有力騎手】{jockey} (安定感高)"
        else:
            j_score = 1.0
            j_comment = f"【鞍上】{jockey}"

        # 2. 脚質・展開（ハイ/ミドル/スロー × 枠番）評価
        running_style = "差し"
        if waku <= 2 or uma in [1, 2, 3]:
            running_style = "逃げ・先行"
        elif p_val <= 3:
            running_style = "先行・好位"
        elif p_val >= 8:
            running_style = "追込"

        pace_score = 0.0
        pace_comment = "展開中立"
        if race_env['pace'] == 'スローペース（前残り）':
            if "逃げ" in running_style or "先行" in running_style:
                pace_score = 8.0
                pace_comment = f"【展開絶好】スローペース前残り ({running_style})"
            elif waku in [1, 2, 3]:
                pace_score = 6.0
                pace_comment = f"【展開有利】スロー・内枠{waku}枠先行"
            else:
                pace_score = 2.0
                pace_comment = f"【展開注意】スローペース前残り懸念 ({running_style})"
        elif race_env['pace'] == 'ハイペース（差し有利）':
            if "差し" in running_style or "追込" in running_style:
                pace_score = 8.0
                pace_comment = f"【展開絶好】ハイペース消耗戦差し一発 ({running_style})"
            elif waku in [6, 7, 8]:
                pace_score = 6.0
                pace_comment = f"【展開有利】ハイペース外枠差し ({waku}枠)"
            else:
                pace_score = -1.0
                pace_comment = f"【展開警戒】ハイペース先行馬消耗懸念"
        else: # ミドルペース
            pace_score = 4.0
            pace_comment = f"【展開適合】ミドルペース好位差し ({running_style})"

        # 3. 血統・コース（芝/ダート/道悪）適性評価
        blood_score = 4.0
        blood_comment = "血統適性標準"
        track_type = race_env.get('track_type', '芝')
        condition = race_env.get('condition', '良')

        dirt_sires = ["キング", "ルーラー", "シニスター", "ヘニー", "ドレフォン", "ゴールド", "ホッコータルマエ", "マジェスティック", "パイロ", "カジノ", "サウスヴィグラス"]
        turf_sires = ["ディープ", "ハーツ", "エピファネ", "ロードカナロア", "モーリス", "キズナ", "ダイワ", "スクリーン", "リアル", "ドゥラメンテ", "スワーヴ"]
        wet_sires = ["キング", "ボルド", "オルフェ", "ゴールド", "バゴ", "キズナ", "ハービンジャー", "シンボリ", "ルーラー"]

        if condition in ['重', '不良', '稍重']:
            if any(kw in horse_name for kw in wet_sires):
                blood_score = 8.0
                blood_comment = f"【血統特注】道悪パワー血統 ({condition}馬場適性◎)"
            else:
                blood_score = 5.0
                blood_comment = f"【血統適性】{condition}馬場力走可"
        elif track_type == 'ダート':
            if any(kw in horse_name for kw in dirt_sires):
                blood_score = 8.0
                blood_comment = "【血統特注】ダート強力適性血統 (パワー◎)"
            else:
                blood_score = 5.0
                blood_comment = "【血統適性】ダート対応血統"
        else: # 芝
            if any(kw in horse_name for kw in turf_sires):
                blood_score = 8.0
                blood_comment = "【血統特注】芝スピード＆瞬発力血統 (芝適性◎)"
            else:
                blood_score = 5.0
                blood_comment = "【血統適性】芝良馬場適性"

        # 4. 馬場バイアス
        bias_score = 0.0
        bias_comment = "馬場フラット"
        if "内伸び・前残り" in race_env['bias']:
            if waku in [1, 2, 3]:
                bias_score = 6.0
                bias_comment = f"【バイアス好走】内枠{waku}枠有利・前目追走可"
            elif waku in [4, 5]:
                bias_score = 3.0
                bias_comment = "【バイアス中立】中枠可"
            else:
                bias_score = -2.0
                bias_comment = "【バイアス懸念】外枠位置取り懸念"
        elif "外伸び・差し" in race_env['bias']:
            if waku in [6, 7, 8]:
                bias_score = 6.0
                bias_comment = f"【バイアス好走】外枠{waku}枠・伸び脚活きる展開"
            else:
                bias_score = 1.0
                bias_comment = "【バイアス標準】内〜中枠"
        else:
            bias_score = 2.0

        # 5. 体重・コンディション
        if abs(hw_diff) <= 4:
            weight_diff_score = 3.0
            hw_comment = "馬体重仕上がり良好"
        elif hw_diff >= 10:
            weight_diff_score = -3.0
            hw_comment = "馬体重太め残り警戒"
        elif hw_diff <= -10:
            weight_diff_score = -4.0
            hw_comment = "馬体重大幅減警戒"
        else:
            weight_diff_score = 0.0
            hw_comment = "馬体重許容範囲"

        p_status = paddock_status_map.get(uma, "⚪ 普通 (0pt)")
        if "✨ 絶好調" in p_status:
            paddock_score = 7.0
        elif "⚠️ 太め残り" in p_status:
            paddock_score = -4.0
        elif "💥 テンション高" in p_status:
            paddock_score = -5.0
        else:
            paddock_score = 0.0

        raw_score = pop_score + odds_score + weight_bonus + j_score + blood_score + pace_score + bias_score + weight_diff_score + paddock_score + 5
        score = round(min(99.9, max(10.0, raw_score)), 1)

        d_copy = dict(d)
        d_copy['AI予想スコア'] = score
        d_copy['脚質'] = running_style
        d_copy['パドック評価'] = p_status
        d_copy['騎手評価'] = j_comment
        d_copy['血統適性'] = blood_comment
        d_copy['バイアス展開'] = f"{bias_comment} / {pace_comment}"
        d_copy['_p_comment'] = f"{hw_comment} | {j_comment} | {blood_comment} | {pace_comment}"
        scored_items.append(d_copy)

    # 勝率・期待値(EV)・期待回収率(%)の自動計算
    total_score = sum(item['AI予想スコア'] for item in scored_items) or 100.0
    for item in scored_items:
        win_prob = (item['AI予想スコア'] / total_score) * 100.0
        item['AI想定勝率'] = f"{round(win_prob, 1)}%"
        
        try:
            o_val = float(item['単勝オッズ'])
            ev = round((win_prob / 100.0) * o_val, 2)
            roi = round(ev * 100, 1)
            item['期待値(EV)'] = ev
            item['期待回収率'] = f"{roi}%"
            if ev >= 1.2:
                item['妙味判定'] = "🔥 超激高妙味 (EV 1.2+)"
            elif ev >= 1.0:
                item['妙味判定'] = "💥 妙味アリ (EV 1.0+)"
            elif ev >= 0.8:
                item['妙味判定'] = "⚖️ 適正オッズ"
            else:
                item['妙味判定'] = "⚠️ 妙味低"
        except (ValueError, TypeError):
            item['期待値(EV)'] = "未確定"
            item['期待回収率'] = "未確定"
            item['妙味判定'] = "オッズ未確定"

    scored_items.sort(key=lambda x: x['AI予想スコア'], reverse=True)
    mark_list = ['◎ 本命', '◯ 対抗', '▲ 単穴', '△ 連下', '△ 連下', '☆ 穴馬']
    
    for idx, item in enumerate(scored_items):
        mark = mark_list[idx] if idx < len(mark_list) else 'ー'
        item['予想印'] = mark
        
        o_str = f"{item['単勝オッズ']}倍" if item['単勝オッズ'] != "未確定" else "オッズ未確定"
        p_str = f"{item['人気']}人気" if item['人気'] != "未確定" else ""
        p_info = item.get('_p_comment', '')
        ev_info = f"期待値{item['期待値(EV)']} (回収率{item['期待回収率']})" if item['期待値(EV)'] != "未確定" else ""

        if idx == 0:
            item['予想根拠'] = f"【絶好の軸馬】単勝{o_str}（{p_str}）。AI総合指数最高値({item['AI予想スコア']}pt)。{ev_info}。{p_info}。"
        elif idx == 1:
            item['予想根拠'] = f"【対抗馬】単勝{o_str}（{p_str}）。{p_info}。ハイレベルな指数をマーク。"
        elif idx == 2:
            item['予想根拠'] = f"【単穴一発】単勝{o_str}（{p_str}）。{p_info}。展開噛み合えば頭まで。"
        elif idx == 3 or idx == 4:
            item['予想根拠'] = f"【連下候補】単勝{o_str}。{p_info}。ヒモ軸として確実な押さえ。"
        elif idx == 5:
            item['予想根拠'] = f"【穴馬特注】単勝{o_str}（{p_str}）。{ev_info}。{p_info}。高配当のキーマン。"
        else:
            item['予想根拠'] = f"静観評価（スコア {item['AI予想スコア']}pt / {p_info}）"

        del item['_p_comment']

    scored_items.sort(key=lambda x: x['馬番'] if isinstance(x['馬番'], int) else 99)
    return scored_items

# ---------------------------------------------------------
# Betting Strategy Generator
# ---------------------------------------------------------
def generate_betting_recommendations(data_list, strategy_mode="バランス重視（王道）", selected_ticket_types=None):
    honmei = next((d for d in data_list if '◎' in d.get('予想印', '')), None)
    taikou = next((d for d in data_list if '◯' in d.get('予想印', '')), None)
    tanana = next((d for d in data_list if '▲' in d.get('予想印', '')), None)
    renka_list = [d for d in data_list if '△' in d.get('予想印', '')]
    anama = next((d for d in data_list if '☆' in d.get('予想印', '')), None)

    all_candidates = [d for d in [honmei, taikou, tanana] + renka_list + [anama] if d is not None]
    if not honmei or len(all_candidates) < 2:
        return []

    h_num = honmei['馬番']
    t_num = taikou['馬番'] if taikou else None
    a_num = tanana['馬番'] if tanana else None
    renka_nums = [d['馬番'] for d in renka_list]
    ana_num = anama['馬番'] if anama else None

    recommendations = []

    if strategy_mode == "本命堅実（低リスク）":
        recommendations.append({
            "ticket": "単勝", "name": f"単勝 軸信頼勝負", "combination": f"【{h_num}】",
            "info": f"本命馬 {honmei['馬名']}({h_num}番) の単勝1点突破",
            "type": "単勝", "count": 1, "code": f"{h_num}", "想定オッズ": honmei.get('単勝オッズ', 3.5),
            "期待回収率": honmei.get('期待回収率', '110%')
        })
        if t_num:
            recommendations.append({
                "ticket": "馬連", "name": f"馬連 本命-対抗1点", "combination": f"【{h_num} - {t_num}】",
                "info": f"最高評価の2頭 ({honmei['馬名']} × {taikou['馬名']}) による本命1点厚め勝負",
                "type": "馬連", "count": 1, "code": f"{h_num}-{t_num}", "想定オッズ": 8.5,
                "期待回収率": "125%"
            })
        if t_num and a_num:
            recommendations.append({
                "ticket": "ワイド", "name": f"ワイド 2頭軸流し", "combination": f"【{h_num} - {t_num}, {a_num}】",
                "info": "的中率を極限まで高めた上位3頭BOX・流し",
                "type": "ワイド", "count": 2, "code": f"{h_num}-{t_num}\n{h_num}-{a_num}", "想定オッズ": 4.8,
                "期待回収率": "115%"
            })

    elif strategy_mode == "穴馬一発（一獲千金）":
        if ana_num:
            recommendations.append({
                "ticket": "単勝", "name": "単勝 穴馬一発逆転", "combination": f"【{ana_num}】",
                "info": f"特注穴馬 {anama['馬名']}({ana_num}番) の単勝単独勝負",
                "type": "単勝", "count": 1, "code": f"{ana_num}", "想定オッズ": anama.get('単勝オッズ', 25.0),
                "期待回収率": "180%"
            })
            recommendations.append({
                "ticket": "馬連", "name": "馬連 穴馬軸流し", "combination": f"【{ana_num} - {h_num}, {t_num}】",
                "info": f"穴馬({ana_num}番)から本命・対抗へ流して万馬券狙い",
                "type": "馬連", "count": 2, "code": f"{ana_num}-{h_num}\n{ana_num}-{t_num}", "想定オッズ": 45.0,
                "期待回収率": "210%"
            })
        if t_num and a_num and renka_nums:
            others = [t_num, a_num] + renka_nums[:2]
            codes = [f"{h_num}-{x}-{y}" for idx_x, x in enumerate(others) for y in others[idx_x+1:]]
            recommendations.append({
                "ticket": "3連複", "name": "3連複 本命1頭軸手広く", "combination": f"【{h_num} - {', '.join(map(str, others))}】",
                "info": "本命軸から波乱に備えて手広く高配当狙い",
                "type": "3連複", "count": len(codes), "code": "\n".join(codes[:6]), "想定オッズ": 65.0,
                "期待回収率": "195%"
            })

    else: # バランス重視
        if t_num:
            recommendations.append({
                "ticket": "馬連", "name": "馬連 本命軸流し", "combination": f"【{h_num} - {t_num}, {a_num if a_num else ''}】",
                "info": f"軸馬({h_num}番)から上位評価馬へスマート流し",
                "type": "馬連", "count": 2 if a_num else 1, "code": f"{h_num}-{t_num}" + (f"\n{h_num}-{a_num}" if a_num else ""),
                "想定オッズ": 12.5, "期待回収率": "135%"
            })
        if t_num and a_num:
            recommendations.append({
                "ticket": "ワイド", "name": "ワイド 本命本線", "combination": f"【{h_num} - {t_num}, {a_num}】",
                "info": "的中率と回収率のバランスが最も優れた王道スタイル",
                "type": "ワイド", "count": 2, "code": f"{h_num}-{t_num}\n{h_num}-{a_num}", "想定オッズ": 6.2,
                "期待回収率": "120%"
            })
        if t_num and a_num and renka_nums:
            stream_targets = [t_num, a_num] + renka_nums[:2]
            c_list = [f"{h_num}-{st_t}" for st_t in stream_targets]
            recommendations.append({
                "ticket": "3連複", "name": "3連複 軸1頭ながし", "combination": f"【{h_num} - {', '.join(map(str, stream_targets))}】",
                "info": "軸1頭から相手4頭へ総流し。的中感と高配当を両立",
                "type": "3連複", "count": len(c_list)*(len(c_list)-1)//2, "code": "\n".join(c_list[:5]),
                "想定オッズ": 38.0, "期待回収率": "150%"
            })

    if selected_ticket_types:
        filtered = [r for r in recommendations if r['type'] in selected_ticket_types]
        return filtered if filtered else recommendations
    return recommendations

# ---------------------------------------------------------
# Capital Allocation Calculator
# ---------------------------------------------------------
def calculate_capital_allocation(tickets, total_budget):
    if not tickets or total_budget < 100:
        return []

    results = []
    num_tickets = len(tickets)
    base_alloc = (total_budget // (num_tickets * 100)) * 100
    if base_alloc < 100:
        base_alloc = 100

    rem_budget = total_budget
    for idx, t in enumerate(tickets):
        if idx == num_tickets - 1:
            alloc = max(100, (rem_budget // 100) * 100)
        else:
            alloc = base_alloc
            rem_budget -= alloc

        odds = t.get('odds', 10.0)
        exp_return = int(alloc * odds)
        results.append({
            'name': t['name'],
            'type': t['type'],
            'combination': t['combination'],
            'alloc': alloc,
            'odds': odds,
            'exp_return': exp_return
        })
    return results

# ---------------------------------------------------------
# Data Fetcher Main Handoff
# ---------------------------------------------------------
def get_race_data(input_id, paddock_status_map=None, race_env=None, force_reload=False):
    clean_id = re.sub(r'\D', '', str(input_id))
    if len(clean_id) != 12:
        return None, "レースIDは12桁の数字(例: 202405021211)で指定してください。"

    db_url = f"https://db.netkeiba.com/race/{clean_id}/"
    soup_db, err_db = fetch_html(db_url)
    data_list = []
    if soup_db:
        data_list = parse_db_netkeiba(soup_db)

    if not data_list:
        race_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={clean_id}"
        soup_race, err_race = fetch_html(race_url)
        if soup_race:
            data_list = parse_race_netkeiba(soup_race)

    if not data_list:
        return None, f"指定されたレースID ({clean_id}) の出馬表データを取得できませんでした。"

    # オッズ補完
    has_missing = any(d['単勝オッズ'] == "未確定" for d in data_list) or force_reload
    if has_missing:
        odds_map = fetch_odds_data(clean_id)
        if odds_map:
            for d in data_list:
                uma = d['馬番']
                if uma in odds_map:
                    d['単勝オッズ'] = odds_map[uma]['odds']
                    if odds_map[uma]['pop'] != "未確定":
                        d['人気'] = odds_map[uma]['pop']

    data_list = calculate_ai_scores(data_list, paddock_status_map, race_env)
    return data_list, None

# ---------------------------------------------------------
# Streamlit Application GUI
# ---------------------------------------------------------
def main():
    st.markdown("""
    <div class="hero-container">
        <div class="hero-title">🏇 Kuina AI Racing Pro</div>
        <div class="hero-sub">JRA中央競馬全12R完全網羅 × リアルタイムオッズ期待値(EV) × 脚質展開・血統AI解析</div>
    </div>
    """, unsafe_allow_html=True)

    # セッション状態の初期化
    if 'race_data' not in st.session_state: st.session_state['race_data'] = None
    if 'current_race_id' not in st.session_state: st.session_state['current_race_id'] = ""
    if 'paddock_status_map' not in st.session_state: st.session_state['paddock_status_map'] = {}
    if 'balance_history' not in st.session_state: st.session_state['balance_history'] = []

    # メインコントロールタスク
    with st.expander("📅 1. 日付からJRA全12Rを一括取得・選択", expanded=True):
        col_dt, col_btn = st.columns([2, 3])
        with col_dt:
            today_dt = datetime.date.today()
            sel_date = st.date_input("開催日を選択", today_dt)
        with col_btn:
            st.write("")
            st.write("")
            fetch_click = st.button("🔍 JRA全12Rを一括取得", use_container_width=True)

        if fetch_click or 'jra_races_list' in st.session_state:
            if fetch_click:
                dt_str = sel_date.strftime("%Y%m%d")
                with st.spinner(f"{sel_date.strftime('%Y年%m月%d日')} のJRA全レースを解析中..."):
                    races, err = fetch_race_list_by_date(dt_str)
                    if err:
                        st.error(err)
                    else:
                        st.session_state['jra_races_list'] = races
                        st.success(f"🎉 全 {len(races)} レースの読み込みが完全完了しました！")

            if 'jra_races_list' in st.session_state and st.session_state['jra_races_list']:
                r_options = {r['name']: r['id'] for r in st.session_state['jra_races_list']}
                sel_race_name = st.selectbox("🎯 対象レースを選択", list(r_options.keys()))
                target_race_id = r_options[sel_race_name]
            else:
                target_race_id = "202405021211" # デフォルト
        else:
            target_race_id = "202405021211"

    # レース条件・馬場環境のカスタマイズ
    with st.expander("⚙️ 2. レース環境・脚質展開・血統条件の設定", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            env_weather = st.selectbox("天候", ["晴", "曇", "雨", "小雨"], index=0)
            env_track = st.selectbox("トラック", ["芝", "ダート"], index=0)
        with c2:
            env_condition = st.selectbox("馬場状態", ["良", "稍重", "重", "不良"], index=0)
            env_dist = st.selectbox("距離", ["マイル (1400-1600m)", "短距離 (1200m以下)", "中距離 (1800-2200m)", "長距離 (2400m以上)"], index=0)
        with c3:
            env_bias = st.selectbox("トラックバイアス", ["⚪ フラット", "🟢 内伸び・前残り", "🔵 外伸び・差し"], index=0)
        with c4:
            env_pace = st.selectbox("想定ペース (脚質影響)", ["ミドルペース", "スローペース（前残り）", "ハイペース（差し有利）"], index=0)

        race_env = {
            'weather': env_weather,
            'condition': env_condition,
            'track_type': env_track,
            'distance': env_dist,
            'bias': env_bias,
            'pace': env_pace
        }

    st.write("")
    analyze_click = st.button("🚀 この条件でAI解析・リアルタイムオッズ計算を実行", use_container_width=True)

    if analyze_click:
        with st.spinner("リアルタイムオッズ・AIスコア・期待値(EV)を計算中..."):
            data_list, err = get_race_data(target_race_id, st.session_state['paddock_status_map'], race_env, force_reload=True)
            if err:
                st.error(err)
            else:
                st.session_state['race_data'] = data_list
                st.session_state['current_race_id'] = target_race_id
                st.success("✨ AI解析および期待値(EV)計算が完了しました！")

    # メイン結果表示
    if st.session_state['race_data']:
        data_list = st.session_state['race_data']
        
        honmei = next((d for d in data_list if '◎' in d.get('予想印', '')), None)
        taikou = next((d for d in data_list if '◯' in d.get('予想印', '')), None)
        tanana = next((d for d in data_list if '▲' in d.get('予想印', '')), None)

        st.markdown("### 🏆 AI予想 本命・対抗・単穴 PICK UP")
        m1, m2, m3 = st.columns(3)
        with m1:
            if honmei:
                st.markdown(f'''
                <div class="horse-card card-honmei">
                    <span class="badge-honmei">◎ 本命</span>
                    <div class="horse-name-title">{honmei['馬名']} ({honmei['馬番']}番)</div>
                    <div>AI指数: <strong>{honmei['AI予想スコア']}pt</strong> (勝率{honmei.get('AI想定勝率', '-')})</div>
                    <div>単勝オッズ: <strong>{honmei['単勝オッズ']}倍</strong> ({honmei['人気']}人気)</div>
                    <div>期待値(EV): <strong>{honmei.get('期待値(EV)', '-')}</strong> ({honmei.get('妙味判定', '-')})</div>
                    <div style="font-size:0.85rem; color:#475569; margin-top:8px;">{honmei['予想根拠']}</div>
                </div>
                ''', unsafe_allow_html=True)
        with m2:
            if taikou:
                st.markdown(f'''
                <div class="horse-card card-taikou">
                    <span class="badge-taikou">◯ 対抗</span>
                    <div class="horse-name-title">{taikou['馬名']} ({taikou['馬番']}番)</div>
                    <div>AI指数: <strong>{taikou['AI予想スコア']}pt</strong> (勝率{taikou.get('AI想定勝率', '-')})</div>
                    <div>単勝オッズ: <strong>{taikou['単勝オッズ']}倍</strong> ({taikou['人気']}人気)</div>
                    <div>期待値(EV): <strong>{taikou.get('期待値(EV)', '-')}</strong> ({taikou.get('妙味判定', '-')})</div>
                    <div style="font-size:0.85rem; color:#475569; margin-top:8px;">{taikou['予想根拠']}</div>
                </div>
                ''', unsafe_allow_html=True)
        with m3:
            if tanana:
                st.markdown(f'''
                <div class="horse-card card-tanana">
                    <span class="badge-tanana">▲ 単穴</span>
                    <div class="horse-name-title">{tanana['馬名']} ({tanana['馬番']}番)</div>
                    <div>AI指数: <strong>{tanana['AI予想スコア']}pt</strong> (勝率{tanana.get('AI想定勝率', '-')})</div>
                    <div>単勝オッズ: <strong>{tanana['単勝オッズ']}倍</strong> ({tanana['人気']}人気)</div>
                    <div>期待値(EV): <strong>{tanana.get('期待値(EV)', '-')}</strong> ({tanana.get('妙味判定', '-')})</div>
                    <div style="font-size:0.85rem; color:#475569; margin-top:8px;">{tanana['予想根拠']}</div>
                </div>
                ''', unsafe_allow_html=True)

        st.markdown("### 📊 全出走馬 AIスコア＆リアルタイム期待値(EV)一覧")
        df = pd.DataFrame(data_list)
        display_cols = ['予想印', '枠番', '馬番', '馬名', 'AI予想スコア', 'AI想定勝率', '単勝オッズ', '人気', '期待値(EV)', '期待回収率', '妙味判定', '脚質', '騎手', '血統適性', 'バイアス展開', '予想根拠']
        existing_cols = [c for c in display_cols if c in df.columns]
        
        st.dataframe(df[existing_cols], use_container_width=True, hide_index=True)

        # 買い目生成
        st.markdown("### 🎯 AI推奨買い目＆オッズ資金配分")
        col_strat, col_budget = st.columns([2, 2])
        with col_strat:
            strat_mode = st.selectbox("投資戦略モード", ["バランス重視（王道）", "本命堅実（低リスク）", "穴馬一発（一獲千金）"])
        with col_budget:
            budget_val = st.number_input("投資総予算 (円)", min_value=100, max_value=1000000, value=3000, step=500)

        recs = generate_betting_recommendations(data_list, strat_mode)
        if recs:
            allocs = calculate_capital_allocation(recs, budget_val)
            r_cols = st.columns(len(allocs)) if allocs else []
            for idx, item in enumerate(allocs):
                with r_cols[idx if idx < len(r_cols) else 0]:
                    st.markdown(f'''
                    <div class="bet-card">
                        <div class="bet-title">{item['name']}</div>
                        <div>買い目: <strong>{item['combination']}</strong></div>
                        <div>配分金額: <strong style="color:#2563eb; font-size:1.1rem;">{item['alloc']}円</strong></div>
                        <div>想定オッズ: {item['odds']}倍 ➔ 想定払戻: <strong>{item['exp_return']}円</strong></div>
                    </div>
                    ''', unsafe_allow_html=True)

if __name__ == '__main__':
    main()
