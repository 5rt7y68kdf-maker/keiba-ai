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

# Visual Styling
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

    .horse-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 18px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        margin-bottom: 16px;
        height: auto !important;
        min-height: 220px;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        white-space: normal !important;
    }
    
    .horse-name-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: #0f172a;
        margin: 10px 0 6px 0;
        line-height: 1.3;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Utilities & Fetchers
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

    m_plain = re.search(r'(\d{3,4})', clean_txt)
    if m_plain:
        return f"{m_plain.group(1)}kg", 0

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

def extract_race_id_from_input(user_input):
    if not user_input:
        return None
    m = re.search(r'(\d{12})', str(user_input))
    if m:
        return m.group(1)
    m10 = re.search(r'(\d{10})', str(user_input))
    if m10:
        return "20" + m10.group(1)
    return None

def fetch_race_list_by_date(dt_str):
    clean_date = re.sub(r'\D', '', str(dt_str))
    if len(clean_date) != 8:
        return [], "日付は8桁の数字(YYYYMMDD)で指定してください。"

    races = []
    race_url = f"https://race.netkeiba.com/top/race_list.html?kaijo_date={clean_date}"
    soup, _ = fetch_html(race_url)
    if soup:
        for a in soup.find_all('a'):
            href = a.get('href', '')
            m = re.search(r'race_id=(\d{12})', href)
            if m:
                r_id = m.group(1)
                txt = a.text.strip().replace('\n', ' ')
                txt = re.sub(r'\s+', ' ', txt)
                if txt and not any(r['id'] == r_id for r in races):
                    races.append({'id': r_id, 'name': txt})

    if not races:
        db_url = f"https://db.netkeiba.com/race/list/{clean_date}/"
        soup_db, _ = fetch_html(db_url)
        if soup_db:
            for a in soup_db.find_all('a'):
                href = a.get('href', '')
                m = re.search(r'/race/(\d{12})', href)
                if m:
                    r_id = m.group(1)
                    txt = a.text.strip().replace('\n', ' ')
                    txt = re.sub(r'\s+', ' ', txt)
                    if txt and not any(r['id'] == r_id for r in races):
                        races.append({'id': r_id, 'name': txt})

    if not races:
        return [], f"指定された日付 ({clean_date}) の公式出馬表データが見つかりませんでした。"

    return races, None

def parse_shutuba_page(soup):
    rows = soup.select('tr.HorseList') or soup.select('table.ShutubaTable tr') or soup.select('table.ResultTable tr') or soup.select('table.race_table_01 tr')
    if not rows:
        all_trs = soup.find_all('tr')
        rows = [tr for tr in all_trs if tr.select_one('a[href*="/horse/"]')]

    if not rows:
        return []

    data_list = []
    for idx, r in enumerate(rows, start=1):
        td_list = r.find_all(['td', 'th'])
        if len(td_list) < 2:
            continue

        horse_a = r.select_one('a[href*="/horse/"]') or r.select_one('.HorseName a')
        if not horse_a:
            continue
        horse_name = horse_a.text.strip()
        if not horse_name or horse_name in ['馬名', '競走馬']:
            continue

        jockey_a = r.select_one('a[href*="/jockey/"]') or r.select_one('.Jockey a')
        jockey_name = jockey_a.text.strip() if jockey_a else "未定義"

        wakaban = None
        umaban = None
        odds_val = "未確定"
        pop_val = "未確定"
        weight_val = 55.0
        hw_str = "計不"

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

            if 'popular' in cls_str or 'pop' in cls_str:
                m_p = re.search(r'(\d+)', text)
                if m_p:
                    try: pop_val = int(m_p.group(1))
                    except ValueError: pass

            if 'weight' in cls_str or re.search(r'\d{3,4}\s*\(', text):
                p_str, _ = parse_horse_weight_str(text)
                if p_str != "計不":
                    hw_str = p_str

        if umaban is None: umaban = idx
        if wakaban is None: wakaban = (umaban - 1) // 2 + 1 if umaban <= 16 else 8

        data_list.append({
            '枠番': wakaban, '馬番': umaban, '馬名': horse_name,
            '騎手': jockey_name,
            '斤量': weight_val, '単勝オッズ': odds_val, '人気': pop_val,
            '馬体重': hw_str
        })

    return data_list

