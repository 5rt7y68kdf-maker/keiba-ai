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
# Streamlit Page Config & High-Contrast Light Clean Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="Kuina AI Racing Pro",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@500;700;800;900&display=swap');
    
    .stApp {
        background-color: #f8fafc;
        color: #0f172a;
        font-family: 'Noto Sans JP', sans-serif;
    }
    
    .main-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #1e3a8a 100%);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 16px;
        padding: 22px 20px;
        text-align: center;
        color: #ffffff;
        margin-bottom: 24px;
        box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.25);
    }
    .main-header h1 {
        font-size: 1.9rem;
        font-weight: 900;
        letter-spacing: 0.5px;
        margin: 0;
        color: #ffffff;
    }

    .step-header {
        background: #ffffff;
        border-left: 6px solid #2563eb;
        border-radius: 8px;
        padding: 12px 16px;
        font-size: 1.15rem;
        font-weight: 900;
        color: #0f172a;
        margin: 22px 0 14px 0;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
    }

    .card-clean {
        background: #ffffff !important;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.06);
        color: #0f172a !important;
    }
    
    .card-honmei {
        border: 3px solid #dc2626 !important;
        background: #fff5f5 !important;
    }
    .card-taikou {
        border: 3px solid #059669 !important;
        background: #f0fdf4 !important;
    }
    .card-tanana {
        border: 3px solid #2563eb !important;
        background: #eff6ff !important;
    }

    .badge-honmei { background: #dc2626; color: #ffffff; padding: 4px 12px; border-radius: 16px; font-weight: 800; font-size: 0.85rem; }
    .badge-taikou { background: #059669; color: #ffffff; padding: 4px 12px; border-radius: 16px; font-weight: 800; font-size: 0.85rem; }
    .badge-tanana { background: #2563eb; color: #ffffff; padding: 4px 12px; border-radius: 16px; font-weight: 800; font-size: 0.85rem; }

    .horse-title {
        font-size: 1.35rem;
        font-weight: 900;
        color: #0f172a !important;
        margin: 8px 0;
    }

    .stat-row {
        font-size: 0.95rem;
        color: #1e293b !important;
        margin-bottom: 4px;
        font-weight: 700;
    }

    .ai-box {
        background: #f0f9ff;
        border: 2px solid #0284c7;
        border-radius: 12px;
        padding: 16px;
        color: #0369a1;
        font-weight: 600;
        margin-top: 12px;
    }

    /* スマホ・PC共通ボタン調整 */
    .stButton > button {
        width: 100% !important;
        min-height: 48px !important;
        font-size: 1.0rem !important;
        font-weight: 800 !important;
        border-radius: 10px !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Helper Utilities & Parsers
# ---------------------------------------------------------
def parse_horse_weight_str(txt):
    if not txt:
        return "未計量 (発走前)", 0
    clean_txt = str(txt).strip().replace(' ', '')
    if not clean_txt or clean_txt in ['--', '計不', '前計不']:
        return "未計量 (発走前)", 0
    clean_txt = re.sub(r'\s+', '', clean_txt)
    m = re.search(r'(\d{3,4})\s*\(([^)]+)\)', clean_txt)
    if m:
        w_val = m.group(1)
        diff_raw = m.group(2).replace('前', '')
        if diff_raw == '0':
            diff_str = '±0'
            diff_val = 0
        elif diff_raw.startswith('+'):
            diff_str = diff_raw
            try: diff_val = int(diff_raw.replace('+', ''))
            except: diff_val = 0
        elif diff_raw.startswith('-'):
            diff_str = diff_raw
            try: diff_val = int(diff_raw)
            except: diff_val = 0
        else:
            diff_str = f"+{diff_raw}"
            try: diff_val = int(diff_raw)
            except: diff_val = 0
        return f"{w_val}kg ({diff_str})", diff_val
    m2 = re.search(r'(\d{3,4})', clean_txt)
    if m2:
        return f"{m2.group(1)}kg", 0
    return "未計量 (発走前)", 0

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

def generate_jra_race_ids_loop(year, venue_name, kai, nichi):
    v_code = VENUE_MAP.get(venue_name, "06")
    races_list = []
    for r_num in range(1, 13):
        r_id = f"{year}{v_code}{kai:02d}{nichi:02d}{r_num:02d}"
        races_list.append({
            'id': r_id,
            'name': f"📍【{venue_name} {r_num}R】",
            'venue': venue_name,
            'r_num': r_num,
            'v_code': v_code
        })
    return races_list

# ---------------------------------------------------------
# Scraping & Data Extraction Logic
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
        hw_str = "未計量 (発走前)"
        hw_diff = 0

        for td in td_list:
            cls_str = ' '.join([c.lower() for c in td.get('class', [])])
            text = td.text.strip()

            m_w = re.search(r'waku(\d)', cls_str)
            if m_w: wakaban = int(m_w.group(1))

            m_u = re.search(r'umaban(\d+)', cls_str)
            if m_u: umaban = int(m_u.group(1))

            if 'kinryo' in cls_str or 'weight' in cls_str:
                m_wt = re.search(r'(\d{2}(?:\.\d)?)', text)
                if m_wt: weight_val = float(m_wt.group(1))

            if 'odds' in cls_str or 'popular' in cls_str:
                m_o = re.search(r'(\d+\.\d+)', text)
                if m_o: odds_val = float(m_o.group(1))

            if 'ninki' in cls_str or 'pop' in cls_str:
                m_p = re.search(r'(\d+)', text)
                if m_p: pop_val = int(m_p.group(1))

            if 'weight' in cls_str or 'weight' in (td.get('id') or '').lower() or re.search(r'\d{3,4}\s*\(', text):
                hw_str, hw_diff = parse_horse_weight_str(text)

        data_list.append({
            "印": "・",
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
# AI Analysis Comment Generator Engine
# ---------------------------------------------------------
def generate_ai_analysis_comment(honmei, taikou, tanana, track_cond, pace_setting, track_bias_waku, track_bias_leg):
    comment_parts = []
    jockey_h = honmei['騎手']
    j_eval = "トップジョッキー鞍上で勝負気配良好。" if any(j in jockey_h for j in TOP_JOCKEYS_S + TOP_JOCKEYS_A) else "主戦騎手とのコンビで一発に期待。"
    w_eval = "好調な馬体重を維持。" if honmei['体重増減'] in range(-4, 5) else "当日の気配に注目。"
    
    bias_desc = f"トラックバイアス（{track_bias_waku}・{track_bias_leg}）"
    comment_parts.append(f"**【本命 ◎ {honmei['馬番']}番 {honmei['馬名']}】**\nAI指数**{honmei['AI指数']}**で最上位評価。{j_eval}{w_eval} {track_cond}馬場、{pace_setting}および{bias_desc}の好条件が揃い、軸としての信頼度は極めて高いです。")
    comment_parts.append(f"**【対抗 ◯ {taikou['馬番']}番 {taikou['馬名']} & 単穴 ▲ {tanana['馬番']}番 {tanana['馬名']}】**\n対抗の{taikou['馬名']}（{taikou['騎手']}）は勝率予測{taikou['勝率予測']}%で高次元で安定。単穴の{tanana['馬名']}は展開バイアスが向けば頭まで狙える一押しの穴馬です。")
    return "\n\n".join(comment_parts)

# ---------------------------------------------------------
# AI Prediction Engine + Track Bias System
# ---------------------------------------------------------
def calculate_ai_scores(data_list, paddock_status_map=None, track_condition="良", pace_setting="ミドルペース", track_bias_waku="フラット", track_bias_leg="フラット"):
    if not data_list: return []

    has_real_odds = any(isinstance(d['単勝オッズ'], (int, float)) for d in data_list)
    
    if not has_real_odds:
        for idx, d in enumerate(data_list):
            j_score = 10.0 if any(j in d['騎手'] for j in TOP_JOCKEYS_S) else (5.0 if any(j in d['騎手'] for j in TOP_JOCKEYS_A) else 0.0)
            w_score = max(0, 10 - (d['枠番'] * 0.5))
            est_power = 50.0 + j_score + w_score + (18 - d['馬番']) * 0.8
            d['est_power'] = est_power
        
        sorted_by_power = sorted(data_list, key=lambda x: x.get('est_power', 50.0), reverse=True)
        for rank, d in enumerate(sorted_by_power, 1):
            p_odds = round(2.0 + (rank ** 1.3) * 1.5, 1)
            d['単勝オッズ'] = p_odds
            d['人気'] = rank
            d['numeric_odds'] = p_odds
    else:
        for d in data_list:
            val = d['単勝オッズ']
            if isinstance(val, (int, float)) and val > 0:
                d['numeric_odds'] = val
            else:
                d['numeric_odds'] = 20.0

    for idx, d in enumerate(data_list):
        o_val = d.get('numeric_odds', 15.0)
        base_score = max(5.0, 100.0 - (o_val * 3.5))

        jockey = d['騎手']
        j_bonus = 0.0
        if any(j in jockey for j in TOP_JOCKEYS_S): j_bonus = 8.0
        elif any(j in jockey for j in TOP_JOCKEYS_A): j_bonus = 4.0

        w_bonus = 0.0
        diff = d.get('体重増減', 0)
        if -6 <= diff <= 4: w_bonus = 2.0
        elif diff < -10 or diff > 10: w_bonus = -3.0

        p_bonus = 0.0
        uma_num = d['馬番']
        if paddock_status_map and uma_num in paddock_status_map:
            st_val = paddock_status_map[uma_num]
            if st_val == "絶好調 (◎)": p_bonus = 12.0
            elif st_val == "好調 (◯)": p_bonus = 6.0
            elif st_val == "平行線 (▲)": p_bonus = 0.0
            elif st_val == "割引 (×)": p_bonus = -10.0

        cond_bonus = 0.0
        if track_condition in ["重", "不良"]:
            if d['枠番'] <= 3: cond_bonus += 3.0
        
        pace_bonus = 0.0
        if pace_setting == "スローペース（前残り）":
            if d['馬番'] <= 6: pace_bonus += 4.0
        elif pace_setting == "ハイペース（差し有利）":
            if d['馬番'] >= 7: pace_bonus += 4.0

        tb_waku_bonus = 0.0
        if track_bias_waku == "超内伸び (1〜3枠絶好)":
            if d['枠番'] <= 3: tb_waku_bonus = 6.0
            elif d['枠番'] >= 6: tb_waku_bonus = -4.0
        elif track_bias_waku == "内有利 (1〜4枠)":
            if d['枠番'] <= 4: tb_waku_bonus = 3.5
        elif track_bias_waku == "外有利 (6〜8枠)":
            if d['枠番'] >= 6: tb_waku_bonus = 3.5
        elif track_bias_waku == "超外伸び (外枠強烈)":
            if d['枠番'] >= 6: tb_waku_bonus = 6.0
            elif d['枠番'] <= 3: tb_waku_bonus = -4.0

        tb_leg_bonus = 0.0
        if track_bias_leg == "前残り絶対優位 (逃げ・先行)":
            if d['馬番'] <= 6: tb_leg_bonus = 5.0
        elif track_bias_leg == "外差し・追込決まる":
            if d['馬番'] >= 7: tb_leg_bonus = 5.0

        ped_bonus = round((hash(d['馬名']) % 5), 1)

        total_score = base_score + j_bonus + w_bonus + p_bonus + cond_bonus + pace_bonus + tb_waku_bonus + tb_leg_bonus + ped_bonus
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
        else: d_rank = '・'
        data_list[i]['印'] = d_rank

    return data_list

def get_race_data_by_id(clean_id, paddock_map=None, track_condition="良", pace_setting="ミドルペース", track_bias_waku="フラット", track_bias_leg="フラット"):
    if len(clean_id) != 12:
        return None, "レースIDは12桁の数字で指定してください。"

    data_list = []
    shutuba_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={clean_id}"
    soup, err = fetch_html(shutuba_url)
    if soup:
        data_list = parse_race_netkeiba(soup)

    if not data_list:
        return None, f"指定されたレースID ({clean_id}) の出馬表データを取得できませんでした。"

    odds_map = fetch_odds_data(clean_id)
    if odds_map:
        for d in data_list:
            uma = d['馬番']
            if uma in odds_map:
                d['単勝オッズ'] = odds_map[uma]['odds']
                if odds_map[uma]['pop'] != "未確定":
                    d['人気'] = odds_map[uma]['pop']

    data_list = calculate_ai_scores(data_list, paddock_status_map=paddock_map, track_condition=track_condition, pace_setting=pace_setting, track_bias_waku=track_bias_waku, track_bias_leg=track_bias_leg)
    return data_list, None

# ---------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------
if 'balance_history' not in st.session_state:
    st.session_state['balance_history'] = []
if 'sel_date_type' not in st.session_state:
    st.session_state['sel_date_type'] = 'sat'
if 'active_venue' not in st.session_state:
    st.session_state['active_venue'] = '中山'
if 'active_race_id' not in st.session_state:
    st.session_state['active_race_id'] = '202606040811'

# ---------------------------------------------------------
# MAIN APP HEADER
# ---------------------------------------------------------
st.markdown("""
<div class="main-header">
    <h1>🏇 Kuina AI Racing Pro</h1>
</div>
""", unsafe_allow_html=True)

now_jst = datetime.datetime.now(JST)
today_jst = now_jst.date()

days_to_sat = (5 - today_jst.weekday()) % 7
sat_date = today_jst + datetime.timedelta(days=days_to_sat)
sun_date = sat_date + datetime.timedelta(days=1)

# =========================================================
# 【Step 1】 レース選択 (1R〜12R昇順 & 開催競馬場選択)
# =========================================================
st.markdown('<div class="step-header">Step 1 🎯 対象レースを選択する</div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📅 今週・日付で全レース検索", "⚙️ 競馬場・条件直接指定 (JRA12桁ID)", "🔢 12桁ID直接入力"])

with tab1:
    col_day1, col_day2 = st.columns(2)
    with col_day1:
        sat_btn = st.button(f"今週土曜 ({sat_date.strftime('%m/%d')}) 開催一覧", use_container_width=True)
        if sat_btn: st.session_state['sel_date_type'] = 'sat'
    with col_day2:
        sun_btn = st.button(f"今週日曜 ({sun_date.strftime('%m/%d')}) 開催一覧", use_container_width=True)
        if sun_btn: st.session_state['sel_date_type'] = 'sun'

    active_dt = sat_date if st.session_state.get('sel_date_type') == 'sat' else sun_date
    st.markdown(f"**📍 選択中の日付: {active_dt.strftime('%Y年%m月%d日')}**")
    
    st.caption("▼ 開催競馬場を選択してください")
    all_venues_list = list(VENUE_MAP.keys())
    cur_v_index = all_venues_list.index(st.session_state.get('active_venue', '中山')) if st.session_state.get('active_venue', '中山') in all_venues_list else 5
    sel_v_name = st.selectbox("🏇 競馬場切り替え", all_venues_list, index=cur_v_index)
    st.session_state['active_venue'] = sel_v_name
    
    cur_v = st.session_state.get('active_venue', '中山')
    st.markdown(f"**🎯 {cur_v}競馬場 1R〜12R レース選択**")
    
    races_tab1 = generate_jra_race_ids_loop(active_dt.year, cur_v, 4, 8)
    
    for row_idx in range(3):
        r_cols = st.columns(4)
        for col_idx in range(4):
            r_i = row_idx * 4 + col_idx
            r = races_tab1[r_i]
            with r_cols[col_idx]:
                if st.button(f"{r['r_num']}R", key=f"tab1_r_{r['id']}", use_container_width=True):
                    st.session_state['active_race_id'] = r['id']

with tab2:
    mc1, mc2 = st.columns(2)
    with mc1:
        sel_year = st.number_input("開催年", 2020, 2026, today_jst.year)
        sel_kai = st.number_input("第何回", 1, 12, 4)
    with mc2:
        sel_venue = st.selectbox("開催競馬場", list(VENUE_MAP.keys()), index=5)
        sel_nichi = st.number_input("何日目", 1, 12, 8)

    races_list = generate_jra_race_ids_loop(sel_year, sel_venue, sel_kai, sel_nichi)
    st.caption(f"📍 対象会場: **{sel_year}年 第{sel_kai}回 {sel_venue} {sel_nichi}日目**")

    for row_idx in range(3):
        r_cols = st.columns(4)
        for col_idx in range(4):
            r_i = row_idx * 4 + col_idx
            r = races_list[r_i]
            with r_cols[col_idx]:
                if st.button(f"{r['r_num']}R", key=f"tab2_r_{r['id']}", use_container_width=True):
                    st.session_state['active_race_id'] = r['id']

with tab3:
    custom_id_input = st.text_input("12桁IDを入力 (例: 202606040811)", value="202606040811")
    if st.button("🚀 このIDで解析"):
        st.session_state['active_race_id'] = custom_id_input.strip()

target_race_id = st.session_state.get('active_race_id', '202606040811')

# =========================================================
# 【Step 2】 トラックバイアス & レース環境 & パドック設定
# =========================================================
st.markdown('<div class="step-header">Step 2 🌦 トラックバイアス（馬場傾向）& パドック補正設定</div>', unsafe_allow_html=True)

tb_col1, tb_col2 = st.columns(2)
with tb_col1:
    track_bias_waku = st.selectbox(
        "🏟️ トラックバイアス【枠順・内外】",
        ["フラット", "内有利 (1〜4枠)", "超内伸び (1〜3枠絶好)", "外有利 (6〜8枠)", "超外伸び (外枠強烈)"],
        index=0
    )
    track_cond = st.selectbox("🌦 馬場状態", ["良", "稍重", "重", "不良"], index=0)

with tb_col2:
    track_bias_leg = st.selectbox(
        "🏃 トラックバイアス【前後・脚質】",
        ["フラット", "前残り絶対優位 (逃げ・先行)", "外差し・追込決まる"],
        index=0
    )
    sel_pace = st.selectbox("⏱ 展開・ペース予想", ["ミドルペース", "スローペース（前残り）", "ハイペース（差し有利）"], index=0)

paddock_map = {}
with st.expander("🐴 直前パドック気配・状態補正チェック（タップで展開）", expanded=False):
    st.caption("パドック気配を選択すると、AI指数と推奨買い目がリアルタイム再計算されます。")
    p_col1, p_col2 = st.columns(2)
    for u_idx in range(1, 19):
        c_target = p_col1 if u_idx % 2 != 0 else p_col2
        with c_target:
            st_select = st.selectbox(f"{u_idx}番 馬気配", ["平行線 (▲)", "絶好調 (◎)", "好調 (◯)", "割引 (×)"], key=f"pad_{u_idx}")
            paddock_map[u_idx] = st_select

# =========================================================
# 【Step 3】 AI解析結果 (最左にAI印を配置 & 出馬表 & AIコメント)
# =========================================================
st.markdown(f'<div class="step-header">Step 3 📊 AI解析結果 (対象レースID: {target_race_id})</div>', unsafe_allow_html=True)

with st.spinner("出馬表・馬体重・オッズ・トラックバイアスを計算中..."):
    data_list, err = get_race_data_by_id(
        target_race_id,
        paddock_map=paddock_map,
        track_condition=track_cond,
        pace_setting=sel_pace,
        track_bias_waku=track_bias_waku,
        track_bias_leg=track_bias_leg
    )

if err:
    st.error(err)
elif data_list:
    df = pd.DataFrame(data_list)
    cols_order = ["印", "枠番", "馬番", "馬名", "AI指数", "勝率予測", "単勝オッズ", "人気", "騎手", "斤量", "馬体重", "体重増減"]
    df = df[[c for c in cols_order if c in df.columns]]

    st.success(f"✅ {len(data_list)}頭のデータ（AI印・馬名・騎手・斤量・馬体重・単勝オッズ・人気）を取得完了しました。")

    honmei = next((d for d in data_list if d['印'] == '◎'), data_list[0])
    taikou = next((d for d in data_list if d['印'] == '◯'), data_list[1] if len(data_list)>1 else data_list[0])
    tanana = next((d for d in data_list if d['印'] == '▲'), data_list[2] if len(data_list)>2 else data_list[0])

    # 上位評価カード
    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(f"""
        <div class="card-clean card-honmei">
            <span class="badge-honmei">本命 ◎</span>
            <div class="horse-title">{honmei['馬番']}番 {honmei['馬名']}</div>
            <div class="stat-row">🏇 騎手: {honmei['騎手']} ({honmei['斤量']}kg)</div>
            <div class="stat-row">💰 単勝オッズ: {honmei['単勝オッズ']}倍 ({honmei['人気']}人気)</div>
            <div class="stat-row">⚖️ 馬体重: {honmei['馬体重']}</div>
            <div class="stat-row">🚀 AI指数: <b>{honmei['AI指数']}</b> (勝率 {honmei['勝率予測']}%)</div>
        </div>
        """, unsafe_allow_html=True)
    with m2:
        st.markdown(f"""
        <div class="card-clean card-taikou">
            <span class="badge-taikou">対抗 ◯</span>
            <div class="horse-title">{taikou['馬番']}番 {taikou['馬名']}</div>
            <div class="stat-row">🏇 騎手: {taikou['騎手']} ({taikou['斤量']}kg)</div>
            <div class="stat-row">💰 単勝オッズ: {taikou['単勝オッズ']}倍 ({taikou['人気']}人気)</div>
            <div class="stat-row">⚖️ 馬体重: {taikou['馬体重']}</div>
            <div class="stat-row">🚀 AI指数: <b>{taikou['AI指数']}</b> (勝率 {taikou['勝率予測']}%)</div>
        </div>
        """, unsafe_allow_html=True)
    with m3:
        st.markdown(f"""
        <div class="card-clean card-tanana">
            <span class="badge-tanana">単穴 ▲</span>
            <div class="horse-title">{tanana['馬番']}番 {tanana['馬名']}</div>
            <div class="stat-row">🏇 騎手: {tanana['騎手']} ({tanana['斤量']}kg)</div>
            <div class="stat-row">💰 単勝オッズ: {tanana['単勝オッズ']}倍 ({tanana['人気']}人気)</div>
            <div class="stat-row">⚖️ 馬体重: {tanana['馬体重']}</div>
            <div class="stat-row">🚀 AI指数: <b>{tanana['AI指数']}</b> (勝率 {tanana['勝率予測']}%)</div>
        </div>
        """, unsafe_allow_html=True)

    # AI展開・バイアス分析見解ボックス
    ai_comment_text = generate_ai_analysis_comment(honmei, taikou, tanana, track_cond, sel_pace, track_bias_waku, track_bias_leg)
    st.markdown(f"""
    <div class="ai-box">
        <div style="font-weight: 800; font-size: 1.1rem; margin-bottom: 6px;">🧠 AIトラックバイアス・展開総合分析コメント</div>
        {ai_comment_text}
    </div>
    """, unsafe_allow_html=True)

    # 数値データの小数点第一位（例: 12.3）丸め処理
    for col in ["AI指数", "勝率予測", "単勝オッズ", "斤量"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            df[col] = df[col].apply(lambda x: round(float(x), 1) if isinstance(x, (int, float, np.number)) and not pd.isna(x) else x)

    # 全出馬表 (一番左が「印」)
    st.markdown("#### 📋 全出馬表 & AI予想一覧 (一番左列がAI印◎◯▲)")
    
    def highlight_marks(val):
        if val == '◎': return 'background-color: #fca5a5; color: #991b1b; font-weight: bold;'
        elif val == '◯': return 'background-color: #6ee7b7; color: #065f46; font-weight: bold;'
        elif val == '▲': return 'background-color: #93c5fd; color: #1e40af; font-weight: bold;'
        elif val == '☆': return 'background-color: #fef08a; color: #854d0e; font-weight: bold;'
        elif val == '△': return 'background-color: #e2e8f0; color: #334155;'
        return ''

    # 小数点第一位で統一フォーマット表示
    fmt_dict = {c: "{:.1f}" for c in ["AI指数", "勝率予測", "単勝オッズ", "斤量"] if c in df.columns}
    st.dataframe(df.style.map(highlight_marks, subset=['印']).format(fmt_dict), use_container_width=True)
    
    csv_data = df.to_csv(index=False, encoding='utf-8-sig')
    st.download_button(
        label="📥 この予想結果をCSVファイルでダウンロード",
        data=csv_data,
        file_name=f"ai_prediction_{target_race_id}.csv",
        mime="text/csv",
        use_container_width=True
    )

    # =========================================================
    # 【Step 4】 本格馬券 複数選択＆資金配分シミュレーター
    # =========================================================
    st.markdown('<div class="step-header">Step 4 🎰 本格馬券 複数選択＆資金配分シミュレーター</div>', unsafe_allow_html=True)
    
    sim_col1, sim_col2 = st.columns(2)
    with sim_col1:
        selected_tickets = st.multiselect(
            "🎫 購入する勝馬投票券タイプ（複数選択可能）",
            ALL_TICKET_TYPES,
            default=["馬連", "3連複"]
        )
        budget = st.number_input("💰 総購入予算 (円)", min_value=1000, value=10000, step=1000)
    
    with sim_col2:
        odds_h = float(honmei.get('numeric_odds', 3.0))
        odds_t = float(taikou.get('numeric_odds', 5.0))
        odds_a = float(tanana.get('numeric_odds', 8.0))
        
        synth_inv = (1/odds_h) + (1/odds_t) + (1/odds_a)
        synth_odds = round(1 / synth_inv, 1) if synth_inv > 0 else 1.5
        
        selected_str = "、".join(selected_tickets) if selected_tickets else "選択なし"
        num_tickets = len(selected_tickets) if selected_tickets else 1
        alloc_per_ticket = max(100, int(budget / (num_tickets * 3)))

        st.markdown(f"""
        **🎯 選択中の馬券タイプ: `{selected_str}`**
        * 本命-対抗軸: **{honmei['馬番']} - {taikou['馬番']}**
        * 本命-単穴軸: **{honmei['馬番']} - {tanana['馬番']}**
        * 対抗-単穴軸: **{taikou['馬番']} - {tanana['馬番']}**
        
        **📊 単勝換算 合成オッズ: `{synth_odds} 倍`**  
        **💰 1点あたりの推奨投入額:** `{alloc_per_ticket:,} 円`（均等資金配分）
        """, unsafe_allow_html=True)

    # 収支記録フォーム
    st.markdown("#### 📝 このレースの成績・結果を収支管理に追加")
    with st.form("balance_form_step4"):
        f1, f2 = st.columns(2)
        with f1:
            rec_bet = st.number_input("実際の投資額 (円)", min_value=0, value=budget, step=100)
        with f2:
            rec_return = st.number_input("実際の払戻額 (円)", min_value=0, value=0, step=100)
        btn_add = st.form_submit_button("📝 トータル収支履歴に記録")
        if btn_add:
            st.session_state['balance_history'].append({
                "レース": f"{target_race_id}",
                "投資": rec_bet,
                "回収": rec_return,
                "収支": rec_return - rec_bet
            })
            st.success("収支履歴に記録しました！")

if st.session_state['balance_history']:
    st.markdown("#### 📜 累計収支サマリー")
    df_bal = pd.DataFrame(st.session_state['balance_history'])
    tot_bet = df_bal["投資"].sum()
    tot_ret = df_bal["回収"].sum()
    tot_profit = tot_ret - tot_bet
    ret_rate = round((tot_ret / tot_bet) * 100, 1) if tot_bet > 0 else 0.0

    s1, s2, s3 = st.columns(3)
    with s1: st.metric("累計投資額", f"{tot_bet:,} 円")
    with s2: st.metric("累計払戻額", f"{tot_ret:,} 円", delta=f"{tot_profit:,} 円")
    with s3: st.metric("累計回収率", f"{ret_rate} %")

    if st.button("🗑️ 収支履歴をリセット"):
        st.session_state['balance_history'] = []
        st.rerun()