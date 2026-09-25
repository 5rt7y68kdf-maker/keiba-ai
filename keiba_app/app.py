import re
import requests
from bs4 import BeautifulSoup
import urllib3
import streamlit as st
import datetime
JST = datetime.timezone(datetime.timedelta(hours=9))
import pandas as pd
import numpy as np

# SSL証明書警告の非表示化
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# JRA全国10競馬場コード
VENUE_MAP = {
    "札幌": "01", "函館": "02", "福島": "03", "新潟": "04",
    "東京": "05", "中山": "06", "中京": "07", "京都": "08",
    "阪神": "09", "小倉": "10"
}
VENUE_CODE_TO_NAME = {v: k for k, v in VENUE_MAP.items()}

TOP_JOCKEYS_S = ["ルメール", "川田", "武豊", "坂井", "横山武", "戸崎", "モレイラ", "レーン"]
TOP_JOCKEYS_A = ["松山", "鮫島克", "岩田望", "西村淳", "菅原明", "津村", "田辺", "デムーロ", "丹内"]

# ---------------------------------------------------------
# Streamlit Page Config & Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="Kuina AI Racing Pro - JRAダイレクト",
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
    }
    .horse-card {
        background: #ffffff;
        border-radius: 14px;
        padding: 16px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.04);
        margin-bottom: 12px;
    }
    .card-honmei { border-left: 6px solid #dc2626; background: #fff5f5; }
    .card-taikou { border-left: 6px solid #059669; background: #f0fdf4; }
    .card-tanana { border-left: 6px solid #2563eb; background: #eff6ff; }
    .badge-honmei { background: #dc2626; color: #fff; padding: 4px 10px; border-radius: 12px; font-weight: 700; }
    .badge-taikou { background: #059669; color: #fff; padding: 4px 10px; border-radius: 12px; font-weight: 700; }
    .badge-tanana { background: #2563eb; color: #fff; padding: 4px 10px; border-radius: 12px; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Data Fetcher (Sidebar Completely Bypassed)
# ---------------------------------------------------------
def fetch_html(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        res = requests.get(url, headers=headers, timeout=10, verify=False)
        res.encoding = res.apparent_encoding or 'euc-jp'
        soup = BeautifulSoup(res.text, 'html.parser')
        # サイドバー・ヘッダー・注目枠などのノイズタグを完全削除（サイドバー完全回避）
        for tag in soup.select('#SideBar, .PickupRace, .Orepro, #Header, .Header, .Header_Inner, #Footer'):
            tag.decompose()
        return soup, None
    except Exception as e:
        return None, f"通信エラー: {e}"

def parse_horse_weight_str(txt):
    if not txt: return "計不", 0
    clean_txt = str(txt).strip().replace(' ', '')
    m = re.search(r'(\\d{3,4})\\s*\\(?([+-]?\\d+)?\\)?', clean_txt)
    if m:
        w_val = m.group(1)
        diff_val = int(m.group(2)) if m.group(2) else 0
        return f"{w_val}kg", diff_val
    return "計不", 0

def parse_race_netkeiba(soup):
    # メインコンテンツエリアのみを抽出
    main_area = soup.select_one('div.RaceList_Body') or soup.select_one('table.Shutuba_Table') or soup.select_one('div#main') or soup
    rows = main_area.select('tr.HorseList') or main_area.select('table.ShutubaTable tr') or main_area.select('table.Shutuba_Table tr')
    if not rows:
        all_trs = main_area.find_all('tr')
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

            m_w = re.search(r'waku(\\d)', cls_str)
            if m_w: wakaban = int(m_w.group(1))

            m_u = re.search(r'umaban(\\d+)', cls_str)
            if m_u: umaban = int(m_u.group(1))

            m_wt = re.search(r'^(4\\d|5\\d|6\\d)(?:\\.\\d)?$', text)
            if m_wt:
                try: weight_val = float(m_wt.group(0))
                except ValueError: pass

            if 'odds' in cls_str:
                m_o = re.search(r'(\\d+\\.\\d+)', text)
                if m_o:
                    try: odds_val = float(m_o.group(1))
                    except ValueError: pass

            if 'popular' in cls_str or 'pop' in cls_str:
                m_p = re.search(r'(\\d+)', text)
                if m_p:
                    try: pop_val = int(m_p.group(1))
                    except ValueError: pass

            if 'weight' in cls_str or re.search(r'\\d{3,4}\\s*\\(', text):
                p_str, p_diff = parse_horse_weight_str(text)
                if p_str != "計不":
                    hw_str = p_str
                    hw_diff = p_diff

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

def parse_db_netkeiba(soup):
    main_area = soup.select_one('div#main') or soup
    table = main_area.select_one('table.race_table_01')
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

    rows = table.find_all('tr')[1:]
    data_list = []
    for r in rows:
        tds = r.find_all('td')
        if len(tds) < 5: continue

        horse_a = r.select_one('a[href*="/horse/"]')
        if not horse_a: continue
        horse_name = horse_a.text.strip()
        if not horse_name: continue

        jockey_a = r.select_one('a[href*="/jockey/"]')
        jockey_name = jockey_a.text.strip() if jockey_a else "未定義"

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
            m = re.search(r'(\\d+\\.?\\d*)', txt)
            if m: weight_val = float(m.group(1))

        odds_val = "未確定"
        o_idx = col_map.get('odds')
        if o_idx is not None and o_idx < len(tds):
            txt = tds[o_idx].text.strip()
            m = re.search(r'(\\d+\\.\\d+|\\d+)', txt)
            if m: odds_val = float(m.group(1))

        pop_val = "未確定"
        p_idx = col_map.get('pop')
        if p_idx is not None and p_idx < len(tds):
            txt = tds[p_idx].text.strip()
            m = re.search(r'(\\d+)', txt)
            if m: pop_val = int(m.group(1))

        hw_str = "計不"
        hw_diff = 0
        hw_idx = col_map.get('horse_weight')
        if hw_idx is not None and hw_idx < len(tds):
            txt = tds[hw_idx].text.strip()
            hw_str, hw_diff = parse_horse_weight_str(txt)

        data_list.append({
            '枠番': wakaban, '馬番': umaban, '馬名': horse_name,
            '騎手': jockey_name,
            '斤量': weight_val, '単勝オッズ': odds_val, '人気': pop_val,
            '馬体重': hw_str, '体重増減': hw_diff
        })

    return data_list

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
        uma = d.get('馬番')
        jockey = d.get('騎手', '')

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

        base_score = pop_score + odds_score + weight_bonus + j_score
        p_status = paddock_status_map.get(uma, "⚪ 普通")
        p_bonus = 0
        if "🔥" in p_status: p_bonus = 8.0
        elif "✨" in p_status: p_bonus = 4.0
        elif "⚠️" in p_status: p_bonus = -6.0

        final_score = base_score + p_bonus
        scored_items.append((final_score, d, j_comment, p_status))

    scored_items.sort(key=lambda x: x[0], reverse=True)
    results = []
    for idx, (score, d, j_comm, p_stat) in enumerate(scored_items):
        mark = "注"
        if idx == 0: mark = "◎"
        elif idx == 1: mark = "◯"
        elif idx == 2: mark = "▲"
        elif idx == 3: mark = "△"

        d['印'] = mark
        d['AI指数'] = round(score, 1)
        d['騎手評価'] = j_comm
        d['パドック気配'] = p_stat
        results.append(d)

    return results

def get_race_data_by_id(clean_id, paddock_status_map=None, race_env=None):
    if len(clean_id) != 12:
        return None, "レースIDは12桁の数字で指定してください。"

    data_list = []
    errors = []

    # 直接出馬表ページへ接続 (サイドバー不使用)
    race_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={clean_id}"
    soup, err = fetch_html(race_url)
    if soup:
        data_list = parse_race_netkeiba(soup)
    elif err:
        errors.append(err)

    if not data_list:
        db_url = f"https://db.netkeiba.com/race/{clean_id}/"
        soup, err = fetch_html(db_url)
        if soup:
            data_list = parse_db_netkeiba(soup)
        elif err:
            errors.append(err)

    if not data_list:
        return None, f"レースデータが見つかりませんでした (試行ID: {clean_id})"

    data_list = calculate_ai_scores(data_list, paddock_status_map, race_env)
    return data_list, None

# ---------------------------------------------------------
# UI Component - 12桁IDダイレクトアクセス & 完全サイドバー回避
# ---------------------------------------------------------
st.markdown('<div class="hero-title">🏇 Kuina AI Racing Pro (JRA直行解析)</div>', unsafe_allow_html=True)

st.info("💡 サイドバー検索を完全回避し、JRA 12桁レースIDから出馬表へ直接ダイレクトアクセスします。")

tab1, tab2 = st.tabs(["🎯 12桁IDダイレクト生成・解析", "🔢 ID直接入力"])

if 'active_race_id' not in st.session_state:
    st.session_state['active_race_id'] = None

now_jst = datetime.datetime.now(JST)
current_year = now_jst.year

with tab1:
    st.markdown("#### ⚙️ JRA 12桁レースID 自動組み立て")
    st.caption("年・競馬場・開催回・日目を指定すると、全12レースのIDが自動生成されます。")

    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    with col_c1:
        sel_year = st.number_input("年", 2020, 2026, current_year)
    with col_c2:
        sel_venue_name = st.selectbox("競馬場(JRA)", list(VENUE_MAP.keys()), index=5) # 中山
    with col_c3:
        sel_kai = st.number_input("回", 1, 6, 4)
    with col_c4:
        sel_nichi = st.number_input("日目", 1, 12, 7)

    venue_code = VENUE_MAP[sel_venue_name]
    base_id = f"{sel_year}{venue_code}{sel_kai:02d}{sel_nichi:02d}"

    st.markdown(f"**生成ベースID:** `{base_id}xx` （{sel_year}年 {sel_kai}回{sel_venue_name}{sel_nichi}日目）")

    st.write("▼ 対象レース番号を選択してください:")
    r_cols = st.columns(6)
    for r_num in range(1, 13):
        r_id = f"{base_id}{r_num:02d}"
        col_i = (r_num - 1) % 6
        with r_cols[col_i]:
            if st.button(f"🏇 {r_num}R", key=f"btn_gen_{r_id}", use_container_width=True):
                st.session_state['active_race_id'] = r_id

with tab2:
    st.markdown("#### 🔢 12桁ID直接指定")
    manual_id = st.text_input("12桁レースIDを入力 (例: 202406040711 = 中山11R):", value="202406040711")
    if st.button("🚀 このIDで直接解析"):
        st.session_state['active_race_id'] = manual_id

# ---------------------------------------------------------
# Results Area
# ---------------------------------------------------------
target_race_id = st.session_state.get('active_race_id')

if target_race_id:
    st.markdown("---")
    # レースID解析・パドック調整表示
    v_code = target_race_id[4:6] if len(target_race_id) == 12 else "00"
    v_name = VENUE_CODE_TO_NAME.get(v_code, "JRA")
    r_num_str = target_race_id[10:12] if len(target_race_id) == 12 else "00"

    st.markdown(f"### 📍 対象レース: **【{v_name} {int(r_num_str) if r_num_str.isdigit() else 0}R】** (ID: `{target_race_id}`)")

    with st.spinner(f"netkeiba出馬表(ID: {target_race_id})へ直接アクセス中... (サイドバー完全回避)"):
        data_list, err = get_race_data_by_id(target_race_id)

    if err:
        st.error(f"❌ {err}")
        st.warning("⚠️ 指定したレースIDの出馬表がまだ公開されていないか、データが存在しない可能性があります。")
    elif data_list:
        df = pd.DataFrame(data_list)
        st.success(f"✅ {len(data_list)} 頭の出馬表・オッズデータを直接取得完了！")

        # 表示順整列
        display_cols = ['印', '馬番', '馬名', '騎手', '斤量', '単勝オッズ', '人気', 'AI指数', '馬体重', '騎手評価']
        existing_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[existing_cols], use_container_width=True)

        st.markdown("#### 🏆 AI予想 本命・対抗・単穴カード")
        top3 = data_list[:3]
        c1, c2, c3 = st.columns(3)
        for idx, item in enumerate(top3):
            col = [c1, c2, c3][idx]
            m_class = "card-honmei" if idx == 0 else ("card-taikou" if idx == 1 else "card-tanana")
            b_class = "badge-honmei" if idx == 0 else ("badge-taikou" if idx == 1 else "badge-tanana")
            with col:
                st.markdown(f"""
                <div class="horse-card {m_class}">
                    <span class="{b_class}">{item.get('印')} {['本命', '対抗', '単穴'][idx]}</span>
                    <h3 style="margin: 8px 0;">{item.get('馬番')}番 {item.get('馬名')}</h3>
                    <p><b>鞍上:</b> {item.get('騎手')} (斤量: {item.get('斤量')}kg)</p>
                    <p><b>オッズ:</b> {item.get('単勝オッズ')}倍 ({item.get('人気')}人気)</p>
                    <p><b>AI指数:</b> <span style="font-size: 1.2rem; font-weight: 800; color: #1e3a8a;">{item.get('AI指数')}</span></p>
                </div>
                """, unsafe_allow_html=True)