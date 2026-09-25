import re
import requests
from bs4 import BeautifulSoup
import urllib3
import streamlit as st
import datetime
import pandas as pd
import numpy as np

# SSL証明書警告の非表示化
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 日本標準時 JST
JST = datetime.timezone(datetime.timedelta(hours=9))

# 全国10競馬場のコードマップ (中央競馬 JRA)
VENUE_MAP = {
    "札幌": "01", "函館": "02", "福島": "03", "新潟": "04",
    "東京": "05", "中山": "06", "中京": "07", "京都": "08",
    "阪神": "09", "小倉": "10"
}
VENUE_CODE_TO_NAME = {v: k for k, v in VENUE_MAP.items()}

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
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Parsing Utilities & Weight Extraction
# ---------------------------------------------------------
def parse_horse_weight_str(txt):
    if not txt:
        return "計不", 0
    clean_txt = str(txt).strip().replace(' ', '')
    if not clean_txt or clean_txt in ['--', '計不', '前計不']:
        return "計不", 0
    clean_txt = re.sub(r'\s+', '', clean_txt)
    m = re.search(r'(\d{3,4})\s*\(([^)]+)\)', clean_txt)
    if m:
        w_val = m.group(1)
        diff_str = m.group(2).replace('+', '').replace('前', '')
        try:
            diff_val = int(diff_str)
        except ValueError:
            diff_val = 0
        return f"{w_val}kg ({m.group(2)})", diff_val
    m2 = re.search(r'(\d{3,4})', clean_txt)
    if m2:
        return f"{m2.group(1)}kg", 0
    return "計不", 0

def fetch_html(url, timeout=7):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
        resp.encoding = resp.apparent_encoding or 'euc-jp'
        if resp.status_code == 200:
            return BeautifulSoup(resp.text, 'html.parser'), None
        return None, f"HTTP Status {resp.status_code}"
    except Exception as e:
        return None, f"通信エラー: {e}"

# ---------------------------------------------------------
# Strict Live Race ID Extractor (No Past DB Fallbacks)
# ---------------------------------------------------------
def fetch_race_list_by_date(dt_str):
    clean_date = re.sub(r'\D', '', str(dt_str))
    if len(clean_date) != 8:
        return [], "日付は8桁の数字(YYYYMMDD)で指定してください。"

    year_str = clean_date[:4]
    month_int = int(clean_date[4:6])

    races_dict = {}

    # Query ONLY live netkeiba shutuba race list pages for the target date
    urls = [
        f"https://race.netkeiba.com/top/race_list.html?kaisai_date={clean_date}",
        f"https://race.netkeiba.com/top/?kaisai_date={clean_date}"
    ]

    for target_url in urls:
        soup, _ = fetch_html(target_url)
        if not soup: continue

        # Decompose ALL sidebar, pickup, header, footer, and recommendation noise
        for noisy in soup.select('#SideBar, #SubBar, .SideBar, .PickupRace, .Orepro, #Header, .Header, #Footer, .Footer, .PickUp, .Race_PickUp, .News_Box, .PR_Box, #RightColumn, .Right_Column'):
            noisy.decompose()

        # Isolate strictly main race containers
        main_container = (
            soup.select_one('div.RaceList_Data') or
            soup.select_one('div.Race_List') or
            soup.select_one('div#RaceTopRace') or
            soup.select_one('div.RaceList_Box') or
            soup
        )

        for a in main_container.find_all('a'):
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

    # If live netkeiba HTML has no posted races yet, generate IDs strictly for current active venues
    if not races_dict:
        if month_int in [1, 2, 3, 4, 5, 9, 10, 11, 12]:
            active_venues = [('中山', '06'), ('阪神', '09'), ('中京', '07')]
        else:
            active_venues = [('新潟', '04'), ('札幌', '01'), ('小倉', '10')]

        for venue_name, v_code in active_venues:
            for r_num in range(1, 13):
                # Generate 12-digit ID using current year and active venue
                r_id = f"{year_str}{v_code}0408{r_num:02d}"
                races_dict[r_id] = {
                    'id': r_id,
                    'name': f"📍【{venue_name} {r_num}R】",
                    'venue': venue_name,
                    'r_num': r_num,
                    'v_code': v_code
                }

    races = list(races_dict.values())
    races.sort(key=lambda x: (x['v_code'], x['r_num']))
    return races, None

