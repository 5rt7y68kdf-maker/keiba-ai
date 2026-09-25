import re
import requests
from bs4 import BeautifulSoup
import urllib3
import streamlit as st
import datetime
import pandas as pd

# SSL証明書警告の非表示化
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 日本標準時 (JST) 定義
JST = datetime.timezone(datetime.timedelta(hours=9))

# 全国10競馬場のコードマップ
JRA_VENUES = {
    "札幌": "01", "函館": "02", "福島": "03", "新潟": "04",
    "東京": "05", "中山": "06", "中京": "07", "京都": "08",
    "阪神": "09", "小倉": "10"
}

VENUE_MAP = JRA_VENUES
VENUE_CODE_TO_NAME = {v: k for k, v in JRA_VENUES.items()}

# ---------------------------------------------------------
# Streamlit Page Config & High-Contrast Light Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="Kuina AI Racing Pro",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Clean, high-contrast light theme
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    
    .stApp {
        background-color: #f8fafc;
        color: #0f172a;
        font-family: 'Inter', 'Helvetica Neue', Arial, 'Hiragino Sans', sans-serif;
    }
    
    
    .hero-container {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
        border-radius: 12px;
        padding: 16px 22px;
        color: #ffffff;
        margin-top: 10px;
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


    /* Horse Card Styling with Full Text Visibility */
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
    .horse-card:hover {
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
        border-color: #cbd5e1;
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
    div[data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow-x: auto;
        border: 1px solid #cbd5e1;
        background: #ffffff;
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

# ---------------------------------------------------------
# Web Scraping & Data Fetching
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

def fetch_race_list_by_date(dt_str):
    clean_date = re.sub(r'\D', '', str(dt_str))
    if len(clean_date) != 8:
        return [], "日付は8桁の数字(YYYYMMDD)で指定してください。"

    races_dict = {}

    # 1. race.netkeiba.com を最優先参照 (当日・翌日・開催予定)
    urls = [
        f"https://race.netkeiba.com/top/race_list.html?kaijo_date={clean_date}",
        f"https://race.netkeiba.com/top/?kaijo_date={clean_date}"
    ]

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

            venue_name = VENUE_CODE_TO_NAME[v_code]
            r_num = int(r_id[10:12])

            raw_text = a.text.strip().replace('\n', ' ')
            raw_text = re.sub(r'\s+', ' ', raw_text)
            clean_name = re.sub(r'^(📍|【.*?】|\d+R)\s*', '', raw_text).strip()
            clean_name = re.sub(r'(出馬表|オッズ|結果|映像|払戻|掲示板|データ)', '', clean_name).strip()

            display_title = f"📍【{venue_name}】 {r_num}R {clean_name}" if clean_name and len(clean_name) >= 2 and not clean_name.isdigit() else f"📍【{venue_name}】 {r_num}R"

            if r_id not in races_dict or len(display_title) > len(races_dict[r_id]['name']):
                races_dict[r_id] = {'id': r_id, 'name': display_title, 'venue': venue_name, 'r_num': r_num}

    # 2. 過去データベース (db.netkeiba.com) の探索
    if not races_dict:
        db_url = f"https://db.netkeiba.com/race/list/{clean_date}/"
        soup, _ = fetch_html(db_url)
        if soup:
            main_area = soup.select_one('div.db_main_race_list') or soup.select_one('div#main') or soup
            for a in main_area.find_all('a'):
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
                    clean_name = re.sub(r'(出馬表|オッズ|結果|映像|払戻|掲示板|データ)', '', clean_name).strip()

                    display_title = f"📍【{venue_name}】 {r_num}R {clean_name}" if clean_name and len(clean_name) >= 2 and not clean_name.isdigit() else f"📍【{venue_name}】 {r_num}R"

                    if r_id not in races_dict or len(display_title) > len(races_dict[r_id]['name']):
                        races_dict[r_id] = {'id': r_id, 'name': display_title, 'venue': venue_name, 'r_num': r_num}

    if not races_dict:
        return [], f"指定された日付 ({clean_date}) の中央競馬(JRA)レースデータは見つかりませんでした。"

    races = list(races_dict.values())
    races.sort(key=lambda x: x['id'])
    return races, None

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
            txt = tds[w_idx].text.strip()
            if txt.isdigit(): wakaban = int(txt)

        umaban = len(data_list) + 1
        u_idx = col_map.get('uma')
        if u_idx is not None and u_idx < len(tds):
            txt = tds[u_idx].text.strip()
            if txt.isdigit(): umaban = int(txt)

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
            if m: odds_val = float(m.group(1))

        pop_val = "未確定"
        p_idx = col_map.get('pop')
        if p_idx is not None and p_idx < len(tds):
            txt = tds[p_idx].text.strip()
            m = re.search(r'(\d+)', txt)
            if m: pop_val = int(m.group(1))

        hw_str = "計不"
        hw_diff = 0
        hw_idx = col_map.get('horse_weight')
        if hw_idx is not None and hw_idx < len(tds):
            txt = tds[hw_idx].text.strip()
            hw_str, hw_diff = parse_horse_weight_str(txt)
        else:
            for td in tds:
                t_txt = td.text.strip()
                if re.search(r'\d{3,4}\s*\(', t_txt):
                    hw_str, hw_diff = parse_horse_weight_str(t_txt)
                    break

        data_list.append({
            '枠番': wakaban, '馬番': umaban, '馬名': horse_name,
            '騎手': jockey_name,
            '斤量': weight_val, '単勝オッズ': odds_val, '人気': pop_val,
            '馬体重': hw_str, '体重増減': hw_diff
        })

    return data_list

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
                uma_txt = tds[0].text.strip() if len(tds) > 0 else ''
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
# AI Score Engine
# ---------------------------------------------------------
def calculate_ai_scores(data_list, paddock_status_map=None, race_env=None):
    if not data_list: return data_list
    if paddock_status_map is None: paddock_status_map = {}
    if race_env is None:
        race_env = {
            'weather': '晴',
            'condition': '良',
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

        pop_score = max(0, 40 - (p_val - 1) * 3.5)
        odds_score = max(0, 30 - (o_val * 0.6))
        weight_bonus = max(0, (56.0 - weight) * 2)

        j_score = 0.0
        j_comment = "騎手標準"
        if any(tj in jockey for tj in TOP_JOCKEYS_S):
            j_score = 7.0
            j_comment = f"【トップ騎手】{jockey} (勝率・連対率特筆)"
        elif any(tj in jockey for tj in TOP_JOCKEYS_A):
            j_score = 4.0
            j_comment = f"【有力騎手】{jockey} (安定感高)"
        else:
            j_score = 1.0
            j_comment = f"【鞍上】{jockey}"

        blood_score = 3.0
        blood_comment = "血統適性標準"
        if race_env['condition'] in ['重', '不良', '稍重']:
            if any(kw in horse_name for kw in ["キング", "ゴールド", "ダノン", "ボルド", "パワー", "ロック", "ブリン", "ロベルト"]):
                blood_score = 6.0
                blood_comment = f"【血統高適性】パワー型血統 (道悪・{race_env['condition']}馬場順応)"
            else:
                blood_score = 4.0
                blood_comment = f"【血統適性】{race_env['condition']}馬場適性あり"
        else:
            blood_score = 5.0
            blood_comment = "【血統高適性】良馬場スピード血統"

        weather_score = 0.0
        if race_env['weather'] == '雨' or race_env['condition'] in ['重', '不良']:
            if hw_diff >= 4:
                weather_score = 3.0
            elif hw_diff <= -6:
                weather_score = -3.0
        else:
            weather_score = 2.0

        bias_score = 0.0
        bias_comment = "馬場フラット"
        if "内伸び・前残り" in race_env['bias']:
            if waku in [1, 2, 3]:
                bias_score = 6.0
                bias_comment = f"【バイアス好走】内枠{waku}枠有利・前目追走可"
            elif waku in [4, 5]:
                bias_score = 3.0
            else:
                bias_score = -2.0
                bias_comment = "【バイアス懸念】外枠位置取り懸念"
        elif "外伸び・差し" in race_env['bias']:
            if waku in [6, 7, 8]:
                bias_score = 6.0
                bias_comment = f"【バイアス好走】外枠{waku}枠・伸び脚活きる展開"
            else:
                bias_score = 1.0
        else:
            bias_score = 2.0

        pattern_score = 4.0
        pattern_comment = "好走パターン適合"
        if race_env['pace'] == 'ハイペース（差し有利）':
            if p_val >= 4 and o_val >= 10.0:
                pattern_score = 6.0
                pattern_comment = "【好走パターン】ハイペース消耗戦での差し一発"
        elif race_env['pace'] == 'スローペース（前残り）':
            if waku <= 4:
                pattern_score = 6.0
                pattern_comment = "【好走パターン】スローマイペース逃げ粘りパターン"

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
            p_comment = "【パドック絶好調】気配最高"
        elif "⚠️ 太め残り" in p_status:
            paddock_score = -4.0
            p_comment = "【パドック懸念】重苦しさ"
        elif "💥 テンション高" in p_status:
            paddock_score = -5.0
            p_comment = "【パドック不安】チャカつき"
        else:
            paddock_score = 0.0
            p_comment = "パドック順調"

        raw_score = pop_score + odds_score + weight_bonus + j_score + blood_score + weather_score + bias_score + pattern_score + weight_diff_score + paddock_score + 5
        score = round(min(99.9, max(10.0, raw_score)), 1)

        d_copy = dict(d)
        d_copy['_raw_score'] = score
        d_copy['パドック評価'] = p_status
        d_copy['騎手評価'] = j_comment
        d_copy['血統適性'] = blood_comment
        d_copy['バイアス展開'] = f"{bias_comment} / {pattern_comment}"
        d_copy['_p_comment'] = f"{hw_comment} | {j_comment} | {blood_comment} | {bias_comment}"
        scored_items.append(d_copy)

    scored_items.sort(key=lambda x: x['_raw_score'], reverse=True)
    mark_list = ['◎ 本命', '◯ 対抗', '▲ 単穴', '△ 連下', '△ 連下', '☆ 穴馬']
    
    for idx, item in enumerate(scored_items):
        mark = mark_list[idx] if idx < len(mark_list) else 'ー'
        item['予想印'] = mark
        item['AI予想スコア'] = item['_raw_score']
        
        o_str = f"{item['単勝オッズ']}倍" if item['単勝オッズ'] != "未確定" else "オッズ未確定"
        p_str = f"{item['人気']}人気" if item['人気'] != "未確定" else ""
        p_info = item.get('_p_comment', '')

        if idx == 0:
            item['予想根拠'] = f"【絶好の軸馬】単勝{o_str}（{p_str}）。AI総合指数最高値({item['_raw_score']}pt)。{p_info}。軸信頼度最高ランク。"
        elif idx == 1:
            item['予想根拠'] = f"【対抗馬】単勝{o_str}（{p_str}）。{p_info}。本命馬に迫るハイレベル評価値。"
        elif idx == 2:
            item['予想根拠'] = f"【単穴一発】単勝{o_str}（{p_str}）。{p_info}。展開次第で頭まで突き抜ける爆発力。"
        elif idx == 3 or idx == 4:
            item['予想根拠'] = f"【連下候補】単勝{o_str}。{p_info}。ヒモ枠として押さえ必須。"
        elif idx == 5:
            item['予想根拠'] = f"【穴馬特注】単勝{o_str}（{p_str}）。{p_info}。高配当をもたらすキーマン。"
        else:
            item['予想根拠'] = f"静観評価（スコア {item['_raw_score']}pt / {p_info}）"

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
            "解説": "本命◎が確実に頭(1着)に来る展開で、高い回収率と的中率を両立",
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
            "解説": "的中率重視。プラス収支を確実に底上げする堅実馬券",
            "想定オッズ": 3.8
        }
        all_bets["3連複（1頭軸流し）"] = {
            "方式": f"3連複 1頭軸流し (軸: {h_uma}番)",
            "買い目": f"{h_uma} ＝ " + ", ".join([str(u) for u in partner_umas]),
            "点数": f"{len(partner_umas)*(len(partner_umas)-1)//2 if len(partner_umas)>=2 else 1} 点",
            "解説": "相手を広めに押さえ、中穴・高配当をしっかり狙う",
            "想定オッズ": 28.5
        }
        all_bets["3連単（フォーメーション）"] = {
            "方式": "3連単 フォーメーション",
            "買い目": f"1着: {h_uma}\n2着: {', '.join([str(u) for u in [t_uma, a_uma] if u])}\n3着: {', '.join([str(u) for u in partner_umas])}",
            "点数": f"{max(1, (len([u for u in [t_uma, a_uma] if u]) * (len(partner_umas)-1)))} 点",
            "解説": "本命1着固定で高回収率・ハイリターンを狙う",
            "想定オッズ": 85.0
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
        all_bets["馬連/ワイド 穴馬軸流し"] = {
            "方式": f"馬連・ワイド 穴軸 (軸: {ana_target}番)",
            "買い目": f"{ana_target} － " + ", ".join([str(u) for u in [h_uma, t_uma, a_uma] if u != ana_target]),
            "点数": f"{len([u for u in [h_uma, t_uma, a_uma] if u != ana_target])} 点",
            "解説": "高オッズ妙味のある特注穴馬から上位馬へ流して跳ね狙い",
            "想定オッズ": 24.0
        }
        all_bets["3連複 穴頭一発流し"] = {
            "方式": f"3連複 1頭軸 (軸: {ana_target}番)",
            "買い目": f"{ana_target} ＝ " + ", ".join([str(u) for u in partner_umas if u != ana_target] + [str(h_uma)]),
            "点数": f"{len(partner_umas)*(len(partner_umas)-1)//2 if len(partner_umas)>=2 else 1} 点",
            "解説": "穴馬絡みの波乱決着で万馬券級の特大高配当をカバー",
            "想定オッズ": 65.0
        }
        all_bets["3連単 穴頭波乱フォーメーション"] = {
            "方式": "3連単 穴固定フォーメーション",
            "買い目": f"1着: {', '.join([str(u) for u in [a_uma, x_uma] if u])}\n2着: {', '.join([str(u) for u in [h_uma, t_uma, a_uma, x_uma] if u])}\n3着: {', '.join([str(u) for u in partner_umas])}",
            "点数": "12〜24 点",
            "解説": "人気馬の着崩れ・荒れるレースを想定した高回収率勝負馬券",
            "想定オッズ": 220.0
        }

    elif "3連単マルチ" in strategy_mode:
        all_bets["馬単 評価上位BOX"] = {
            "方式": "馬単 BOX (上位3頭)",
            "買い目": f"BOX: {', '.join([str(u) for u in [h_uma, t_uma, a_uma] if u])}",
            "点数": "6 点",
            "解説": "AI評価上位3頭による馬単BOXで1着2着の順不同取りこぼしを完全ガード",
            "想定オッズ": 18.0
        }
        all_bets["3連単 1頭軸マルチ"] = {
            "方式": f"3連単 1頭軸マルチ (軸: {h_uma}番)",
            "買い目": f"軸: {h_uma} ↔ 相手: {', '.join([str(u) for u in partner_umas[:4]])}",
            "点数": f"{len(partner_umas[:4]) * (len(partner_umas[:4])-1) * 3 if len(partner_umas[:4])>=2 else 6} 点",
            "解説": "本命馬が2着・3着に敗れても取りこぼさない高回収マルチ",
            "想定オッズ": 140.0
        }
        all_bets["3連単 2頭軸マルチ"] = {
            "方式": f"3連単 2頭軸マルチ (軸: {h_uma}, {t_uma}番)",
            "買い目": f"軸: {h_uma}, {t_uma} ↔ 相手: {', '.join([str(u) for u in partner_umas if u not in [h_uma, t_uma]])}",
            "点数": f"{len([u for u in partner_umas if u not in [h_uma, t_uma]]) * 6} 点",
            "解説": "本命・対抗の2頭が3着以内に入れば相手どれでも的中",
            "想定オッズ": 95.0
        }
        all_bets["3連複 評価上位4頭BOX"] = {
            "方式": "3連複 BOX (4頭)",
            "買い目": "BOX: " + ", ".join([str(u) for u in [h_uma, t_uma, a_uma, x_uma] if u]),
            "点数": "4 点",
            "解説": "上位評価4頭のBOXで確実な着漏れ防止",
            "想定オッズ": 18.0
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

def calculate_capital_allocation(tickets, total_budget):
    valid_tickets = [t for t in tickets if t.get('odds', 0) > 0]
    if not valid_tickets or total_budget <= 0:
        return [], 0, 0

    inv_sum = sum(1.0 / t['odds'] for t in valid_tickets)
    synthetic_odds = round(1.0 / inv_sum, 2) if inv_sum > 0 else 0

    results = []
    for t in valid_tickets:
        raw_alloc = total_budget / (t['odds'] * inv_sum)
        alloc_100 = max(100, round(raw_alloc / 100.0) * 100)
        expected_payout = round(alloc_100 * t['odds'])
        expected_profit = expected_payout - total_budget
        results.append({
            '買い目': t['name'],
            'オッズ': f"{t['odds']}倍",
            '最適配分金額': f"{alloc_100:,}円",
            '的中時払戻想定': f"{expected_payout:,}円",
            '的中時推定純利益': f"{'+' if expected_profit > 0 else ''}{expected_profit:,}円",
            '_alloc': alloc_100
        })

    total_allocated = sum(r['_alloc'] for r in results)
    for r in results:
        del r['_alloc']

    return results, synthetic_odds, total_allocated

def get_race_data(input_id, paddock_status_map=None, race_env=None):
    clean_id = re.sub(r'\D', '', str(input_id))
    if len(clean_id) == 10 and clean_id.startswith(('20', '21', '22', '23', '24', '25', '26')):
        clean_id = '20' + clean_id

    if not clean_id or len(clean_id) != 12:
        return None, "有効な12桁（または10桁）のレースIDを入力してください。"

    data_list = []
    errors = []

    db_url = f"https://db.netkeiba.com/race/{clean_id}/"
    soup, err = fetch_html(db_url)
    if soup: data_list = parse_db_netkeiba(soup)
    elif err: errors.append(f"DB: {err}")

    if not data_list:
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
        return None, f"レースデータが見つかりませんでした。(試行ID: {clean_id})\n" + "\n".join(errors)

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
st.markdown('<div class="hero-container"><div class="hero-title">🏇 Kuina AI Racing Pro</div><div class="hero-sub">JRA中央競馬 AIレーシング・アナリティクス</div></div>', unsafe_allow_html=True)

# 日本標準時 (JST) での現在日付
today_jst = datetime.datetime.now(JST).date()

st.markdown("### 📅 分析対象レースの選択")
c_date1, c_date2 = st.columns([1, 2])

with c_date1:
    selected_date = st.date_input("開催日を選択:", value=today_jst)
    dt_str = selected_date.strftime("%Y%m%d")
    
    if st.button("🔍 レース一覧を取得"):
        with st.spinner(f"{selected_date.strftime('%Y/%m/%d')} のJRA全レースを取得中..."):
            races, err = fetch_race_list_by_date(dt_str)
            if err:
                st.error(err)
            else:
                st.session_state['fetched_races'] = races
                st.session_state['current_date_str'] = dt_str

with c_date2:
    if 'fetched_races' in st.session_state and st.session_state['fetched_races']:
        races_list = st.session_state['fetched_races']
        race_options = {f"{r['name']} (ID: {r['id']})": r['id'] for r in races_list}
        
        selected_race_label = st.selectbox(
            f"📍 {selected_date.strftime('%Y/%m/%d')} の全レース一覧から選択:",
            options=list(race_options.keys()),
            key=f"select_race_{dt_str}"
        )
        
        if selected_race_label:
            st.session_state['selected_race_id'] = race_options[selected_race_label]

target_race_id = st.session_state.get('selected_race_id', None)


# Results Area
# ---------------------------------------------------------
if target_race_id:
    st.markdown("---")
    
    if 'paddock_map' not in st.session_state:
        st.session_state['paddock_map'] = {}

    st.markdown("### 🌦️ トラックバイアス・天候・展開ペルソナ調整")
    env_c1, env_c2, env_c3, env_c4 = st.columns(4)
    
    with env_c1:
        sel_weather = st.selectbox("☀️ 天候", ["晴", "曇", "雨", "小雨"], index=0)
    with env_c2:
        sel_condition = st.selectbox("🌿 馬場状態", ["良", "稍重", "重", "不良"], index=0)
    with env_c3:
        sel_bias = st.selectbox("🚧 トラックバイアス", ["⚪ フラット", "🟩 内伸び・前残り有利", "🟨 外伸び・差し有利"], index=0)
    with env_c4:
        sel_pace = st.selectbox("🏃 展開・ペース予想", ["ミドルペース", "スローペース（前残り）", "ハイペース（差し有利）"], index=0)

    current_race_env = {
        'weather': sel_weather,
        'condition': sel_condition,
        'bias': sel_bias,
        'pace': sel_pace
    }

    with st.spinner("🤖 AI多角分析エンジン実行中（血統・騎手・バイアス・展開統合中）..."):
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

            with st.expander("🐴 直前パドック気配・状態補正チェック（クリックで展開）"):
                st.caption("パドックで見た気配を選択すると、AIスコアと推奨買い目がリアルタイムで再判定されます。")
                p_cols = st.columns(3)
                p_options = ["⚪ 普通 (0pt)", "✨ 絶好調 (+8pt)", "⚠️ 太め残り (-5pt)", "💥 テンション高 (-6pt)"]
                
                updated_paddock = {}
                for idx, horse in enumerate(data):
                    col_idx = idx % 3
                    with p_cols[col_idx]:
                        default_val = st.session_state['paddock_map'].get(horse['馬番'], "⚪ 普通 (0pt)")
                        sel_p = st.selectbox(
                            f"{horse['馬番']}番 {horse['馬名']} ({horse['騎手']} / {horse['馬体重']})",
                            options=p_options,
                            index=p_options.index(default_val) if default_val in p_options else 0,
                            key=f"paddock_{target_race_id}_{horse['馬番']}"
                        )
                        updated_paddock[horse['馬番']] = sel_p

                if st.button("🔄 パドック気配を反映してAI再スコアリング"):
                    st.session_state['paddock_map'] = updated_paddock
                    st.rerun()

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
                            単勝オッズ: <strong>{horse['単勝オッズ']}倍</strong> ({horse['人気']}人気) | 馬体重: <strong>{horse['馬体重']}</strong>
                        </p>
                        <p style="margin: 4px 0; color: #047857; font-size: 0.85rem; word-break: break-word;">
                            <strong>血統適性:</strong> {horse['血統適性']}
                        </p>
                        <p style="margin: 4px 0; color: #1e40af; font-size: 0.85rem; word-break: break-word;">
                            <strong>バイアス展開:</strong> {horse['バイアス展開']}
                        </p>
                        <hr style="border-color: #cbd5e1; margin: 10px 0;">
                        <p style="font-size: 0.88rem; color: #475569; line-height: 1.5; word-break: break-word; white-space: normal;">
                            {horse['予想根拠']}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("### 🎫 競馬AI 推奨戦略＆買い目設定")

            strat_col1, strat_col2 = st.columns(2)

            with strat_col1:
                strategy_mode = st.radio(
                    "🎯 買い目戦略スタイルの選択:",
                    ["⚖️ バランス重視（王道）", "🔥 高配当・妙味狙い（万馬券特化）", "🎯 3連単マルチ＆BOX特化"],
                    index=0,
                    horizontal=True
                )

            with strat_col2:
                selected_tickets = st.multiselect(
                    "🎟️ 表示したい馬券種を絞り込み（複数選択可）:",
                    options=["馬単", "馬連", "ワイド", "3連複", "3連単", "マルチ", "BOX"],
                    default=[]
                )

            bets = generate_betting_recommendations(data, strategy_mode, selected_tickets)

            if bets:
                b_cols = st.columns(len(bets)) if len(bets) <= 4 else st.columns(3)
                for idx, (b_name, b_info) in enumerate(bets.items()):
                    col_target = b_cols[idx % len(b_cols)]
                    with col_target:
                        st.markdown(f"""
                        <div class="bet-card">
                            <div class="bet-title">{b_name}</div>
                            <div style="font-size: 0.85rem; color: #64748b;">{b_info['方式']} ({b_info['点数']})</div>
                            <div class="bet-code">{b_info['買い目']}</div>
                            <div style="font-size: 0.83rem; color: #475569; margin-top: 6px;">{b_info['解説']}</div>
                        </div>
                        """, unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("### 🎰 全券種対応！資金配分＆オッズシミュレーター")
            st.caption("馬単・馬連・ワイド・3連複・3連単および単勝（1頭）・複勝（2頭）から選択してトリガミなし資金配分を実行します。")

            sim_option_dict = {}

            for b_name, b_info in bets.items():
                lbl = f"【AI推奨: {b_name}】 {b_info['方式']} (想定{b_info.get('想定オッズ', 10.0)}倍)"
                sim_option_dict[lbl] = {
                    'name': f"{b_name} ({b_info['方式']})",
                    'odds': b_info.get('想定オッズ', 10.0)
                }

            top_ranked = sorted([d for d in data if d['単勝オッズ'] != "未確定"], key=lambda x: x.get('AI予想スコア', 0), reverse=True)

            for d in top_ranked[:1]:
                try:
                    o_val = float(d['単勝オッズ'])
                    lbl_t = f"【単勝】 {d['馬番']}番 {d['馬名']} ({o_val}倍)"
                    sim_option_dict[lbl_t] = {
                        'name': f"単勝 {d['馬番']}番 {d['馬名']}",
                        'odds': o_val
                    }
                except ValueError:
                    pass

            for d in top_ranked[:2]:
                try:
                    o_val = float(d['単勝オッズ'])
                    f_odds = round(max(1.1, o_val * 0.35), 1)
                    lbl_f = f"【複勝】 {d['馬番']}番 {d['馬名']} (想定{f_odds}倍)"
                    sim_option_dict[lbl_f] = {
                        'name': f"複勝 {d['馬番']}番 {d['馬名']}",
                        'odds': f_odds
                    }
                except ValueError:
                    pass

            sim_col1, sim_col2 = st.columns(2)

            with sim_col1:
                total_sim_budget = st.number_input("総購入予算（円）", min_value=1000, max_value=1000000, value=10000, step=1000)
                select_all_tickets = st.checkbox("✅ 利用可能な買い目を全選択する（全券種一括）", value=False)
                
                all_option_keys = list(sim_option_dict.keys())
                default_selections = all_option_keys if select_all_tickets else all_option_keys[:4]

                selected_sim_labels = st.multiselect(
                    "🎯 シミュレーション対象の買い目を選択（馬単・全券種対応）:",
                    options=all_option_keys,
                    default=default_selections
                )

            with sim_col2:
                if selected_sim_labels:
                    sim_tickets = [sim_option_dict[lbl] for lbl in selected_sim_labels if lbl in sim_option_dict]

                    sim_results, syn_odds, total_alloc = calculate_capital_allocation(sim_tickets, total_sim_budget)

                    if sim_results:
                        st.markdown(f"""
                        <div class="sim-card">
                            <h4 style="margin-top:0; color:#047857;">💡 全券種 資金配分シミュレーション結果</h4>
                            <p style="font-size:1.1rem; margin:3px 0;"><strong>総予算:</strong> {total_sim_budget:,} 円 | <strong>合計購入額:</strong> {total_alloc:,} 円</p>
                            <p style="font-size:1.2rem; font-weight:bold; color:#059669; margin:3px 0;">
                                合成オッズ: {syn_odds} 倍 (選択した買い目のいずれかが的中すれば均等回収)
                            </p>
                        </div>
                        """, unsafe_allow_html=True)

                        sim_df = pd.DataFrame(sim_results)
                        st.dataframe(sim_df, use_container_width=True)
                else:
                    st.info("左側の選択欄からシミュレーションしたい対象の買い目・券種を選択してください。")

            st.markdown("---")
            st.markdown("### 💰 実績 馬券収支メモ")

            calc_col1, calc_col2 = st.columns(2)

            with calc_col1:
                st.markdown("#### 🧮 馬券購入＆払戻金 計算")
                bet_type = st.selectbox("馬券種別", ["馬単", "馬連", "ワイド", "3連複", "3连単", "3連単マルチ", "単勝", "複勝", "枠連", "その他"])
                invest_amount = st.number_input("購入額（投資金額 / 円）", min_value=100, max_value=1000000, value=1000, step=100)
                payout_amount = st.number_input("払戻金（円）※不命中の場合は0円", min_value=0, max_value=10000000, value=0, step=100)

                profit = payout_amount - invest_amount
                recovery_rate = round((payout_amount / invest_amount) * 100, 1) if invest_amount > 0 else 0.0

                st.markdown(f"""
                <div class="calc-card">
                    <h4 style="margin-top:0; color:#1e40af;">【計算結果】</h4>
                    <p style="font-size:1.1rem; margin:5px 0;"><strong>投資合計:</strong> {invest_amount:,} 円</p>
                    <p style="font-size:1.1rem; margin:5px 0;"><strong>払戻合計:</strong> {payout_amount:,} 円</p>
                    <p style="font-size:1.3rem; font-weight:bold; color:{'#059669' if profit >= 0 else '#dc2626'}; margin:5px 0;">
                        損益: {'+' if profit > 0 else ''}{profit:,} 円
                    </p>
                    <p style="font-size:1.1rem; font-weight:bold; color:#2563eb; margin:5px 0;">
                        回収率: {recovery_rate}%
                    </p>
                </div>
                """, unsafe_allow_html=True)

                if st.button("📝 この収支結果をトータル履歴に記録・追加"):
                    if 'balance_history' not in st.session_state:
                        st.session_state['balance_history'] = []
                    
                    st.session_state['balance_history'].append({
                        "日時": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "レースID": target_race_id,
                        "馬券種": bet_type,
                        "投資額": invest_amount,
                        "払戻額": payout_amount,
                        "収支": profit,
                        "回収率": f"{recovery_rate}%"
                    })
                    st.success("収支履歴に記録しました！")

            with calc_col2:
                st.markdown("#### 📜 累計収支サマリー（全レース合計）")
                if 'balance_history' in st.session_state and st.session_state['balance_history']:
                    hist_df = pd.DataFrame(st.session_state['balance_history'])
                    total_invest = hist_df['投資額'].sum()
                    total_payout = hist_df['払戻額'].sum()
                    total_profit = total_payout - total_invest
                    total_recovery = round((total_payout / total_invest) * 100, 1) if total_invest > 0 else 0.0

                    s1, s2 = st.columns(2)
                    s1.metric("累計投資額", f"{total_invest:,} 円")
                    s2.metric("累計払戻額", f"{total_payout:,} 円")
                    
                    s3, s4 = st.columns(2)
                    s3.metric("トータル収支", f"{'+' if total_profit > 0 else ''}{total_profit:,} 円", delta=f"{total_profit:,}円")
                    s4.metric("トータル回収率", f"{total_recovery} %")

                    st.markdown("##### 記録一覧")
                    st.dataframe(hist_df, use_container_width=True, height=200)

                    if st.button("🗑️ 収支履歴をリセット"):
                        st.session_state['balance_history'] = []
                        st.rerun()
                else:
                    st.info("まだ収支履歴が記録されていません。")

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("### 📋 AI予想・詳細分析一覧")
            
            cols = ['予想印', '枠番', '馬番', '馬名', 'AI予想スコア', '騎手', '血統適性', 'バイアス展開', '単勝オッズ', '人気', '馬体重', 'パドック評価', '予想根拠']
            df_display = df[[c for c in cols if c in df.columns]]

            def highlight_row(val):
                if '◎' in str(val): return 'background-color: #fee2e2; color: #991b1b; font-weight: bold;'
                elif '◯' in str(val): return 'background-color: #d1fae5; color: #065f46; font-weight: bold;'
                elif '▲' in str(val): return 'background-color: #dbeafe; color: #1e40af; font-weight: bold;'
                elif '☆' in str(val): return 'background-color: #fef9c3; color: #854d0e; font-weight: bold;'
                return ''

            column_config = {
                "予想印": st.column_config.TextColumn("印", width="small"),
                "枠番": st.column_config.NumberColumn("枠", width="small"),
                "馬番": st.column_config.NumberColumn("馬番", width="small"),
                "馬名": st.column_config.TextColumn("馬名", width="medium"),
                "AI予想スコア": st.column_config.NumberColumn("スコア", width="small", format="%.1f"),
                "騎手": st.column_config.TextColumn("騎手", width="medium"),
                "血統適性": st.column_config.TextColumn("血統適性", width="large"),
                "バイアス展開": st.column_config.TextColumn("バイアス展開", width="large"),
                "単勝オッズ": st.column_config.TextColumn("オッズ", width="small"),
                "人気": st.column_config.TextColumn("人気", width="small"),
                "馬体重": st.column_config.TextColumn("馬体重", width="small"),
                "パドック評価": st.column_config.TextColumn("パドック", width="medium"),
                "予想根拠": st.column_config.TextColumn("予想根拠", width="large")
            }

            st.dataframe(
                df_display.style.map(highlight_row, subset=['予想印']),
                use_container_width=True,
                column_config=column_config,
                hide_index=True,
                height=480
            )

            csv = df_display.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 分析結果（CSV）を保存する",
                data=csv,
                file_name=f"keiba_ai_{target_race_id}.csv",
                mime="text/csv"
            )