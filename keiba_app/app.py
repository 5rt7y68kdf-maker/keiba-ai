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

TOP_JOCKEYS_S = ["ルメール", "川田", "武豊", "坂井", "横山武", "戸崎", "モレイラ", "レーン"]
TOP_JOCKEYS_A = ["松山", "鮫島克", "岩田望", "西村淳", "菅原明", "津村", "田辺", "デムーロ", "丹内"]

# ---------------------------------------------------------
# Streamlit Page Config & High-Contrast Light Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="Kuina AI Racing Pro (JRA中央競馬)",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    /* 画面上部の余白をしっかり確保してタイトル見切れを完全に防止 */
    .block-container {
        padding-top: 3.5rem !important;
        padding-bottom: 1.5rem !important;
        padding-left: 1.0rem !important;
        padding-right: 1.0rem !important;
        max-width: 99% !important;
    }
    div[data-testid="stVerticalBlock"] {
        gap: 0.6rem !important;
    }
    
    .stApp {
        background: #f8fafc;
        color: #0f172a;
        font-family: 'Helvetica Neue', Arial, 'Hiragino Kaku Gothic ProN', 'Hiragino Sans', sans-serif;
        line-height: 1.6 !important;
    }
    
    /* 洗練されたメインヘッダー */
    .hero-container {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
        border-radius: 12px;
        padding: 16px 22px;
        color: #ffffff;
        margin-top: 8px;
        margin-bottom: 16px;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.15);
    }
    .hero-title {
        font-size: 1.7rem;
        font-weight: 900;
        color: #ffffff;
        margin: 0;
        line-height: 1.25;
        letter-spacing: -0.01em;
    }
    .hero-sub {
        font-size: 0.85rem;
        color: #93c5fd;
        font-weight: 700;
        margin-top: 4px;
        letter-spacing: 0.05em;
    }

    /* ボタン */
    .stButton>button {
        width: 100% !important;
        background: linear-gradient(135deg, #1e40af 0%, #2563eb 100%) !important;
        color: #ffffff !important;
        font-weight: 800 !important;
        font-size: 0.95rem !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 10px 16px !important;
        box-shadow: 0 2px 6px rgba(37, 99, 235, 0.2) !important;
    }

    /* 予想カード (行間ゆったり・見やすさ重視) */
    .horse-card {
        background: #ffffff;
        border-radius: 10px;
        padding: 14px 16px !important;
        border: 1px solid #cbd5e1;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);
        margin-bottom: 10px !important;
        word-break: break-word !important;
        white-space: normal !important;
        line-height: 1.6 !important;
    }
    .card-honmei { border-left: 5px solid #dc2626; background: #fff5f5; }
    .card-taikou { border-left: 5px solid #059669; background: #f0fdf4; }
    .card-tanana { border-left: 5px solid #2563eb; background: #eff6ff; }

    .badge-honmei { background: #dc2626; color: white; padding: 3px 10px; border-radius: 12px; font-weight: bold; font-size: 0.8rem; }
    .badge-taikou { background: #059669; color: white; padding: 3px 10px; border-radius: 12px; font-weight: bold; font-size: 0.8rem; }
    .badge-tanana { background: #2563eb; color: white; padding: 3px 10px; border-radius: 12px; font-weight: bold; font-size: 0.8rem; }

    /* 枠番・馬番バッジの左右幅をタイトに凝縮 */
    .waku-badge {
        display: inline-block;
        background: #334155;
        color: #ffffff;
        font-weight: 800;
        padding: 1px 4px !important;
        border-radius: 3px;
        font-size: 0.78rem;
        margin-right: 2px !important;
        letter-spacing: -0.02em;
    }
    .uma-badge {
        display: inline-block;
        background: #0f172a;
        color: #ffffff;
        font-weight: 800;
        padding: 1px 5px !important;
        border-radius: 3px;
        font-size: 0.85rem;
        margin-right: 3px !important;
        letter-spacing: -0.02em;
    }

    /* 展開・指標・計算カード */
    .pace-card {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 10px 12px !important;
        margin-bottom: 6px !important;
        line-height: 1.5 !important;
    }
    .pace-title {
        font-weight: 800;
        font-size: 0.88rem;
        margin-bottom: 4px;
        padding: 2px 6px;
        border-radius: 4px;
        display: inline-block;
    }
    .pace-nige { background: #fee2e2; color: #991b1b; }
    .pace-senko { background: #d1fae5; color: #065f46; }
    .pace-sashi { background: #dbeafe; color: #1e40af; }
    .pace-oikomi { background: #fef9c3; color: #854d0e; }

    .bet-card, .calc-card, .sim-card {
        background: #ffffff;
        border-radius: 8px;
        padding: 12px 14px !important;
        border: 1px solid #cbd5e1;
        box-shadow: 0 1px 4px rgba(0,0,0,0.02);
        margin-bottom: 8px !important;
        line-height: 1.5 !important;
    }
    .bet-title {
        font-weight: 700;
        font-size: 0.92rem;
        color: #1e40af;
        margin-bottom: 4px;
    }
    .bet-code {
        font-family: monospace;
        font-size: 0.92rem;
        background: #f1f5f9;
        padding: 6px 10px;
        border-radius: 4px;
        color: #0f172a;
        font-weight: bold;
        border: 1px solid #cbd5e1;
        margin: 4px 0;
        white-space: pre-line;
        word-break: break-all;
    }

    .metric-container {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 10px 14px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
        line-height: 1.4 !important;
    }
    .metric-label {
        font-size: 0.76rem;
        color: #64748b;
        font-weight: 700;
    }
    .metric-value {
        font-size: 1.08rem;
        font-weight: 800;
        color: #0f172a;
        margin-top: 2px;
    }
    div[data-testid="stDataFrame"] {
        border-radius: 8px;
        border: 1px solid #cbd5e1;
        background: #ffffff;
    }
    
    div[data-testid="stDataFrame"] td, div[data-testid="stDataFrame"] th {
        padding: 6px 8px !important;
        line-height: 1.5 !important;
    }
    hr {
        margin: 0.8rem 0 !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Helper Functions & Formatting
# ---------------------------------------------------------
def format_odds_val(val):
    if val is None or val == "未確定" or val == "" or str(val).strip() in ['--', '---.-']:
        return "未確定"
    try:
        f_val = float(val)
        return f"{f_val:.1f}"
    except (ValueError, TypeError):
        return "未確定"

def parse_horse_weight_str(txt):
    if not txt:
        return "計不", 0
    clean_txt = str(txt).strip().replace(' ', '')
    if not clean_txt or clean_txt in ['--', '計不', '前計不', '---']:
        return "計不", 0

    m = re.search(r'(\d{3,4})\s*\\(\s*([+-]?\d+)\s*\\)', clean_txt)
    if m:
        w_val = m.group(1)
        d_val = int(m.group(2))
        d_str = f"+{d_val}" if d_val > 0 else str(d_val)
        return f"{w_val}kg ({d_str})", d_val

    m_note = re.search(r'(\d{3,4})\s*\\((.*)\\)', clean_txt)
    if m_note:
        return f"{m_note.group(1)}kg ({m_note.group(2)})", 0

    m_plain = re.search(r'(\d{3,4})', clean_txt)
    if m_plain:
        return f"{m_plain.group(1)}kg", 0

    return "計不", 0

def infer_leg_style_from_passage(passage_txt, umaban, wakaban, pop_val):
    if passage_txt:
        m = re.search(r'(\d{1,2})', str(passage_txt))
        if m:
            first_pos = int(m.group(1))
            if first_pos <= 2: return "逃げ"
            elif first_pos <= 5: return "先行"
            elif first_pos <= 10: return "差し"
            else: return "追込"

    txt = str(passage_txt)
    if "逃" in txt: return "逃げ"
    if "先" in txt: return "先行"
    if "差" in txt: return "差し"
    if "追" in txt: return "追込"

    if umaban in [1, 2] or (wakaban == 1 and (isinstance(pop_val, int) and pop_val <= 5)):
        return "逃げ"
    elif umaban in [3, 4, 5, 6]:
        return "先行"
    elif umaban in [7, 8, 9, 10, 11, 12]:
        return "差し"
    else:
        return "追込"

# ---------------------------------------------------------
# Web Scraping & Data Fetching (1R〜12R 全レース完全網羅)
# ---------------------------------------------------------
def fetch_html(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://race.netkeiba.com/'
    }
    try:
        session = requests.Session()
        session.headers.update(headers)
        res = session.get(url, verify=False, timeout=15)
        if res.status_code != 200:
            return None, f"アクセスエラー (ステータスコード: {res.status_code})"

        html_text = None
        for enc in ['euc-jp', 'euc_jp', 'cp932', 'shift_jis', 'utf-8']:
            try:
                html_text = res.content.decode(enc)
                if 'netkeiba' in html_text or '馬名' in html_text or '出馬' in html_text or 'レース' in html_text:
                    break
            except Exception:
                continue

        if not html_text:
            html_text = res.content.decode('euc-jp', errors='replace')

        return BeautifulSoup(html_text, 'html.parser'), None
    except Exception as e:
        return None, f"通信エラーが発生しました: {e}"

def extract_race_id_from_input(user_input):
    if not user_input: return None
    m = re.search(r'(\d{12})', str(user_input))
    if m: return m.group(1)
    m10 = re.search(r'(\d{10})', str(user_input))
    if m10: return "20" + m10.group(1)
    return None

def fetch_race_list_by_date(dt_str):
    clean_date = re.sub(r'\D', '', str(dt_str))
    if len(clean_date) != 8:
        return [], "日付は8桁の数字(YYYYMMDD)で指定してください。"

    urls = [
        f"https://race.netkeiba.com/top/race_list.html?kaijo_date={clean_date}",
        f"https://race.netkeiba.com/top/?kaijo_date={clean_date}",
        f"https://db.netkeiba.com/race/list/{clean_date}/"
    ]

    discovered_prefixes = set()
    title_map = {}

    for target_url in urls:
        soup, _ = fetch_html(target_url)
        if not soup: continue

        for a in soup.find_all('a'):
            href = a.get('href', '')
            m = re.search(r'race_id=(\d{12})', href) or re.search(r'/race/(\d{12})', href)
            if not m: continue

            r_id = m.group(1)
            v_code = r_id[4:6]
            if v_code not in VENUE_CODE_TO_NAME: continue

            prefix = r_id[0:10]
            discovered_prefixes.add(prefix)

            raw_text = a.text.strip().replace('\n', ' ')
            raw_text = re.sub(r'\s+', ' ', raw_text)
            clean_name = re.sub(r'^(📍|【.*?】|\d+R)\s*', '', raw_text).strip()
            clean_name = re.sub(r'(出馬表|オッズ|結果|映像|払戻|掲示板|データ)', '', clean_name).strip()

            if clean_name and len(clean_name) >= 2:
                title_map[r_id] = clean_name

    if not discovered_prefixes:
        yr = clean_date[0:4]
        for v_code in ["05", "06", "07", "08", "09"]:
            discovered_prefixes.add(f"{yr}{v_code}0101")

    races = []
    for prefix in sorted(discovered_prefixes):
        v_code = prefix[4:6]
        venue_name = VENUE_CODE_TO_NAME.get(v_code, "競馬場")
        
        for r_num in range(1, 13):
            r_id = f"{prefix}{r_num:02d}"
            clean_title = title_map.get(r_id, "")
            
            if clean_title:
                display_name = f"📍【{venue_name}】 {r_num}R  {clean_title}"
            else:
                display_name = f"📍【{venue_name}】 {r_num}R"

            races.append({
                'id': r_id,
                'name': display_name,
                'venue': venue_name,
                'r_num': r_num
            })

    return races, None

def parse_race_netkeiba(soup):
    rows = soup.select('tr.HorseList') or soup.select('table.ShutubaTable tr') or soup.select('table.Shutuba_Table tr') or soup.select('table.ResultTable tr')
    if not rows:
        all_trs = soup.find_all('tr')
        rows = [tr for tr in all_trs if tr.select_one('a[href*="/horse/"]')]

    if not rows: return []

    data_list = []
    seen_uma = set()
    for idx, r in enumerate(rows, start=1):
        td_list = r.find_all(['td', 'th'])
        if len(td_list) < 2: continue

        horse_a = r.select_one('a[href*="/horse/"]') or r.select_one('.HorseName a')
        if not horse_a: continue
        horse_name = horse_a.text.strip()
        if not horse_name or horse_name in ['馬名', '競走馬']: continue

        jockey_a = r.select_one('a[href*="/jockey/"]') or r.select_one('.Jockey a')
        jockey_name = jockey_a.text.strip() if jockey_a else "未定義"

        wakaban, umaban = None, None
        odds_val = "未確定"
        pop_val = "未確定"
        weight_val = 55.0
        hw_str, hw_diff = "計不", 0
        passage_txt = ""

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
                    try: odds_val = round(float(m_o.group(1)), 1)
                    except ValueError: pass

            if 'popular' in cls_str or 'pop' in cls_str or 'ninki' in cls_str:
                m_p = re.search(r'(\d+)', text)
                if m_p:
                    try: pop_val = int(m_p.group(1))
                    except ValueError: pass

            if 'past' in cls_str or 'result' in cls_str or 'passage' in cls_str:
                passage_txt += " " + text

            if 'weight' in cls_str or 'weight' in (td.get('id') or '').lower() or re.search(r'\d{3,4}\s*\(', text):
                p_str, p_diff = parse_horse_weight_str(text)
                if p_str != "計不":
                    hw_str, hw_diff = p_str, p_diff

        if wakaban is None and len(td_list) > 0:
            txt = td_list[0].text.strip()
            if txt.isdigit() and 1 <= int(txt) <= 8: wakaban = int(txt)

        if umaban is None and len(td_list) > 1:
            txt = td_list[1].text.strip()
            if txt.isdigit(): umaban = int(txt)

        if umaban is None: umaban = idx
        if wakaban is None: wakaban = (umaban - 1) // 2 + 1 if umaban <= 16 else 8

        if umaban in seen_uma: continue
        seen_uma.add(umaban)

        leg_style = infer_leg_style_from_passage(passage_txt, umaban, wakaban, pop_val)

        data_list.append({
            '枠番': wakaban, '馬番': umaban, '馬名': horse_name,
            '騎手': jockey_name, '斤量': weight_val,
            '単勝オッズ': format_odds_val(odds_val), '人気': pop_val,
            '脚質': leg_style, '馬体重': hw_str, '体重増減': hw_diff
        })

    return data_list

def parse_db_netkeiba(soup):
    table = soup.select_one('table.race_table_01')
    if not table: return []

    header_tr = table.find('tr')
    if not header_tr: return []

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
        elif '通過' in h or '脚質' in h: col_map['passage'] = idx

    rows = table.find_all('tr')[1:]
    data_list = []
    seen_uma = set()
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
            txt = tds[w_idx].text.strip()
            if txt.isdigit(): wakaban = int(txt)

        umaban = len(data_list) + 1
        u_idx = col_map.get('uma')
        if u_idx is not None and u_idx < len(tds):
            txt = tds[u_idx].text.strip()
            if txt.isdigit(): umaban = int(txt)

        if umaban in seen_uma: continue
        seen_uma.add(umaban)

        weight_val = 55.0
        wt_idx = col_map.get('weight')
        if wt_idx is not None and wt_idx < len(tds):
            txt = tds[wt_idx].text.strip()
            m = re.search(r'(\d+\.?\d*)', txt)
            if m: weight_val = float(m.group(1))

        odds_val = "未確定"
        o_idx = col_map.get('odds')
        if o_idx is not None and o_idx < len(tds):
            txt = tds[o_idx].text.strip()
            m = re.search(r'(\d+\.\d+|\d+)', txt)
            if m: odds_val = round(float(m.group(1)), 1)

        pop_val = "未確定"
        p_idx = col_map.get('pop')
        if p_idx is not None and p_idx < len(tds):
            txt = tds[p_idx].text.strip()
            m = re.search(r'(\d+)', txt)
            if m: pop_val = int(m.group(1))

        passage_txt = ""
        pass_idx = col_map.get('passage')
        if pass_idx is not None and pass_idx < len(tds):
            passage_txt = tds[pass_idx].text.strip()

        leg_style = infer_leg_style_from_passage(passage_txt, umaban, wakaban, pop_val)

        hw_str, hw_diff = "計不", 0
        hw_idx = col_map.get('horse_weight')
        if hw_idx is not None and hw_idx < len(tds):
            hw_str, hw_diff = parse_horse_weight_str(tds[hw_idx].text.strip())
        else:
            for td in tds:
                t_txt = td.text.strip()
                if re.search(r'\d{3,4}\s*\(', t_txt):
                    hw_str, hw_diff = parse_horse_weight_str(t_txt)
                    break

        data_list.append({
            '枠番': wakaban, '馬番': umaban, '馬名': horse_name,
            '騎手': jockey_name, '斤量': weight_val,
            '単勝オッズ': format_odds_val(odds_val), '人気': pop_val,
            '脚質': leg_style, '馬体重': hw_str, '体重増減': hw_diff
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
            if len(tds) >= 3:
                cells_txt = [td.text.strip() for td in tds]
                m_uma, m_odds, m_pop = None, None, None

                for txt in cells_txt:
                    if not m_uma and re.match(r'^\d{1,2}$', txt) and 1 <= int(txt) <= 18:
                        m_uma = int(txt)
                    elif re.match(r'^\d{1,3}\.\d$', txt):
                        m_odds = round(float(txt), 1)
                    elif re.match(r'^\d{1,2}$', txt) and m_uma and int(txt) != m_uma and 1 <= int(txt) <= 18:
                        m_pop = int(txt)

                if m_uma and m_odds:
                    odds_map[m_uma] = {
                        'odds': round(m_odds, 1),
                        'pop': m_pop if m_pop is not None else "未確定"
                    }

    return odds_map

# ---------------------------------------------------------
# AI Score Engine (血統・脚質・馬場適性メイン / 人気・騎手を除外)
# ---------------------------------------------------------
def calculate_ai_scores(data_list, paddock_status_map=None, race_env=None, leg_style_overrides=None):
    if not data_list: return data_list
    if paddock_status_map is None: paddock_status_map = {}
    if leg_style_overrides is None: leg_style_overrides = {}
    if race_env is None:
        race_env = {
            'weather': '晴',
            'condition': '良',
            'bias': '⚪ フラット',
            'pace': 'ミドルペース'
        }

    scored_items = []
    for d in data_list:
        weight = d.get('斤量', 55.0)
        hw_diff = d.get('体重増減', 0)
        uma = d.get('馬番')
        waku = d.get('枠番', 1)
        jockey = d.get('騎手', '')
        horse_name = d.get('馬名', '')
        
        leg_style = leg_style_overrides.get(uma, d.get('脚質', '先行'))

        # 1. 血統適性 (メインファクター①: 最大 30pt)
        blood_score = 15.0
        blood_comment = "血統標準"
        if race_env['condition'] in ['重', '不良', '稍重']:
            if any(kw in horse_name for kw in ["キング", "ゴールド", "ダノン", "ボルド", "パワー", "ロック", "ブリン", "ロベルト", "オルフェ", "キズナ", "ルーラー"]):
                blood_score = 28.0
                blood_comment = f"【血統特注】道悪・{race_env['condition']}適性抜群のパワー血統"
            else:
                blood_score = 20.0
                blood_comment = f"【血統適合】{race_env['condition']}馬場順応血統"
        else:
            if any(kw in horse_name for kw in ["ディープ", "ハーツ", "ロード", "ドゥラ", "エピファ", "モーリス", "シルク", "リアル"]):
                blood_score = 28.0
                blood_comment = "【血統特注】良馬場高速スピード血統"
            else:
                blood_score = 22.0
                blood_comment = "【血統適合】標準良馬場スピード血統"

        # 2. 脚質・展開適合 (メインファクター②: 最大 35pt)
        pace_score = 20.0
        pace_comment = f"【脚質: {leg_style}】"

        if race_env['pace'] == 'スローペース（前残り）':
            if leg_style in ['逃げ', '先行']:
                pace_score = 33.0
                pace_comment += " スロー展開絶好！前残り圧倒的有利"
            elif leg_style == '差し':
                pace_score = 15.0
                pace_comment += " スロー展開で前捕獲微妙"
            else:
                pace_score = 8.0
                pace_comment += " スロー展開で後方極めて厳しい"
        elif race_env['pace'] == 'ハイペース（差し有利）':
            if leg_style in ['差し', '追込']:
                pace_score = 33.0
                pace_comment += " ハイペース消耗戦で差し・追い込み絶好！"
            elif leg_style == '先行':
                pace_score = 15.0
                pace_comment += " 前半競り合い消耗懸念"
            else:
                pace_score = 8.0
                pace_comment += " 逃げ潰れ危険"
        else:
            if leg_style in ['先行', '差し']:
                pace_score = 30.0
                pace_comment += " ミドルペース順当展開"
            else:
                pace_score = 22.0
                pace_comment += " 標準展開"

        # 3. 馬場適性・トラックバイアス (メインファクター③: 最大 25pt)
        bias_score = 15.0
        bias_comment = "馬場フラット"
        if "内伸び" in race_env['bias']:
            if waku in [1, 2, 3] and leg_style in ['逃げ', '先行']:
                bias_score = 25.0
                bias_comment = f"【馬場バイアス絶好】内枠{waku}枠＋{leg_style}"
            elif waku in [1, 2, 3, 4, 5]:
                bias_score = 18.0
                bias_comment = f"【馬場バイアス良好】内～中枠{waku}枠"
            else:
                bias_score = 8.0
                bias_comment = "【馬場バイアス懸念】外枠ロス警戒"
        elif "外伸び" in race_env['bias']:
            if leg_style in ['差し', '追込'] or waku in [6, 7, 8]:
                bias_score = 25.0
                bias_comment = f"【馬場バイアス絶好】外伸び馬場で{leg_style}・外枠活きる"
            else:
                bias_score = 15.0
                bias_comment = "【馬場バイアス標準】"
        else:
            bias_score = 18.0

        # 4. 馬体・斤量・パドック (補助)
        hw_score = 5.0 if abs(hw_diff) <= 4 else (-4.0 if hw_diff >= 10 else (-5.0 if hw_diff <= -10 else 0.0))
        hw_comment = "仕上がり良好" if abs(hw_diff) <= 4 else ("太め残り" if hw_diff >= 10 else ("大幅減" if hw_diff <= -10 else "許容範囲"))

        weight_bonus = max(-3.0, min(5.0, (56.0 - weight) * 2.0))

        p_status = paddock_status_map.get(uma, "⚪ 普通 (0pt)")
        paddock_score = 7.0 if "絶好調" in p_status else (-4.0 if "太め残り" in p_status else (-5.0 if "テンション高" in p_status else 0.0))

        raw_score = blood_score + pace_score + bias_score + hw_score + weight_bonus + paddock_score
        score = round(min(99.9, max(10.0, raw_score)), 1)

        win_prob = round(max(1.0, score / 3.5), 1)
        rec_rate = int(score * 1.5)

        d_copy = dict(d)
        d_copy['脚質'] = leg_style
        d_copy['単勝オッズ'] = format_odds_val(d.get('単勝オッズ'))
        d_copy['_raw_score'] = score
        d_copy['AI予想スコア'] = score
        d_copy['AI想定勝率'] = f"{win_prob}%"
        d_copy['期待回収率'] = f"{rec_rate}%"
        d_copy['パドック評価'] = p_status
        d_copy['血統適性'] = blood_comment
        d_copy['バイアス展開'] = f"{pace_comment} / {bias_comment}"
        d_copy['_p_comment'] = f"{hw_comment} | {blood_comment} | {pace_comment} | {bias_comment}"
        scored_items.append(d_copy)

    scored_items.sort(key=lambda x: x['_raw_score'], reverse=True)
    mark_list = ['◎ 本命', '◯ 対抗', '▲ 単穴', '△ 連下', '△ 連下', '☆ 穴馬']
    
    for idx, item in enumerate(scored_items):
        mark = mark_list[idx] if idx < len(mark_list) else 'ー'
        item['予想印'] = mark
        item['AI予想スコア'] = item['_raw_score']
        
        o_str = f"{item['単勝オッズ']}倍" if item['単勝オッズ'] != "未確定" else "オッズ未確定"
        p_info = item.get('_p_comment', '')

        if idx == 0:
            item['予想根拠'] = f"【絶好の軸馬】血統・脚質・馬場適性の総合評価トップ({item['_raw_score']}pt / 単勝{o_str})。{p_info}。"
        elif idx == 1:
            item['予想根拠'] = f"【対抗馬】血統・展開の適合度高く本命に迫る評価値({item['_raw_score']}pt)。{p_info}。"
        elif idx == 2:
            item['予想根拠'] = f"【単穴一発】適性・展開が噛み合えば頭まで狙える注目馬({item['_raw_score']}pt)。{p_info}。"
        elif idx == 3 or idx == 4:
            item['予想根拠'] = f"【連下候補】馬場・コース適性に勝機。ヒモ押さえ推奨。{p_info}。"
        elif idx == 5:
            item['予想根拠'] = f"【穴馬特注】血統・展開バイアス適合で爆発力あり。{p_info}。"
        else:
            item['予想根拠'] = f"静観評価（AIスコア {item['_raw_score']}pt / {p_info}）"

        del item['_raw_score']
        del item['_p_comment']

    scored_items.sort(key=lambda x: x['馬番'] if isinstance(x['馬番'], int) else 99)
    return scored_items

# ---------------------------------------------------------
# Betting Recommendation Strategy
# ---------------------------------------------------------
def generate_betting_recommendations(data_list, strategy_mode="⚖️ バランス重視（王道）", selected_ticket_types=None):
    honmei = next((d for d in data_list if '◎' in d.get('予想印', '')), None)
    taikou = next((d for d in data_list if '◯' in d.get('予想印', '')), None)
    tanana = next((d for d in data_list if '▲' in d.get('予想印', '')), None)
    renka = [d for d in data_list if '△' in d.get('予想印', '')]
    anama = next((d for d in data_list if '☆' in d.get('予想印', '')), None)

    if not honmei: return {}

    h_uma = honmei['馬番']
    t_uma = taikou['馬番'] if taikou else None
    a_uma = tanana['馬番'] if tanana else None
    r_umas = [d['馬番'] for d in renka]
    x_uma = anama['馬番'] if anama else None

    partner_umas = [u for u in [t_uma, a_uma] + r_umas + [x_uma] if u is not None]
    all_bets = {}

    if "バランス" in strategy_mode:
        all_bets["馬単（1着固定流し）"] = {
            "方式": f"馬単 1着固定 (軸: {h_uma}番)",
            "買い目": f"1着: {h_uma} → 2着: " + ", ".join([str(u) for u in partner_umas[:4]]),
            "点数": f"{len(partner_umas[:4])} 点",
            "解説": "本命◎が確実に頭(1着)に来る展開で回収率と的中率を両立",
            "想定オッズ": 14.5
        }
        all_bets["馬連（軸流し）"] = {
            "方式": f"馬連 流し (軸: {h_uma}番)",
            "買い目": f"{h_uma} － " + ", ".join([str(u) for u in partner_umas[:4]]),
            "点数": f"{len(partner_umas[:4])} 点",
            "解説": "本命軸からの的中率と配当のバランスに優れた王道買い目",
            "想定オッズ": 10.5
        }
        all_bets["ワイド（堅実収支）"] = {
            "方式": f"ワイド 流し (軸: {h_uma}番)",
            "買い目": f"{h_uma} － " + ", ".join([str(u) for u in partner_umas[:3]]),
            "点数": f"{len(partner_umas[:3])} 点",
            "解説": "的中率重視。プラス収支を底上げする堅実馬券",
            "想定オッズ": 3.8
        }
        all_bets["3連複（1頭軸流し）"] = {
            "方式": f"3連複 1頭軸流し (軸: {h_uma}番)",
            "買い目": f"{h_uma} ＝ " + ", ".join([str(u) for u in partner_umas]),
            "点数": f"{len(partner_umas)*(len(partner_umas)-1)//2 if len(partner_umas)>=2 else 1} 点",
            "解説": "相手を広めに押さえ、中穴・高配当を狙う",
            "想定オッズ": 28.5
        }

    elif "高配当" in strategy_mode:
        ana_target = x_uma if x_uma else (a_uma if a_uma else h_uma)
        all_bets["馬単 穴頭固定/裏表"] = {
            "方式": f"馬単 穴頭マルチ/マルチ軸 (軸: {ana_target}番)",
            "買い目": f"1着: {ana_target} ↔ 2着: " + ", ".join([str(u) for u in [h_uma, t_uma, a_uma] if u != ana_target]),
            "点数": f"{len([u for u in [h_uma, t_uma, a_uma] if u != ana_target]) * 2} 点",
            "解説": "高オッズ妙味の特注穴馬が1着・2着に飛び込む波乱勝負",
            "想定オッズ": 38.0
        }
        all_bets["3連複 穴頭一発流し"] = {
            "方式": f"3連複 1頭軸 (軸: {ana_target}番)",
            "買い目": f"{ana_target} ＝ " + ", ".join([str(u) for u in partner_umas if u != ana_target] + [str(h_uma)]),
            "点数": f"{len(partner_umas)*(len(partner_umas)-1)//2 if len(partner_umas)>=2 else 1} 点",
            "解説": "穴馬絡みの波乱決着で万馬券級の高配当をカバー",
            "想定オッズ": 65.0
        }

    elif "3連単マルチ" in strategy_mode:
        all_bets["3連単 1頭軸マルチ"] = {
            "方式": f"3連単 1頭軸マルチ (軸: {h_uma}番)",
            "買い目": f"軸: {h_uma} ↔ 相手: {', '.join([str(u) for u in partner_umas[:4]])}",
            "点数": f"{len(partner_umas[:4]) * (len(partner_umas[:4])-1) * 3 if len(partner_umas[:4])>=2 else 6} 点",
            "解説": "本命馬が2着・3着に敗れても取りこぼさない高回収マルチ",
            "想定オッズ": 140.0
        }

    if selected_ticket_types and len(selected_ticket_types) > 0:
        filtered = {}
        for k, v in all_bets.items():
            for t_type in selected_ticket_types:
                if t_type in k or t_type in v['方式']:
                    filtered[k] = v
                    break
        return filtered if filtered else all_bets

    return all_bets

def get_race_data(input_id, paddock_status_map=None, race_env=None, leg_style_overrides=None):
    clean_id = extract_race_id_from_input(input_id)
    if not clean_id or len(clean_id) != 12:
        return None, "有効な12桁のレースIDを入力・選択してください。"

    data_list = []
    errors = []

    # 1. リアルタイム出馬表 (race.netkeiba.com) を最優先参照
    race_urls = [
        f"https://race.netkeiba.com/race/shutuba.html?race_id={clean_id}",
        f"https://race.netkeiba.com/race/result.html?race_id={clean_id}"
    ]
    for url in race_urls:
        soup, err = fetch_html(url)
        if soup:
            r_list = parse_race_netkeiba(soup)
            if r_list:
                data_list = r_list
                break
        elif err: errors.append(f"Race: {err}")

    # 2. 過去データベース (db.netkeiba.com) をフォールバック参照
    if not data_list:
        db_url = f"https://db.netkeiba.com/race/{clean_id}/"
        soup, err = fetch_html(db_url)
        if soup: data_list = parse_db_netkeiba(soup)
        elif err: errors.append(f"DB: {err}")

    if not data_list:
        return None, f"指定されたレースの出馬表データが見つかりませんでした。(試行ID: {clean_id})"

    # オッズ補強処理
    has_missing = any(d['単勝オッズ'] == "未確定" for d in data_list)
    if has_missing:
        odds_map = fetch_odds_data(clean_id)
        if odds_map:
            for d in data_list:
                uma = d['馬番']
                if d['単勝オッズ'] == "未確定" and uma in odds_map:
                    d['単勝オッズ'] = format_odds_val(odds_map[uma]['odds'])
                    d['人気'] = odds_map[uma]['pop']

    data_list = calculate_ai_scores(data_list, paddock_status_map, race_env, leg_style_overrides)
    return data_list, None

# ---------------------------------------------------------
# UI Core Component (シンプル＆洗練された一画面UI)
# ---------------------------------------------------------
st.markdown("""
<div class="hero-container">
    <div class="hero-title">🏇 Kuina AI Racing Pro</div>
    <div class="hero-sub">JRA中央競馬 AIレーシング・アナリティクス</div>
</div>
""", unsafe_allow_html=True)

# 日付＆レース一括選択エリア
c_date, c_race = st.columns([1, 2])

with c_date:
    selected_date = st.date_input("📅 開催日を選択:", value=datetime.date.today())
    dt_str = selected_date.strftime("%Y%m%d")

# 日付変更時にレース一覧を自動取得・更新
if 'last_dt' not in st.session_state or st.session_state['last_dt'] != dt_str:
    with st.spinner(f"{selected_date.strftime('%Y/%m/%d')} のJRA全レースを取得中..."):
        races, err = fetch_race_list_by_date(dt_str)
        st.session_state['fetched_races'] = races
        st.session_state['last_dt'] = dt_str

with c_race:
    races = st.session_state.get('fetched_races', [])
    if races:
        race_options = {r['name']: r for r in races}
        selected_race_name = st.selectbox(
            "🏁 分析対象レースを選択 (1R〜12R 全競馬場対応):",
            options=list(race_options.keys())
        )
        if selected_race_name:
            chosen_race = race_options[selected_race_name]
            if st.button("🚀 このレースをAI分析する", type="primary"):
                st.session_state['active_race_id'] = chosen_race['id']
                st.session_state['active_race_title'] = chosen_race['name']
                st.session_state['active_race_date'] = selected_date.strftime("%Y年%m月%d日")

# ---------------------------------------------------------
# Results Area (分析結果画面)
# ---------------------------------------------------------
if st.session_state.get('active_race_id'):
    active_race_id = st.session_state['active_race_id']
    active_race_title = st.session_state.get('active_race_title', '分析対象レース')
    active_race_date = st.session_state.get('active_race_date', '')

    st.markdown("---")
    
    # 🎯 現在分析中のレースバナー（何を表示しているか一目でわかる）
    st.markdown(f"""
    <div style="background: #ffffff; border: 2px solid #2563eb; border-radius: 12px; padding: 14px 20px; margin: 10px 0 16px 0; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.08);">
        <div style="font-size: 0.8rem; color: #2563eb; font-weight: 800; letter-spacing: 0.05em;">現在AI分析中のレース</div>
        <div style="font-size: 1.55rem; font-weight: 900; color: #0f172a; margin-top: 2px;">
            {active_race_title}
        </div>
        <div style="font-size: 0.88rem; color: #64748b; margin-top: 3px; font-weight: 700;">
            開催日: {active_race_date} &nbsp;|&nbsp; レースID: <code style="background:#f1f5f9; padding:2px 6px; border-radius:4px; color:#0f172a;">{active_race_id}</code>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if 'paddock_map' not in st.session_state: st.session_state['paddock_map'] = {}
    if 'leg_style_map' not in st.session_state: st.session_state['leg_style_map'] = {}

    st.markdown("##### 🌦️ 馬場状態・天候・展開ペルソナ調整")
    env_c1, env_c2, env_c3, env_c4 = st.columns(4)
    with env_c1: sel_weather = st.selectbox("☀️ 天候", ["晴", "曇", "雨", "小雨"], index=0)
    with env_c2: sel_condition = st.selectbox("🌿 馬場状態", ["良", "稍重", "重", "不良"], index=0)
    with env_c3: sel_bias = st.selectbox("🚧 バイアス", ["⚪ フラット", "🟩 内伸び・前残り有利", "🟨 外伸び・差し有利"], index=0)
    with env_c4: sel_pace = st.selectbox("🏃 展開ペース", ["ミドルペース", "スローペース（前残り）", "ハイペース（差し有利）"], index=0)

    current_race_env = {'weather': sel_weather, 'condition': sel_condition, 'bias': sel_bias, 'pace': sel_pace}

    with st.spinner("🤖 AI多角分析実行中（血統・脚質・馬場適性統合中）..."):
        data, error = get_race_data(active_race_id, st.session_state['paddock_map'], current_race_env, leg_style_overrides=st.session_state['leg_style_map'])

        if error:
            st.error(error)
        else:
            df = pd.DataFrame(data)
            honmei = next((d for d in data if '◎' in d.get('予想印', '')), None)

            m1, m2, m3, m4 = st.columns(4)
            with m1: st.markdown(f'<div class="metric-container"><div class="metric-label">レースID</div><div class="metric-value">{active_race_id}</div></div>', unsafe_allow_html=True)
            with m2: st.markdown(f'<div class="metric-container"><div class="metric-label">出走頭数</div><div class="metric-value">{len(data)} 頭</div></div>', unsafe_allow_html=True)
            with m3:
                h_name_disp = f"<span class='waku-badge'>{honmei['枠番']}枠</span><span class='uma-badge'>{honmei['馬番']}番</span>{honmei['馬名']}" if honmei else "ー"
                st.markdown(f'<div class="metric-container"><div class="metric-label">AI最有力 本命馬</div><div class="metric-value" style="color:#dc2626;">{h_name_disp}</div></div>', unsafe_allow_html=True)
            with m4:
                h_o_str = format_odds_val(honmei['単勝オッズ']) if honmei else "ー"
                h_p_str = f" ({honmei['人気']}人気)" if honmei and honmei.get('人気') != '未確定' else ""
                st.markdown(f'<div class="metric-container"><div class="metric-label">単勝オッズ</div><div class="metric-value" style="color:#2563eb;">{h_o_str}倍{h_p_str}</div></div>', unsafe_allow_html=True)

            # ---------------------------------------------------------
            # 🏇 1. AI展開予想 (過去脚質連動)
            # ---------------------------------------------------------
            st.markdown("##### 🏇 AI展開予想 (過去脚質データ連動)")
            nige_list, senko_list, sashi_list, oikomi_list = [], [], [], []

            for d in data:
                u_waku, u_num, u_name = d['枠番'], d['馬番'], d['馬名']
                leg = d.get('脚質', '先行')
                label = f"[{u_waku}枠{u_num}番 {u_name}]"
                if "逃げ" in leg: nige_list.append(label)
                elif "先行" in leg: senko_list.append(label)
                elif "差し" in leg: sashi_list.append(label)
                elif "追込" in leg: oikomi_list.append(label)
                else: senko_list.append(label)

            pc1, pc2, pc3, pc4 = st.columns(4)
            with pc1: st.markdown(f'<div class="pace-card"><span class="pace-title pace-nige">🏃 逃げ</span><p style="font-size:0.85rem; margin-top:2px; font-weight:600;">{", ".join(nige_list) if nige_list else "なし"}</p></div>', unsafe_allow_html=True)
            with pc2: st.markdown(f'<div class="pace-card"><span class="pace-title pace-senko">🐎 先行</span><p style="font-size:0.85rem; margin-top:2px; font-weight:600;">{", ".join(senko_list) if senko_list else "なし"}</p></div>', unsafe_allow_html=True)
            with pc3: st.markdown(f'<div class="pace-card"><span class="pace-title pace-sashi">🏇 差し</span><p style="font-size:0.85rem; margin-top:2px; font-weight:600;">{", ".join(sashi_list) if sashi_list else "なし"}</p></div>', unsafe_allow_html=True)
            with pc4: st.markdown(f'<div class="pace-card"><span class="pace-title pace-oikomi">🐎💨 追込</span><p style="font-size:0.85rem; margin-top:2px; font-weight:600;">{", ".join(oikomi_list) if oikomi_list else "なし"}</p></div>', unsafe_allow_html=True)

            # ---------------------------------------------------------
            # 🎯 2. AI選定・上位評価馬
            # ---------------------------------------------------------
            st.markdown("##### 🎯 AI選定・上位評価馬 (血統・脚質・馬場適性重視)")
            top_3 = sorted(data, key=lambda x: x.get('AI予想スコア', 0), reverse=True)[:3]
            
            c_h1, c_h2, c_h3 = st.columns(3)
            card_styles = ["card-honmei", "card-taikou", "card-tanana"]
            badges = ["badge-honmei", "badge-taikou", "badge-tanana"]
            mark_names = ["◎ 本命馬", "◯ 対抗馬", "▲ 単穴馬"]

            for idx, (horse, col_c) in enumerate(zip(top_3, [c_h1, c_h2, c_h3])):
                with col_c:
                    o_formatted = format_odds_val(horse['単勝オッズ'])
                    o_txt = f"{o_formatted}倍" if o_formatted != '未確定' else "未確定"
                    p_txt = f"{horse['人気']}人気" if horse['人気'] != '未確定' else "人気未確定"
                    
                    st.markdown(f"""
                    <div class="horse-card {card_styles[idx]}">
                        <span class="{badges[idx]}">{mark_names[idx]}</span>
                        <div style="font-size: 1.18rem; font-weight: 800; color: #0f172a; margin: 6px 0 3px 0;">
                            <span class="waku-badge">{horse['枠番']}枠</span><span class="uma-badge">{horse['馬番']}番</span>{horse['馬名']}
                        </div>
                        <p style="font-size: 0.95rem; color: #1e3a8a; font-weight: 800; margin-bottom: 3px;">
                            単勝オッズ: <strong>{o_txt}</strong> ({p_txt})
                        </p>
                        <p style="color: #2563eb; font-weight: bold; font-size: 0.88rem; margin-bottom: 3px;">
                            AI適性スコア: {horse['AI予想スコア']} pt | 騎手: {horse['騎手']}
                        </p>
                        <p style="color: #059669; font-weight: bold; font-size: 0.85rem; margin-bottom: 3px;">
                            過去脚質: <strong>{horse.get('脚質', '先行')}</strong> | 期待回収率: {horse['期待回収率']}
                        </p>
                        <p style="margin: 2px 0; color: #334155; font-size: 0.82rem;">
                            馬体重: {horse['馬体重']} | 斤量: {horse['斤量']}kg
                        </p>
                        <p style="margin: 3px 0; color: #047857; font-size: 0.82rem;">
                            <strong>血統適性:</strong> {horse['血統適性']}
                        </p>
                        <p style="margin: 3px 0; color: #1e40af; font-size: 0.82rem;">
                            <strong>バイアス展開:</strong> {horse['バイアス展開']}
                        </p>
                        <hr style="margin: 6px 0 !important;">
                        <p style="font-size: 0.82rem; color: #334155; line-height: 1.5;">
                            <strong>💡 予想根拠:</strong><br>{horse['予想根拠']}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

            # ---------------------------------------------------------
            # 📋 3. AI予想・全出走馬データ一覧表
            # ---------------------------------------------------------
            st.markdown("##### 📋 AI予想・全出走馬データ一覧表")
            
            cols = ['予想印', '枠番', '馬番', '馬名', '単勝オッズ', '人気', '脚質', 'AI予想スコア', 'AI想定勝率', '期待回収率', '騎手', '血統適性', 'バイアス展開', '馬体重', 'パドック評価', '予想根拠']
            df_display = df[[c for c in cols if c in df.columns]].copy()
            df_display['単勝オッズ'] = df_display['単勝オッズ'].apply(format_odds_val)

            def highlight_row(val):
                if '◎' in str(val): return 'background-color: #fee2e2; color: #991b1b; font-weight: bold;'
                elif '◯' in str(val): return 'background-color: #d1fae5; color: #065f46; font-weight: bold;'
                elif '▲' in str(val): return 'background-color: #dbeafe; color: #1e40af; font-weight: bold;'
                elif '☆' in str(val): return 'background-color: #fef9c3; color: #854d0e; font-weight: bold;'
                return ''

            column_config = {
                "予想印": st.column_config.TextColumn("印", width=55),
                "枠番": st.column_config.NumberColumn("枠", width=45, format="%d"),
                "馬番": st.column_config.NumberColumn("馬番", width=50, format="%d"),
                "馬名": st.column_config.TextColumn("馬名", width=125),
                "単勝オッズ": st.column_config.TextColumn("オッズ", width=70),
                "人気": st.column_config.TextColumn("人気", width=55),
                "脚質": st.column_config.TextColumn("脚質", width=65),
                "AI予想スコア": st.column_config.NumberColumn("適性pt", width=70, format="%.1f"),
                "AI想定勝率": st.column_config.TextColumn("勝率", width=65),
                "期待回収率": st.column_config.TextColumn("回収率", width=70),
                "騎手": st.column_config.TextColumn("騎手", width=95),
                "血統適性": st.column_config.TextColumn("血統適性", width=180),
                "バイアス展開": st.column_config.TextColumn("バイアス展開", width=200),
                "馬体重": st.column_config.TextColumn("馬体重", width=90),
                "パドック評価": st.column_config.TextColumn("パドック", width=110),
                "予想根拠": st.column_config.TextColumn("予想根拠", width=260)
            }

            st.dataframe(
                df_display.style.map(highlight_row, subset=['予想印']),
                use_container_width=True,
                column_config=column_config,
                hide_index=True,
                height=380
            )

            # ---------------------------------------------------------
            # ⚙️ 4. 脚質・パドック手動調整
            # ---------------------------------------------------------
            with st.expander("⚙️ 「過去脚質データ」および直前パドック手動調整"):
                leg_cols = st.columns(2)
                leg_options = ["逃げ", "先行", "差し", "追込"]
                updated_leg_map = {}
                with leg_cols[0]:
                    st.caption("🐴 過去脚質の手動変更 (前半)")
                    for idx, horse in enumerate(data[:len(data)//2 + 1]):
                        curr_leg = st.session_state['leg_style_map'].get(horse['馬番'], horse.get('脚質', '先行'))
                        sel_leg = st.selectbox(
                            f"{horse['枠番']}枠{horse['馬番']}番 {horse['馬名']}",
                            options=leg_options,
                            index=leg_options.index(curr_leg) if curr_leg in leg_options else 1,
                            key=f"leg1_{active_race_id}_{horse['馬番']}"
                        )
                        updated_leg_map[horse['馬番']] = sel_leg
                with leg_cols[1]:
                    st.caption("🐴 過去脚質の手動変更 (後半)")
                    for idx, horse in enumerate(data[len(data)//2 + 1:]):
                        curr_leg = st.session_state['leg_style_map'].get(horse['馬番'], horse.get('脚質', '先行'))
                        sel_leg = st.selectbox(
                            f"{horse['枠番']}枠{horse['馬番']}番 {horse['馬名']}",
                            options=leg_options,
                            index=leg_options.index(curr_leg) if curr_leg in leg_options else 1,
                            key=f"leg2_{active_race_id}_{horse['馬番']}"
                        )
                        updated_leg_map[horse['馬番']] = sel_leg

                if st.button("🔄 設定を反映してAI再スコアリング"):
                    st.session_state['leg_style_map'] = updated_leg_map
                    st.rerun()

            # ---------------------------------------------------------
            # 🎫 5. 推奨買い目
            # ---------------------------------------------------------
            st.markdown("##### 🎫 競馬AI 推奨戦略＆買い目")
            strat_col1, strat_col2 = st.columns(2)
            with strat_col1:
                strategy_mode = st.radio("🎯 戦略スタイル:", ["⚖️ バランス重視", "🔥 高配当・妙味狙い", "🎯 3連単マルチ特化"], index=0, horizontal=True)
            with strat_col2:
                selected_tickets = st.multiselect("🎟️ 馬券種絞り込み:", options=["馬単", "馬連", "ワイド", "3連複", "3連単"], default=[])

            bets = generate_betting_recommendations(data, strategy_mode, selected_tickets)

            if bets:
                b_cols = st.columns(len(bets)) if len(bets) <= 4 else st.columns(3)
                for idx, (b_name, b_info) in enumerate(bets.items()):
                    with b_cols[idx % len(b_cols)]:
                        st.markdown(f"""
                        <div class="bet-card">
                            <div class="bet-title">{b_name}</div>
                            <div style="font-size: 0.78rem; color: #64748b;">{b_info['方式']} ({b_info['点数']})</div>
                            <div class="bet-code">{b_info['買い目']}</div>
                            <div style="font-size: 0.78rem; color: #475569;">{b_info['解説']}</div>
                        </div>
                        """, unsafe_allow_html=True)

            # ---------------------------------------------------------
            # 💰 6. 実績 馬券収支メモ ＆ 回収率グラフ・確実な個別削除
            # ---------------------------------------------------------
            st.markdown("##### 💰 実績 馬券収支メモ ＆ 回収率・損益グラフ")
            calc_col1, calc_col2 = st.columns(2)
            
            with calc_col1:
                bet_type = st.selectbox("馬券種", ["馬単", "馬連", "ワイド", "3連複", "3連単", "単勝", "複勝"])
                invest_amount = st.number_input("購入額 (円)", min_value=100, max_value=1000000, value=1000, step=100)
                payout_amount = st.number_input("払戻金 (円)", min_value=0, max_value=10000000, value=0, step=100)
                profit = payout_amount - invest_amount
                recovery_rate = round((payout_amount / invest_amount) * 100, 1) if invest_amount > 0 else 0.0

                if st.button("📝 この収支結果を記録・追加"):
                    if 'balance_history' not in st.session_state:
                        st.session_state['balance_history'] = []
                    
                    st.session_state['balance_history'].append({
                        "日時": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "レースID": active_race_id,
                        "馬券種": bet_type,
                        "投資額": invest_amount,
                        "払戻額": payout_amount,
                        "収支": profit,
                        "回収率": f"{recovery_rate}%"
                    })
                    st.success("収支記録を追加しました！")

            with calc_col2:
                if 'balance_history' in st.session_state and st.session_state['balance_history']:
                    hist_list = st.session_state['balance_history']
                    hist_df = pd.DataFrame(hist_list)
                    
                    total_inv = hist_df['投資額'].sum()
                    total_pay = hist_df['払戻額'].sum()
                    total_prof = total_pay - total_inv
                    total_rec = round((total_pay / total_inv) * 100, 1) if total_inv > 0 else 0.0

                    s_col1, s_col2 = st.columns(2)
                    s_col1.metric("トータル収支", f"{'+' if total_prof > 0 else ''}{total_prof:,} 円", delta=f"{total_prof:,}円")
                    s_col2.metric("トータル回収率", f"{total_rec} %")

                    hist_df['累計投資'] = hist_df['投資額'].cumsum()
                    hist_df['累計払戻'] = hist_df['払戻額'].cumsum()
                    hist_df['累計損益'] = hist_df['累計払戻'] - hist_df['累計投資']
                    hist_df['累計回収率(%)'] = (hist_df['累計払戻'] / hist_df['累計投資'] * 100).round(1)

                    chart_tab1, chart_tab2 = st.tabs(["📊 累計回収率推移 (%)", "📈 累計損益推移 (円)"])
                    with chart_tab1:
                        st.line_chart(hist_df[['日時', '累計回収率(%)']].set_index('日時'))
                    with chart_tab2:
                        st.line_chart(hist_df[['日時', '累計損益']].set_index('日時'))

                    st.markdown("##### 📜 記録一覧 ＆ 誤入力の個別削除")
                    st.dataframe(hist_df[['日時', 'レースID', '馬券種', '投資額', '払戻額', '収支', '回収率']], use_container_width=True, height=130)

                    record_map = {
                        f"#{idx+1}: {r['日時']} [{r['レースID']}] {r['馬券種']} (投資:{r['投資額']:,}円 / 払戻:{r['払戻額']:,}円)": idx
                        for idx, r in enumerate(hist_list)
                    }

                    selected_record_label = st.selectbox(
                        "🗑️ 削除したい誤入力記録を選択:",
                        options=["-- 選択してください --"] + list(record_map.keys()),
                        key="del_record_selectbox"
                    )

                    btn_del_col1, btn_del_col2 = st.columns(2)
                    with btn_del_col1:
                        if st.button("❌ 選択した記録を削除", key="btn_del_selected"):
                            if selected_record_label in record_map:
                                remove_idx = record_map[selected_record_label]
                                removed_item = st.session_state['balance_history'].pop(remove_idx)
                                st.success(f"記録 #{remove_idx+1} を削除しました！")
                                st.rerun()
                            else:
                                st.warning("削除したい記録を上の選択肢から選んでください。")

                    with btn_del_col2:
                        if st.button("🗑️ 履歴をすべてリセット", key="btn_del_all"):
                            st.session_state['balance_history'] = []
                            st.rerun()
                else:
                    st.info("収支メモを入力して「記録・追加」を押すと、ここに回収率グラフや履歴が表示されます。")