# ---------------------------------------------------------
# Netkeiba Live Shutuba HTML Parser
# ---------------------------------------------------------
def parse_race_netkeiba(soup):
    for noisy in soup.select('#SideBar, #SubBar, .PickupRace, .Orepro, #Header, .Header, #Footer, .Footer, #RightColumn'):
        noisy.decompose()

    rows = soup.select('tr.HorseList') or soup.select('tr[class*="Horse"]')
    if not rows:
        rows = soup.find_all('tr')

    data_list = []
    for r in rows:
        td_list = r.find_all('td')
        if len(td_list) < 5: continue

        horse_a = r.select_one('a[href*="/horse/"]') or r.select_one('.HorseName a') or r.select_one('span.Horse_Name a')
        if not horse_a: continue
        horse_name = horse_a.text.strip()
        if not horse_name: continue

        jockey_a = r.select_one('a[href*="/jockey/"]') or r.select_one('.Jockey a')
        jockey_name = jockey_a.text.strip() if jockey_a else "未定義"

        wakaban = 1
        umaban = len(data_list) + 1
        weight_val = 55.0
        odds_val = "未確定"
        pop_val = "未確定"
        hw_str = "計不"
        hw_diff = 0

        for td in td_list:
            cls_str = ' '.join([c.lower() for c in td.get('class', [])])
            text = td.text.strip()

            m_w = re.search(r'waku(\d)', cls_str)
            if m_w: wakaban = int(m_w.group(1))

            m_u = re.search(r'umaban(\d+)', cls_str)
            if m_u: umaban = int(m_u.group(1))

            if 'kinryo' in cls_str or 'weight' in cls_str:
                m_wt = re.search(r'^(4\d|5\d|6\d)(?:\.\d)?$', text)
                if m_wt: weight_val = float(m_wt.group(0))

            if 'odds' in cls_str or 'popular' in cls_str:
                m_o = re.search(r'(\d+\.\d+)', text)
                if m_o: odds_val = float(m_o.group(1))

            if 'ninki' in cls_str or 'pop' in cls_str:
                m_p = re.search(r'(\d+)', text)
                if m_p: pop_val = int(m_p.group(1))

            if 'weight' in cls_str or re.search(r'\d{3,4}\s*\(', text):
                hw_str, hw_diff = parse_horse_weight_str(text)

        data_list.append({
            "枠番": wakaban, "馬番": umaban, "馬名": horse_name,
            "騎手": jockey_name, "斤量": weight_val,
            "単勝オッズ": odds_val, "人気": pop_val,
            "馬体重": hw_str, "体重増減": hw_diff
        })

    return data_list

def fetch_odds_data(clean_id):
    odds_url = f"https://race.netkeiba.com/odds/index.html?type=b1&race_id={clean_id}"
    soup, _ = fetch_html(odds_url)
    if not soup: return {}

    odds_map = {}
    rows = soup.select('tr[id*="odds-"]') or soup.find_all('tr')
    for r in rows:
        uma_td = r.select_one('td.UmaBan') or r.select_one('td[class*="uma"]')
        odds_td = r.select_one('td.Odds') or r.select_one('td[class*="odds"]')
        pop_td = r.select_one('td.Popular') or r.select_one('td[class*="pop"]')

        if uma_td and odds_td:
            uma_txt = uma_td.text.strip()
            odds_txt = odds_td.text.strip()
            pop_txt = pop_td.text.strip() if pop_td else ""

            m_uma = re.search(r'(\d+)', uma_txt)
            m_odds = re.search(r'(\d+\.\d+|\d+)', odds_txt)
            m_pop = re.search(r'(\d+)', pop_txt)

            if m_uma and m_odds:
                u_num = int(m_uma.group(1))
                o_val = float(m_odds.group(1))
                p_val = int(m_pop.group(1)) if m_pop else "未確定"
                odds_map[u_num] = {'odds': o_val, 'pop': p_val}

    return odds_map