def calculate_ai_scores(data_list):
    if not data_list: return data_list

    scored_items = []
    for d in data_list:
        odds = d.get('単勝オッズ')
        pop = d.get('人気')
        weight = d.get('斤量', 55.0)
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
        if any(tj in jockey for tj in TOP_JOCKEYS_S): j_score = 7.0
        elif any(tj in jockey for tj in TOP_JOCKEYS_A): j_score = 4.0

        raw_score = pop_score + odds_score + weight_bonus + j_score + 15.0
        score = round(min(99.9, max(10.0, raw_score)), 1)

        win_prob = round(max(1.0, score / 3.5), 1)
        ev_val = round((win_prob / 100.0) * o_val, 2)
        rec_rate = int(ev_val * 100)

        d_copy = dict(d)
        d_copy['AI予想スコア'] = score
        d_copy['AI想定勝率'] = f"{win_prob}%"
        d_copy['期待値(EV)'] = f"{ev_val}"
        d_copy['期待回収率'] = f"{rec_rate}%"
        scored_items.append(d_copy)

    scored_items.sort(key=lambda x: x['AI予想スコア'], reverse=True)
    mark_list = ['◎ 本命', '◯ 対抗', '▲ 単穴', '△ 連下', '△ 連下', '☆ 穴馬']
    
    for idx, item in enumerate(scored_items):
        mark = mark_list[idx] if idx < len(mark_list) else 'ー'
        item['予想印'] = mark

    scored_items.sort(key=lambda x: x['馬番'] if isinstance(x['馬番'], int) else 99)
    return scored_items

def get_race_data_by_id(clean_id):
    urls = [
        f"https://race.netkeiba.com/race/shutuba.html?race_id={clean_id}",
        f"https://db.netkeiba.com/race/{clean_id}/",
        f"https://race.netkeiba.com/race/result.html?race_id={clean_id}"
    ]
    
    data_list = []
    for url in urls:
        soup, _ = fetch_html(url)
        if soup:
            data_list = parse_shutuba_page(soup)
            if data_list:
                break

    if not data_list:
        return None, f"出馬表データが見つかりませんでした。(指定ID: {clean_id})"

    data_list = calculate_ai_scores(data_list)
    return data_list, None

# ---------------------------------------------------------
# UI Core Component
# ---------------------------------------------------------
st.markdown('<div class="hero-title">🏇 Kuina AI Racing Pro</div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["🔗 出馬表URL / IDを直接貼り付け", "📅 日付から本物レース検索", "📌 お試しサンプル"])

target_race_id = None
today = datetime.date.today()

with tab1:
    st.markdown("##### netkeibaの「出馬表URL」または「12桁レースID」を入力")
    user_url_input = st.text_input(
        "出馬表URL / レースID:",
        placeholder="例: https://race.netkeiba.com/race/shutuba.html?race_id=202405021211"
    )
    if st.button("🚀 出馬表を直接読み込んでAI解析実行"):
        extracted_id = extract_race_id_from_input(user_url_input)
        if extracted_id:
            target_race_id = extracted_id
        else:
            st.error("有効なネット競馬の出馬表URLまたは12桁レースIDを入力してください。")

with tab2:
    selected_date = st.date_input("開催日を選択:", value=today)
    if st.button("🔍 指定日の公式出馬表一覧を取得"):
        dt_str = selected_date.strftime("%Y%m%d")
        races, err = fetch_race_list_by_date(dt_str)
        if err:
            st.error(err)
        else:
            st.session_state['fetched_races'] = races

    if 'fetched_races' in st.session_state and st.session_state['fetched_races']:
        race_options = {f"{r['name']} (ID: {r['id']})": r['id'] for r in st.session_state['fetched_races']}
        selected_race_label = st.selectbox("出馬表を選択してください:", list(race_options.keys()))
        if st.button("🚀 選択したレースの出馬表を解析"):
            target_race_id = race_options[selected_race_label]

with tab3:
    if st.button("🏆 日本ダービー (G1) の出馬表を解析"):
        target_race_id = "202405021211"

# ---------------------------------------------------------
# Results Area
# ---------------------------------------------------------
if target_race_id:
    st.markdown("---")
    with st.spinner("🏇 出馬表ページにアクセスしてリアルタイムAI解析中..."):
        data, error = get_race_data_by_id(target_race_id)

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
                    <div style="font-weight:bold; color:#1e40af; font-size:1.1rem;">{horse['予想印']}</div>
                    <div class="horse-name-title">{horse['馬番']}番 {horse['馬名']}</div>
                    <p style="color:#2563eb; font-weight:bold; margin:4px 0;">AIスコア: {horse['AI予想スコア']}pt</p>
                    <p style="color:#059669; font-weight:bold; margin:4px 0;">期待回収率: {horse['期待回収率']} (EV: {horse['期待値(EV)']})</p>
                    <p style="color:#475569; margin:4px 0;">騎手: {horse['騎手']} | オッズ: {horse['単勝オッズ']}倍</p>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("### 📋 出馬表 AI分析一覧")
        st.dataframe(df, use_container_width=True)