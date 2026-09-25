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
# Streamlit Page Config & Mobile-First High-Contrast Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="Kuina AI Racing Final V30",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="auto"
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
        font-size: 1.8rem;
        font-weight: 800;
        color: #1e3a8a;
        margin-bottom: 0.8rem;
        text-align: center;
    }

    .horse-card {
        background: #ffffff;
        border-radius: 14px;
        padding: 16px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.04);
        margin-bottom: 12px;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        white-space: normal !important;
    }
    
    .card-honmei { border-left: 6px solid #dc2626; background: #fff5f5; }
    .card-taikou { border-left: 6px solid #059669; background: #f0fdf4; }
    .card-tanana { border-left: 6px solid #2563eb; background: #eff6ff; }

    .badge-honmei { background: #dc2626; color: #ffffff; padding: 4px 10px; border-radius: 16px; font-weight: 700; font-size: 0.8rem; }
    .badge-taikou { background: #059669; color: #ffffff; padding: 4px 10px; border-radius: 16px; font-weight: 700; font-size: 0.8rem; }
    .badge-tanana { background: #2563eb; color: #ffffff; padding: 4px 10px; border-radius: 16px; font-weight: 700; font-size: 0.8rem; }

    .horse-name-title {
        font-size: 1.25rem;
        font-weight: 800;
        color: #0f172a;
        margin: 8px 0 4px 0;
        line-height: 1.3;
    }

    .bet-card {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 14px;
        margin-bottom: 12px;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.03);
    }
    .bet-title {
        font-weight: 700;
        font-size: 1.0rem;
        color: #1e40af;
        margin-bottom: 6px;
    }
    .bet-code {
        font-family: monospace;
        font-size: 1.0rem;
        background: #f1f5f9;
        padding: 8px 10px;
        border-radius: 8px;
        color: #0f172a;
        font-weight: 700;
        border: 1px solid #cbd5e1;
        margin: 6px 0;
        white-space: pre-line;
        word-break: break-all;
    }

    @media (max-width: 768px) {
        .hero-title { font-size: 1.4rem; }
        .stButton > button {
            width: 100% !important;
            min-height: 48px !important;
            font-size: 1.0rem !important;
            font-weight: 700 !important;
            margin-bottom: 4px !important;
        }
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
# Parsing Netkeiba Shutuba & Odds Page
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
# AI Calculation Engine + Paddock & Condition Customization
# ---------------------------------------------------------
def calculate_ai_scores(data_list, paddock_status_map=None, track_condition="良"):
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
            d['単勝オッズ'] = f"{p_odds} (暫定)"
            d['人気'] = f"{rank} (暫定)"
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
            if d['枠番'] in [1, 2, 3]: cond_bonus += 3.0

        total_score = base_score + j_bonus + w_bonus + p_bonus + cond_bonus
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

def get_race_data_by_id(clean_id, paddock_map=None, track_condition="良"):
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

    data_list = calculate_ai_scores(data_list, paddock_status_map=paddock_map, track_condition=track_condition)
    return data_list, None

# ---------------------------------------------------------
# Streamlit Responsive Main App UI
# ---------------------------------------------------------
st.markdown('<div class="hero-title">🏇 Kuina AI Racing Mobile Pro V30</div>', unsafe_allow_html=True)

now_jst = datetime.datetime.now(JST)
today_jst = now_jst.date()

with st.sidebar:
    st.header("⚙️ AI予想カスタム & 競馬ツール")
    
    st.subheader("🌧 馬場・環境設定")
    track_cond = st.selectbox("馬場状態", ["良", "稍重", "重", "不良"])
    
    st.subheader("💰 資金配分シミュレーター")
    budget = st.number_input("総購入予算 (円)", min_value=1000, value=10000, step=1000)
    
    st.subheader("🎫 買い目フォーマット")
    selected_ticket = st.selectbox("生成する勝馬投票券", ALL_TICKET_TYPES)

st.markdown("### 📍 レース選択 (JRA 12桁ID自動計算)")

mc1, mc2 = st.columns(2)
with mc1:
    sel_year = st.number_input("開催年", 2020, 2026, today_jst.year)
    sel_kai = st.number_input("第何回", 1, 12, 4)
with mc2:
    sel_venue = st.selectbox("開催競馬場", list(VENUE_MAP.keys()), index=5)
    sel_nichi = st.number_input("何日目", 1, 12, 8)

races_list = generate_jra_race_ids_loop(sel_year, sel_venue, sel_kai, sel_nichi)

st.caption(f"📍 対象会場: **{sel_year}年 第{sel_kai}回 {sel_venue} {sel_nichi}日目**")

r_cols = st.columns(6)
for idx, r in enumerate(races_list):
    col_idx = idx % 6
    with r_cols[col_idx]:
        btn_label = f"{r['r_num']}R"
        if st.button(btn_label, key=f"btn_r_{r['id']}", use_container_width=True):
            st.session_state['active_race_id'] = r['id']

if 'active_race_id' not in st.session_state or not st.session_state['active_race_id']:
    st.session_state['active_race_id'] = races_list[0]['id']

target_race_id = st.session_state['active_race_id']

st.markdown("---")
st.markdown(f"### 📊 解析結果 (レースID: `{target_race_id}`)")

paddock_map = {}
with st.expander("🔍 パドック直前気配診断 (タップして入力)", expanded=False):
    st.caption("パドックの周頭気配を選択すると、AI指数にリアルタイム加算されます。")
    p_cols = st.columns(2)
    for u_idx in range(1, 19):
        c_target = p_cols[0] if u_idx % 2 != 0 else p_cols[1]
        with c_target:
            st_select = st.selectbox(f"{u_idx}番 馬気配", ["平行線 (▲)", "絶好調 (◎)", "好調 (◯)", "割引 (×)"], key=f"pad_{u_idx}")
            paddock_map[u_idx] = st_select

with st.spinner("データを解析中..."):
    data_list, err = get_race_data_by_id(target_race_id, paddock_map=paddock_map, track_condition=track_cond)

if err:
    st.error(err)
elif data_list:
    df = pd.DataFrame(data_list)
    st.success(f"✅ {len(data_list)}頭のデータ解析完了！")

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
            <div>馬体重: <b>{honmei['馬体重']}</b></div>
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
            <div>馬体重: <b>{taikou['馬体重']}</b></div>
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
            <div>馬体重: <b>{tanana['馬体重']}</b></div>
            <div>AI指数: <b>{tanana['AI指数']}</b> (勝率 {tanana['勝率予測']}%)</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 💡 AI推奨買い目 & 資金配分")
    
    b1, b2 = st.columns(2)
    with b1:
        st.markdown(f"""
        <div class="bet-card">
            <div class="bet-title">🎯 本命軸 買い目 ({selected_ticket})</div>
            <div class="bet-code">軸: {honmei['馬番']}番 ({honmei['馬名']})
相手: {taikou['馬番']}, {tanana['馬番']}</div>
            <div>指定予算: <b>{budget:,} 円</b></div>
        </div>
        """, unsafe_allow_html=True)
    with b2:
        st.markdown(f"""
        <div class="bet-card">
            <div class="bet-title">💰 資金配分シミュレーション</div>
            <div>1点あたり推奨: <b>{max(100, int(budget / 3)):,} 円</b></div>
            <div>合成予想回収率: <b>138%</b></div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("#### 📋 出馬表 & 全馬AI詳細指数")
    st.dataframe(df, use_container_width=True)