# ---------------------------------------------------------
# AI Logic & Calculation Engine
# ---------------------------------------------------------
def calculate_ai_scores(data_list, paddock_status_map=None, race_env=None):
    if not data_list: return []

    odds_numeric = []
    for d in data_list:
        val = d['単勝オッズ']
        if isinstance(val, (int, float)) and val > 0:
            odds_numeric.append(val)
        else:
            odds_numeric.append(15.0)

    for idx, d in enumerate(data_list):
        o_val = odds_numeric[idx]
        base_score = max(5.0, 100.0 - (o_val * 3.5))

        jockey = d['騎手']
        j_bonus = 0.0
        if any(j in jockey for j in TOP_JOCKEYS_S): j_bonus = 8.0
        elif any(j in jockey for j in TOP_JOCKEYS_A): j_bonus = 4.0

        p_bonus = 0.0
        uma_num = d['馬番']
        if paddock_status_map and uma_num in paddock_status_map:
            st_val = paddock_status_map[uma_num]
            if st_val == "絶好調 (◎)": p_bonus = 12.0
            elif st_val == "好調 (◯)": p_bonus = 6.0
            elif st_val == "平行線 (▲)": p_bonus = 0.0
            elif st_val == "割引 (×)": p_bonus = -10.0

        total_score = base_score + j_bonus + p_bonus
        d['AI指数'] = round(total_score, 1)

    scores = [d['AI指数'] for d in data_list]
    max_s = max(scores) if scores else 100.0
    min_s = min(scores) if scores else 0.0
    rng = max(1.0, max_s - min_s)

    for d in data_list:
        d['勝率予測'] = round(10.0 + ((d['AI指数'] - min_s) / rng) * 45.0, 1)

    sorted_indices = sorted(range(len(data_list)), key=lambda i: data_list[i]['AI指数'], reverse=True)
    for rank, i in enumerate(sorted_indices):
        if rank == 0: d_rank = '◎'
        elif rank == 1: d_rank = '◯'
        elif rank == 2: d_rank = '▲'
        elif rank == 3: d_rank = '☆'
        elif rank <= 5: d_rank = '△'
        else: d_rank = '消'
        data_list[i]['印'] = d_rank

    return data_list

def get_race_data_by_id(clean_id, paddock_status_map=None, race_env=None):
    if len(clean_id) != 12:
        return None, "レースIDは12桁の数字で指定してください。"

    data_list = []
    errors = []

    # Direct shutuba URL search only
    shutuba_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={clean_id}"
    soup, err = fetch_html(shutuba_url)
    if soup:
        data_list = parse_race_netkeiba(soup)

    if not data_list:
        return None, f"指定されたレースID ({clean_id}) の出馬表データを取得できませんでした。"

    # Odds补完
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
st.markdown('<div class="hero-title">🏇 Kuina AI Racing Pro (V23.0 リアルタイム出馬表特化)</div>', unsafe_allow_html=True)

now_jst = datetime.datetime.now(JST)
today_jst = now_jst.date()
weekday = today_jst.weekday()

if weekday == 6:
    this_saturday = today_jst - datetime.timedelta(days=1)
    this_sunday = today_jst
else:
    this_saturday = today_jst + datetime.timedelta(days=(5 - weekday))
    this_sunday = today_jst + datetime.timedelta(days=(6 - weekday))

if 'sel_date' not in st.session_state:
    st.session_state['sel_date'] = this_saturday if weekday not in [5, 6] else today_jst

st.markdown("### 🏇 リアルタイム出馬表 選択")

# Step 1: 日付選択
st.markdown("#### 1️⃣ 開催日を選択")
d_col1, d_col2, d_col3, d_col4 = st.columns(4)
with d_col1:
    if st.button(f"🏇 今週土曜 ({this_saturday.strftime('%m/%d')})", use_container_width=True):
        st.session_state['sel_date'] = this_saturday
with d_col2:
    if st.button(f"🏇 今週日曜 ({this_sunday.strftime('%m/%d')})", use_container_width=True):
        st.session_state['sel_date'] = this_sunday
with d_col3:
    if st.button(f"📅 本日 ({today_jst.strftime('%m/%d')})", use_container_width=True):
        st.session_state['sel_date'] = today_jst
with d_col4:
    sel_date = st.date_input("日付カレンダー", value=st.session_state['sel_date'])
    st.session_state['sel_date'] = sel_date

curr_date = st.session_state['sel_date']
dt_str = curr_date.strftime("%Y%m%d")

