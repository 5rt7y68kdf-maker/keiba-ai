import re
import requests
from bs4 import BeautifulSoup
import urllib3
import streamlit as st
import datetime
import pandas as pd

# SSL証明書警告の非表示化
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 全国10競馬場のコードマップ
VENUE_MAP = {
    "札幌": "01", "函館": "02", "福島": "03", "新潟": "04",
    "東京": "05", "中山": "06", "中京": "07", "京都": "08",
    "阪神": "09", "小倉": "10"
}

ALL_TICKET_TYPES = ["単勝", "複勝", "枠連", "馬連", "ワイド", "馬単", "3連複", "3連単"]

TOP_JOCKEYS_S = ["ルメール", "川田", "武豊", "坂井", "横山武", "戸崎", "モレイラ", "レーン"]
TOP_JOCKEYS_A = ["松山", "鮫島克", "岩田望", "西村淳", "菅原明", "津村", "田辺", "デムーロ", "丹内"]

# ---------------------------------------------------------
# Streamlit Page Config & High-Contrast Light Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="Kuina AI Racing Pro",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Clean, high-contrast light theme with prominent buttons
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    
    .stApp {
        background-color: #f8fafc;
        color: #0f172a;
        font-family: 'Inter', 'Helvetica Neue', Arial, 'Hiragino Sans', sans-serif;
    }
    
    .hero-title {
        font-size: 2.1rem;
        font-weight: 800;
        color: #1e3a8a;
        margin-bottom: 1rem;
        letter-spacing: -0.02em;
    }

    /* ボタンの視認性改善（スマホ対応） */
    .stButton>button {
        width: 100% !important;
        background: linear-gradient(135deg, #1e40af 0%, #2563eb 100%) !important;
        color: #ffffff !important;
        font-weight: 800 !important;
        font-size: 1.05rem !important;
        border-radius: 12px !important;
        border: none !important;
        padding: 12px 18px !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25) !important;
        margin-bottom: 6px !important;
    }
    .stButton>button:hover {
        background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%) !important;
        color: #ffffff !important;
    }

    /* Horse Card Styling with Full Text Visibility */
    .horse-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 18px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        margin-bottom: 16px;
        height: auto !important;
        min-height: 240px;
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
        font-size: 1.35rem;
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
        margin-bottom: 10px;
    }
    .bet-title {
        font-weight: 700;
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

    races = []
    db_url = f"https://db.netkeiba.com/race/list/{clean_date}/"
    soup, _ = fetch_html(db_url)
    if soup:
        for a in soup.find_all('a'):
            href = a.get('href', '')
            m = re.search(r'/race/(\d{12})', href)
            if m:
                r_id = m.group(1)
                txt = a.text.strip().replace('\n', ' ')
                txt = re.sub(r'\s+', ' ', txt)
                if txt and not any(r['id'] == r_id for r in races):
                    races.append({'id': r_id, 'name': txt})

    if not races:
        race_url = f"https://race.netkeiba.com/top/race_list.html?kaijo_date={clean_date}"
        soup, _ = fetch_html(race_url)
        if soup:
            for a in soup.find_all('a'):
                href = a.get('href', '')
                m = re.search(r'race_id=(\d{12})', href) or re.search(r'/race/(\d{12})', href)
                if m:
                    r_id = m.group(1)
                    txt = a.text.strip().replace('\n', ' ')
                    txt = re.sub(r'\s+', ' ', txt)
                    if txt and not any(r['id'] == r_id for r in races):
                        races.append({'id': r_id, 'name': txt})

    if not races:
        return [], f"指定された日付 ({clean_date}) のレースデータは見つかりませんでした。"

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
                uma_txt = tds[0].text.strip() if len(tds) > 1 else ''
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
# AI Score Engine (オッズ期待値・血統・展開拡張)
# ---------------------------------------------------------
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

        j_score = 0.0
        j_comment = "騎手標準"
        if any(tj in jockey for tj in TOP_JOCKEYS_S):
            j_score = 7.0
            j_comment = f"【トップ騎手】{jockey}"
        elif any(tj in jockey for tj in TOP_JOCKEYS_A):
            j_score = 4.0
            j_comment = f"【有力騎手】{jockey}"

        blood_score = 5.0
        blood_comment = "【血統高適性】良馬場スピード血統"
        if race_env['condition'] in ['重', '不良', '稍重']:
            if any(kw in horse_name for kw in ["キング", "ゴールド", "ダノン", "ボルド", "パワー", "ロック", "ロベルト"]):
                blood_score = 7.0
                blood_comment = f"【血統高適性】パワー型血統 ({race_env['condition']}馬場順応)"

        bias_score = 2.0
        bias_comment = "馬場フラット"
        if "内伸び" in race_env['bias'] and waku in [1, 2, 3]:
            bias_score = 6.0
            bias_comment = f"【バイアス好走】内枠{waku}枠有利"

        pattern_score = 4.0
        pattern_comment = "展開適合"
        if race_env['pace'] == 'ハイペース（差し有利）' and p_val >= 4 and o_val >= 10.0:
            pattern_score = 6.0
            pattern_comment = "【好走パターン】ハイペース差し一発"

        p_status = paddock_status_map.get(uma, "⚪ 普通 (0pt)")
        paddock_score = 7.0 if "絶好調" in p_status else 0.0

        raw_score = pop_score + odds_score + weight_bonus + j_score + blood_score + bias_score + pattern_score + paddock_score + 5
        score = round(min(99.9, max(10.0, raw_score)), 1)

        # 期待値 (EV) & 回収率の算出
        win_prob = round(max(1.0, score / 3.5), 1)
        ev_val = round((win_prob / 100.0) * o_val, 2)
        rec_rate = int(ev_val * 100)

        d_copy = dict(d)
        d_copy['_raw_score'] = score
        d_copy['AI想定勝率'] = f"{win_prob}%"
        d_copy['期待値(EV)'] = f"{ev_val}"
        d_copy['期待回収率'] = f"{rec_rate}%"
        d_copy['パドック評価'] = p_status
        d_copy['騎手評価'] = j_comment
        d_copy['血統適性'] = blood_comment
        d_copy['バイアス展開'] = f"{bias_comment} / {pattern_comment}"
        scored_items.append(d_copy)

    scored_items.sort(key=lambda x: x['_raw_score'], reverse=True)
    mark_list = ['◎ 本命', '◯ 対抗', '▲ 単穴', '△ 連下', '△ 連下', '☆ 穴馬']
    
    for idx, item in enumerate(scored_items):
        mark = mark_list[idx] if idx < len(mark_list) else 'ー'
        item['予想印'] = mark
        item['AI予想スコア'] = item['_raw_score']
        
        o_str = f"{item['単勝オッズ']}倍" if item['単勝オッズ'] != "未確定" else "オッズ未確定"
        item['予想根拠'] = f"AIスコア: {item['_raw_score']}pt | 期待値: {item['期待値(EV)']} (回収率 {item['期待回収率']}) | 単勝 {o_str}"

        del item['_raw_score']

    scored_items.sort(key=lambda x: x['馬番'] if isinstance(x['馬番'], int) else 99)
    return scored_items

def get_race_data(input_id, paddock_status_map=None, race_env=None):
    clean_id = re.sub(r'\D', '', str(input_id))
    if len(clean_id) == 10 and clean_id.startswith(('20', '21', '22', '23', '24', '25', '26')):
        clean_id = '20' + clean_id

    if not clean_id or len(clean_id) != 12:
        return None, "有効な12桁のレースIDを入力してください。"

    data_list = []
    db_url = f"https://db.netkeiba.com/race/{clean_id}/"
    soup, _ = fetch_html(db_url)
    if soup: data_list = parse_db_netkeiba(soup)

    if not data_list:
        race_urls = [
            f"https://race.netkeiba.com/race/shutuba.html?race_id={clean_id}",
            f"https://race.netkeiba.com/race/result.html?race_id={clean_id}"
        ]
        for url in race_urls:
            soup, _ = fetch_html(url)
            if soup:
                data_list = parse_race_netkeiba(soup)
                if data_list: break

    if not data_list:
        return None, f"レースデータが見つかりませんでした。(ID: {clean_id})"

    data_list = calculate_ai_scores(data_list, paddock_status_map, race_env)
    return data_list, None

# ---------------------------------------------------------
# UI Core Component
# ---------------------------------------------------------
st.markdown('<div class="hero-title">🏇 Kuina AI Racing Pro</div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["⚡ 競馬場・レース指定（おすすめ）", "📅 日付で全レース検索", "🏆 サンプルID"])

target_race_id = None
today = datetime.date.today()

with tab1:
    st.caption("競馬場と1R〜12Rのボタンを選ぶだけで一瞬で全レースをロードします！")
    c_v, c_r = st.columns([1, 2])
    with c_v:
        sel_v = st.selectbox("競馬場を選択:", list(VENUE_MAP.keys()), index=4)
    with c_r:
        r_num = st.radio("レース番号を選択:", [f"{i}R" for i in range(1, 13)], index=10, horizontal=True)
    
    r_digit = re.sub(r'\D', '', r_num)
    gen_id = f"{today.year}{VENUE_MAP[sel_v]}0101{int(r_digit):02d}"
    if st.button(f"🚀 【{sel_v} {r_num}】をAI解析実行"):
        target_race_id = gen_id

with tab2:
    selected_date = st.date_input("開催日を選択:", value=today)
    if st.button("🔍 日付でレース一覧を取得"):
        dt_str = selected_date.strftime("%Y%m%d")
        races, err = fetch_race_list_by_date(dt_str)
        if err: st.error(err)
        else: st.session_state['fetched_races'] = races

    if 'fetched_races' in st.session_state and st.session_state['fetched_races']:
        race_options = {f"{r['name']} (ID: {r['id']})": r['id'] for r in st.session_state['fetched_races']}
        selected_race_label = st.selectbox("レースを選択:", list(race_options.keys()))
        if selected_race_label:
            target_race_id = race_options[selected_race_label]

with tab3:
    if st.button("📌 日本ダービー (2024年) をお試し解析"):
        target_race_id = "202405021211"

# ---------------------------------------------------------
# Results Area
# ---------------------------------------------------------
if target_race_id:
    st.markdown("---")
    data, error = get_race_data(target_race_id)

    if error:
        st.error(error)
    else:
        df = pd.DataFrame(data)
        honmei = next((d for d in data if '◎' in d.get('予想印', '')), None)

        m1, m2, m3 = st.columns(3)
        m1.metric("対象レースID", target_race_id)
        m2.metric("出走頭数", f"{len(data)} 頭")
        m3.metric("AI最有力 本命馬", f"{honmei['馬番']}番 {honmei['馬名']}" if honmei else "ー")

        st.markdown("### 🎯 AI選定・上位評価馬（期待値・回収率付き）")
        top_3 = sorted(data, key=lambda x: x.get('AI予想スコア', 0), reverse=True)[:3]
        
        cols = st.columns(3)
        for idx, (horse, col_c) in enumerate(zip(top_3, cols)):
            with col_c:
                st.markdown(f"""
                <div class="horse-card">
                    <div style="font-weight:bold; color:#1e40af;">{horse['予想印']}</div>
                    <div class="horse-name-title">{horse['馬番']}番 {horse['馬名']}</div>
                    <p style="color:#2563eb; font-weight:bold;">AIスコア: {horse['AI予想スコア']}pt</p>
                    <p style="color:#059669; font-weight:bold;">期待回収率: {horse['期待回収率']} (EV: {horse['期待値(EV)']})</p>
                    <p>騎手: {horse['騎手']} | オッズ: {horse['単勝オッズ']}倍</p>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("### 📋 全出走馬 AI分析一覧表")
        st.dataframe(df, use_container_width=True)