import re
import requests
from bs4 import BeautifulSoup
import urllib3
import streamlit as st
import datetime
JST = datetime.timezone(datetime.timedelta(hours=9))
import pandas as pd
import numpy as np

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Kuina AI Racing Pro V14.0 - Auto Race ID Rule Engine
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

VENUE_MAP = {
    "中山": "06", "阪神": "09", "中京": "07", "東京": "05",
    "京都": "08", "新潟": "04", "福島": "03", "小倉": "10",
    "札幌": "01", "函館": "02"
}
VENUE_CODE_TO_NAME = {v: k for k, v in VENUE_MAP.items()}

TOP_JOCKEYS_S = ["ルメール", "川田", "武豊", "坂井", "横山武", "戸崎", "モレイラ", "レーン"]
TOP_JOCKEYS_A = ["松山", "鮫島克", "岩田望", "西村淳", "菅原明", "津村", "田辺", "デムーロ", "丹内"]

st.set_page_config(
    page_title="Kuina AI Racing Pro",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    .stApp { background-color: #f8fafc; color: #0f172a; font-family: 'Inter', sans-serif; }
    .hero-title { font-size: 2.2rem; font-weight: 800; color: #1e3a8a; margin-bottom: 1.2rem; }
    .horse-card { background: #ffffff; border-radius: 16px; padding: 20px; border: 1px solid #e2e8f0; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 16px; }
    .card-honmei { border-left: 6px solid #dc2626; background: #fff5f5; }
    .card-taikou { border-left: 6px solid #059669; background: #f0fdf4; }
    .card-tanana { border-left: 6px solid #2563eb; background: #eff6ff; }
    .badge-honmei { background: #dc2626; color: #ffffff; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 0.85rem; }
    .badge-taikou { background: #059669; color: #ffffff; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 0.85rem; }
    .badge-tanana { background: #2563eb; color: #ffffff; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 0.85rem; }
    .horse-name-title { font-size: 1.4rem; font-weight: 800; color: #0f172a; margin: 10px 0 6px 0; }
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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36',
        'Referer': 'https://race.netkeiba.com/'
    }
    try:
        session = requests.Session()
        session.headers.update(headers)
        res = session.get(url, verify=False, timeout=12)
        if res.status_code != 200: return None, f"Status {res.status_code}"
        html_text = None
        for enc in ['euc-jp', 'cp932', 'utf-8']:
            try:
                html_text = res.content.decode(enc)
                if 'netkeiba' in html_text or '馬名' in html_text or '出馬' in html_text: break
            except Exception: continue
        if not html_text: html_text = res.content.decode('euc-jp', errors='replace')
        return BeautifulSoup(html_text, 'html.parser'), None
    except Exception as e:
        return None, str(e)

def generate_venue_all_races(year, venue_name, kai, nichi):
    """AI側で12桁レースID法則（YYYY + VenueCode + Kai + Nichi + RaceNum）から1R〜12Rを全自動生成"""
    v_code = VENUE_MAP.get(venue_name, "06")
    races = []
    for r in range(1, 13):
        r_id = f"{year}{v_code}{kai:02d}{nichi:02d}{r:02d}"
        races.append({
            'id': r_id,
            'name': f"📍【{venue_name} {r}R】 (ID: {r_id})",
            'venue': venue_name,
            'r_num': r
        })
    return races

def parse_race_netkeiba(soup):
    rows = soup.select('tr.HorseList') or soup.select('table.ShutubaTable tr') or soup.select('table.Shutuba_Table tr')
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

        wakaban, umaban, odds_val, pop_val = None, None, None, None
        weight_val, hw_str, hw_diff = 55.0, "計不", 0

        for td in td_list:
            cls_str = ' '.join([c.lower() for c in td.get('class', [])])
            text = td.text.strip()

            m_w = re.search(r'waku(\d)', cls_str)
            if m_w: wakaban = int(m_w.group(1))

            m_u = re.search(r'umaban(\d+)', cls_str)
            if m_u: umaban = int(m_u.group(1))

            m_wt = re.search(r'^(4\d|5\d|6\d)(?:\.\d)?$', text)
            if m_wt:
                try: weight_val = float(m_wt.group(0))
                except ValueError: pass

            if 'odds' in cls_str:
                m_o = re.search(r'(\d+\.\d+)', text)
                if m_o:
                    try: odds_val = float(m_o.group(1))
                    except ValueError: pass

            if 'popular' in cls_str or 'pop' in cls_str:
                m_p = re.search(r'(\d+)', text)
                if m_p:
                    try: pop_val = int(m_p.group(1))
                    except ValueError: pass

            if 'weight' in cls_str or re.search(r'\d{3,4}\s*\(', text):
                p_str, p_diff = parse_horse_weight_str(text)
                if p_str != "計不": hw_str, hw_diff = p_str, p_diff

        if umaban is None and len(td_list) > 1:
            txt = td_list[1].text.strip()
            if txt.isdigit(): umaban = int(txt)
        if umaban is None: umaban = idx
        if wakaban is None: wakaban = (umaban - 1) // 2 + 1 if umaban <= 16 else 8

        data_list.append({
            '枠番': wakaban, '馬番': umaban, '馬名': horse_name,
            '騎手': jockey_name, '斤量': weight_val,
            '単勝オッズ': odds_val if odds_val is not None else "未確定",
            '人気': pop_val if pop_val is not None else "未確定",
            '馬体重': hw_str, '体重増減': hw_diff
        })

    return data_list

def fetch_odds_data(clean_id):
    odds_url = f"https://race.netkeiba.com/odds/index.html?type=b1&race_id={clean_id}"
    soup, _ = fetch_html(odds_url)
    if not soup: return {}
    odds_map = {}
    for table in soup.find_all('table'):
        for r in table.find_all('tr'):
            tds = r.find_all(['td', 'th'])
            if len(tds) >= 4:
                uma_txt = tds[1].text.strip() if len(tds) > 1 else tds[0].text.strip()
                odds_txt = tds[-2].text.strip()
                pop_txt = tds[-1].text.strip()
                m_uma = re.search(r'(\d+)', uma_txt)
                m_odds = re.search(r'(\d+\.\d+|\d+)', odds_txt)
                m_pop = re.search(r'(\d+)', pop_txt)
                if m_uma and m_odds:
                    try:
                        uma = int(m_uma.group(1))
                        odds_map[uma] = {
                            'odds': float(m_odds.group(1)),
                            'pop': int(m_pop.group(1)) if m_pop else "未確定"
                        }
                    except ValueError: pass
    return odds_map

def calculate_ai_scores(data_list, paddock_status_map=None, race_env=None):
    if not data_list: return data_list
    if paddock_status_map is None: paddock_status_map = {}
    if race_env is None:
        race_env = {'weather': '晴', 'condition': '良', 'bias': '⚪ フラット', 'pace': 'ミドルペース'}

    scored_items = []
    for d in data_list:
        try: o_val = float(d.get('単勝オッズ'))
        except (ValueError, TypeError): o_val = 20.0
        try: p_val = float(d.get('人気'))
        except (ValueError, TypeError): p_val = 8.0

        weight = d.get('斤量', 55.0)
        hw_diff = d.get('体重増減', 0)
        uma = d.get('馬番')
        waku = d.get('枠番', 1)
        jockey = d.get('騎手', '')
        horse_name = d.get('馬名', '')

        pop_score = max(0, 40 - (p_val - 1) * 3.5)
        odds_score = max(0, 30 - (o_val * 0.6))
        weight_bonus = max(0, (56.0 - weight) * 2)

        j_score = 7.0 if any(tj in jockey for tj in TOP_JOCKEYS_S) else (4.0 if any(tj in jockey for tj in TOP_JOCKEYS_A) else 1.0)
        p_status = paddock_status_map.get(uma, "⚪ 普通 (0pt)")
        paddock_score = 7.0 if "✨ 絶好調" in p_status else (-4.0 if "⚠️ 太め残り" in p_status else 0.0)

        raw_score = pop_score + odds_score + weight_bonus + j_score + paddock_score + 10
        score = round(min(99.9, max(10.0, raw_score)), 1)

        d_copy = dict(d)
        d_copy['_raw_score'] = score
        d_copy['パドック評価'] = p_status
        scored_items.append(d_copy)

    scored_items.sort(key=lambda x: x['_raw_score'], reverse=True)
    mark_list = ['◎ 本命', '◯ 対抗', '▲ 単穴', '△ 連下', '△ 連下', '☆ 穴馬']
    for idx, item in enumerate(scored_items):
        item['予想印'] = mark_list[idx] if idx < len(mark_list) else 'ー'
        item['AI予想スコア'] = item['_raw_score']
    return scored_items

def get_race_data(clean_id, paddock_status_map=None, race_env=None):
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={clean_id}"
    soup, err = fetch_html(url)
    data_list = []
    if soup:
        data_list = parse_race_netkeiba(soup)
    if not data_list:
        return None, f"出馬表が見つかりません (Race ID: {clean_id})。開催日・レース番号をお確かめください。"

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

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# UI Header & Core Engine
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

st.markdown('<div class="hero-title">🏇 Kuina AI Racing Pro (12桁ID法則・ダイレクト自動生成エンジン)</div>', unsafe_allow_html=True)

if 'active_race_id' not in st.session_state:
    st.session_state['active_race_id'] = None

now_jst = datetime.datetime.now(JST)
today_year = now_jst.year

st.markdown("### 🧠 AI法則生成：開催場所と日程を選ぶだけで全12レースを一括生成")

col1, col2, col3, col4 = st.columns(4)
with col1:
    sel_venue = st.selectbox("📍 競馬場 (JRA全10場)", list(VENUE_MAP.keys()), index=5)  # デフォルト中山
with col2:
    sel_kai = st.number_input("回 (例: 4回中山)", 1, 10, 4)
with col3:
    sel_nichi = st.number_input("日目 (例: 7日目/8日目)", 1, 12, 7)
with col4:
    sel_year = st.number_input("年", 2020, 2026, today_year)

st.markdown("---")

# AI側で12桁法則に従い 1R〜12R の全レースリストを自動算出
generated_races = generate_venue_all_races(sel_year, sel_venue, sel_kai, sel_nichi)

col_r1, col_r2 = st.columns([2, 1])

with col_r1:
    race_options = {r['name']: r['id'] for r in generated_races}
    selected_race_name = st.selectbox("🎯 レースを選択してください (1R〜12R 全網羅):", list(race_options.keys()))
    current_selected_id = race_options[selected_race_name]

with col_r2:
    st.write("")
    st.write("")
    if st.button("🚀 AI出馬表解析を実行", use_container_width=True):
        st.session_state['active_race_id'] = current_selected_id

st.markdown("#### ⚡ 今週末の主要レース ダイレクトボタン")
b_col1, b_col2, b_col3, b_col4 = st.columns(4)
with b_col1:
    if st.button("📍 中山11R (オールカマー)", use_container_width=True):
        st.session_state['active_race_id'] = f"{sel_year}06040711"
with b_col2:
    if st.button("📍 阪神11R (神戸新聞杯)", use_container_width=True):
        st.session_state['active_race_id'] = f"{sel_year}09040111"
with b_col3:
    if st.button("📍 中京11R", use_container_width=True):
        st.session_state['active_race_id'] = f"{sel_year}07030711"
with b_col4:
    if st.button("📍 中山1R (朝イチ)", use_container_width=True):
        st.session_state['active_race_id'] = f"{sel_year}06040701"

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Analysis Results Section
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

target_race_id = st.session_state.get('active_race_id')

if target_race_id:
    st.markdown("---")
    st.success(f"分析対象レースID: ")

    if 'paddock_map' not in st.session_state:
        st.session_state['paddock_map'] = {}

    data, err = get_race_data(target_race_id, st.session_state['paddock_map'])

    if err:
        st.error(err)
    elif data:
        df_display = pd.DataFrame(data)[['予想印', '枠番', '馬番', '馬名', '騎手', '斤量', '単勝オッズ', '人気', 'AI予想スコア']]
        st.subheader("📊 AI予想出馬表・スコア一覧")
        st.dataframe(df_display, use_container_width=True)

        st.subheader("🏆 AI本命・対抗・単穴カード")
        card_cols = st.columns(3)
        top3 = data[:3]
        badges = [('badge-honmei', 'card-honmei'), ('badge-taikou', 'card-taikou'), ('badge-tanana', 'card-tanana')]

        for idx, horse in enumerate(top3):
            badge_cls, card_cls = badges[idx]
            with card_cols[idx]:
                st.markdown(f"""
                <div class="horse-card {card_cls}">
                    <span class="{badge_cls}">{horse['予想印']}</span>
                    <div class="horse-name-title">{horse['馬番']}番 {horse['馬名']}</div>
                    <p style="color: #475569; margin-bottom: 4px;"><b>鞍上:</b> {horse['騎手']} ({horse['斤量']}kg)</p>
                    <p style="color: #475569; margin-bottom: 4px;"><b>単勝オッズ:</b> {horse['単勝オッズ']}倍 ({horse['人気']}人気)</p>
                    <p style="color: #1e3a8a; font-weight: 800; font-size: 1.2rem;">AIスコア: {horse['AI予想スコア']} pt</p>
                </div>
                """, unsafe_allow_html=True)