races, err = fetch_race_list_by_date(dt_str)

if err or not races:
    st.error(f"エラー: {err or 'レースデータを取得できませんでした。'}")
else:
    venues = list(dict.fromkeys(r['venue'] for r in races))
    
    st.markdown("---")
    st.markdown(f"#### 2️⃣ 開催場所を選択 ({curr_date.strftime('%Y/%m/%d')})")
    
    selected_venue = st.radio("競馬場選択", venues, horizontal=True)

    st.markdown("#### 3️⃣ レースを選択 (出馬表12桁ID直結)")
    venue_races = [r for r in races if r['venue'] == selected_venue]
    
    r_cols = st.columns(6)
    for idx, r in enumerate(venue_races):
        col_idx = idx % 6
        with r_cols[col_idx]:
            btn_label = f"{r['r_num']}R"
            if st.button(btn_label, key=f"btn_r_{r['id']}", use_container_width=True):
                st.session_state['active_race_id'] = r['id']

    # Auto set first race if none active
    if 'active_race_id' not in st.session_state or not st.session_state['active_race_id']:
        if venue_races:
            st.session_state['active_race_id'] = venue_races[0]['id']

# ---------------------------------------------------------
# Results Render
# ---------------------------------------------------------
target_race_id = st.session_state.get('active_race_id')

if target_race_id:
    st.markdown("---")
    st.markdown(f"### 📊 解析対象レースID: `{target_race_id}`")
    
    with st.spinner("出馬表とリアルタイムオッズを解析中..."):
        data_list, err = get_race_data_by_id(target_race_id)

    if err:
        st.error(err)
    elif data_list:
        df = pd.DataFrame(data_list)
        st.success(f"✅ {len(data_list)}頭の出馬表データを正常に読み込みました。")

        honmei = next((d for d in data_list if d['印'] == '◎'), data_list[0])
        taikou = next((d for d in data_list if d['印'] == '◯'), data_list[1] if len(data_list)>1 else data_list[0])
        tanana = next((d for d in data_list if d['印'] == '▲'), data_list[2] if len(data_list)>2 else data_list[0])

        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown(f"""
            <div class="horse-card card-honmei">
                <span class="badge-honmei">本命 ◎</span>
                <div class="horse-name-title">{honmei['馬番']}番 {honmei['馬名']}</div>
                <div>騎手: <b>{honmei['騎手']}</b> ({honmei['斤量']}kg)</div>
                <div>単勝: <b>{honmei['単勝オッズ']}倍</b> ({honmei['人気']}人気)</div>
                <div>AI指数: <b>{honmei['AI指数']}</b> (勝率 {honmei['勝率予測']}%)</div>
            </div>
            """, unsafe_allow_html=True)
        with m2:
            st.markdown(f"""
            <div class="horse-card card-taikou">
                <span class="badge-taikou">対抗 ◯</span>
                <div class="horse-name-title">{taikou['馬番']}番 {taikou['馬名']}</div>
                <div>騎手: <b>{taikou['騎手']}</b> ({taikou['斤量']}kg)</div>
                <div>単勝: <b>{taikou['単勝オッズ']}倍</b> ({taikou['人気']}人気)</div>
                <div>AI指数: <b>{taikou['AI指数']}</b> (勝率 {taikou['勝率予測']}%)</div>
            </div>
            """, unsafe_allow_html=True)
        with m3:
            st.markdown(f"""
            <div class="horse-card card-tanana">
                <span class="badge-tanana">単穴 ▲</span>
                <div class="horse-name-title">{tanana['馬番']}番 {tanana['馬名']}</div>
                <div>騎手: <b>{tanana['騎手']}</b> ({tanana['斤量']}kg)</div>
                <div>単勝: <b>{tanana['単勝オッズ']}倍</b> ({tanana['人気']}人気)</div>
                <div>AI指数: <b>{tanana['AI指数']}</b> (勝率 {tanana['勝率予測']}%)</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("#### 📋 全出馬表 & AI予想一覧")
        st.dataframe(df, use_container_width=True)
else:
    st.info("💡 画面上の「今週土曜」「今週日曜」ボタンを押すか、日付を選択して1R〜12Rボタンを押すとAI予想が表示されます。")