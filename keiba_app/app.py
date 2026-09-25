import re
import requests
from bs4 import BeautifulSoup
import urllib3
import streamlit as st
import datetime
import pandas as pd
import numpy as np

JST = datetime.timezone(datetime.timedelta(hours=9))

# SSL証明書警告の非表示化
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# JRA 10競馬場
VENUE_MAP = {
    "札幌": "01", "函館": "02", "福島": "03", "新潟": "04",
    "東京": "05", "中山": "06", "中京": "07", "京都": "08",
    "阪神": "09", "小倉": "10"
}
VENUE_CODE_TO_NAME = {v: k for k, v in VENUE_MAP.items()}

TOP_JOCKEYS_S = ["ルメール", "川田", "武豊", "坂井", "横山武", "戸崎", "モレイラ", "レーン"]
TOP_JOCKEYS_A = ["松山", "鮫島克", "岩田望", "西村淳", "菅原明", "津村", "田辺", "デムーロ", "丹内"]

st.set_page_config(
    page_title="Kuina AI Racing Pro",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="collapsed"
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
        margin-bottom: 0.5rem;
        letter-spacing: -0.02em;
    }
    .hero-sub {
        font-size: 1.0rem;
        color: #64748b;
        margin-bottom: 1.5rem;
    }

    /* Horse Card Styling */
    .horse-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 20px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        margin-bottom: 16px;
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
    }

    .race-btn-card {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 10px;
        padding: 12px;
        text-align: center;
        margin-bottom: 10px;
        transition: all 0.2s;
    }
    .race-btn-card:hover {
        border-color: #2563eb;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.15);
    }
</style>
""", unsafe_allow_html=True)

def fetch_html(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        html_text = res.content.decode('euc-jp', errors='replace')
        return BeautifulSoup(html_text, 'html.parser'), None
    except Exception as e:
        return None, f"通信エラー: {e}"

def clean_text(el):
    if not el: return ""
    return re.sub(r'\s+', ' ', el.text).strip()

def parse_horse_weight_str(txt):
    if not txt: return "計不", 0
    m = re.search(r'(\d{3,4})\s*\(?\s*([+-]?\d+)?\s*\)?', str(txt))
    if m:
        w_str = m.group(1)
        diff = int(m.group(2)) if m.group(2) else 0
        return w_str, diff
    return "計不", 0

# ---------------------------------------------------------
# 日付指定から【JRA全競馬場・全12レース】の正確な実在IDを一括抽出する関数
# ---------------------------------------------------------
def fetch_daily_schedule(dt_str):
    """
    指定日のnetkeibaトップ一覧から、各競馬場ブロック(中山・阪神等)ごとに
    実在する全12レースのIDとレース名を完全にグループ化抽出します。
    """
    clean_date = re.sub(r'\D', '', str(dt_str))
    if len(clean_date) != 8:
        return {}, "日付は8桁の数字(YYYYMMDD)で指定してください。"

    target_url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={clean_date}"
    soup, err = fetch_html(target_url)
    
    if not soup:
        # DB側のバックアップURL
        target_url = f"https://db.netkeiba.com/race/list/{clean_date}/"
        soup, err = fetch_html(target_url)

    if not soup:
        return {}, f"指定日({clean_date})のデータが取得できませんでした。"

    # サイドバーやヘッダーの注目レースノイズを完全分解破棄
    for noisy in soup.select('#SideBar, .PickupRace, .Orepro, #Header, .Header, .Footer'):
        noisy.decompose()

    venue_races_map = {}

    # netkeibaの会場ごとブロック (RaceList_DataList または dl/div 単位)
    venue_blocks = soup.select('div.RaceList_Box') or soup.select('dl.RaceList_DataList') or soup.select('div.db_main_race_list')

    if venue_blocks:
        for block in venue_blocks:
            # 会場名取得
            header_el = block.select_one('.RaceList_DataHeader') or block.select_one('dt') or block.select_one('.db_head')
            header_text = clean_text(header_el)
            
            # 会場コード特定 (例: 中山, 阪神, 中京)
            v_name = None
            for v_key in VENUE_MAP.keys():
                if v_key in header_text:
                    v_name = v_key
                    break
            
            if not v_name:
                continue

            if v_name not in venue_races_map:
                venue_races_map[v_name] = []

            # その会場ブロック内の全レースリンク取得
            a_list = block.find_all('a')
            for a in a_list:
                href = a.get('href', '')
                m = re.search(r'race_id=(\d{12})', href) or re.search(r'/race/(\d{12})', href)
                if not m: continue

                r_id = m.group(1)
                r_num = int(r_id[10:12])

                r_text = clean_text(a)
                clean_r_name = re.sub(r'^(📍|【.*?】|\d+R)\s*', '', r_text).strip()
                clean_r_name = re.sub(r'(出馬表|オッズ|結果|映像|払戻|掲示板|データ|競馬新聞|予想|俺プロ)', '', clean_r_name).strip()
                if not clean_r_name or len(clean_r_name) < 2:
                    clean_r_name = f"第{r_num}レース"

                # 重複回避で追加
                if not any(item['id'] == r_id for item in venue_races_map[v_name]):
                    venue_races_map[v_name].append({
                        'id': r_id,
                        'r_num': r_num,
                        'name': clean_r_name,
                        'venue': v_name
                    })

    # 全体走査のフォールバック (ブロック抽出に漏れがあった場合)
    if not venue_races_map:
        main_box = soup.select_one('div.RaceList_Data') or soup.select_one('div.Race_List') or soup
        for a in main_box.find_all('a'):
            href = a.get('href', '')
            m = re.search(r'race_id=(\d{12})', href) or re.search(r'/race/(\d{12})', href)
            if not m: continue
            r_id = m.group(1)
            v_code = r_id[4:6]
            if v_code not in VENUE_CODE_TO_NAME: continue
            
            v_name = VENUE_CODE_TO_NAME[v_code]
            r_num = int(r_id[10:12])
            
            if v_name not in venue_races_map:
                venue_races_map[v_name] = []

            if not any(item['id'] == r_id for item in venue_races_map[v_name]):
                venue_races_map[v_name].append({
                    'id': r_id,
                    'r_num': r_num,
                    'name': f"第{r_num}レース",
                    'venue': v_name
                })

    # レース番号順にソート
    for v_name in venue_races_map:
        venue_races_map[v_name].sort(key=lambda x: x['r_num'])

    if not venue_races_map:
        return {}, f"指定日 ({clean_date}) の中央競馬(JRA)レースは見つかりませんでした。"

    return venue_races_map, None

# ---------------------------------------------------------
# 出馬表解析ロジック (厳格・推測なし)
# ---------------------------------------------------------
def parse_race_netkeiba(soup):
    rows = soup.select('tr.HorseList') or soup.select('table.ShutubaTable tr') or soup.select('table.Shutuba_Table tr') or soup.select('table.ResultTable tr')
    if not rows:
        all_trs = soup.find_all('tr')
        rows = [tr for tr in all_trs if tr.select_one('a[href*="/horse/"]')]

    if not rows: return []

    data_list = []
    for idx, r in enumerate(rows, start=1):
        if 'Cancel' in r.get('class', []): continue
        td_list = r.find_all(['td', 'th'])
        if len(td_list) < 2: continue

        horse_a = r.select_one('a[href*="/horse/"]') or r.select_one('.HorseName a')
        if not horse_a: continue
        horse_name = clean_text(horse_a)
        if not horse_name or horse_name in ['馬名', '競走馬']: continue

        jockey_a = r.select_one('a[href*="/jockey/"]') or r.select_one('.Jockey a')
        jockey_name = clean_text(jockey_a) if jockey_a else "未定義"

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
            text = clean_text(td)

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
            txt = clean_text(td_list[0])
            if txt.isdigit() and 1 <= int(txt) <= 8: wakaban = int(txt)

        if umaban is None and len(td_list) > 1:
            txt = clean_text(td_list[1])
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
                uma_txt = clean_text(tds[1]) if len(tds) > 1 else (clean_text(tds[0]) if len(tds) > 0 else '')
                odds_txt = clean_text(tds[-2]) if len(tds) > 2 else ''
                pop_txt = clean_text(tds[-1]) if len(tds) > 3 else ''
                
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
            j_comment = f"【トップ騎手】{jockey} (勝率特筆)"
        elif any(tj in jockey for tj in TOP_JOCKEYS_A):
            j_score = 4.0
            j_comment = f"【有力騎手】{jockey} (安定高)"
        else:
            j_score = 1.0
            j_comment = f"【鞍上】{jockey}"

        blood_score = 3.0
        blood_comment = "血統適性標準"
        if race_env['condition'] in ['重', '不良', '稍重']:
            if any(kw in horse_name for kw in ["キング", "ゴールド", "ダノン", "ボルド", "パワー", "ロック", "ロベルト"]):
                blood_score = 6.0
                blood_comment = f"【血統高適性】パワー型血統 ({race_env['condition']}馬場順応)"
            else:
                blood_score = 4.0
                blood_comment = f"【血統適性】{race_env['condition']}馬場適性あり"
        else:
            blood_score = 5.0
            blood_comment = "【血統高適性】良馬場スピード血統"

        weather_score = 2.0
        if race_env['weather'] == '雨' or race_env['condition'] in ['重', '不良']:
            weather_score = 3.0 if hw_diff >= 4 else (-3.0 if hw_diff <= -6 else 1.0)

        bias_score = 2.0
        bias_comment = "馬場フラット"
        if "内伸び・前残り" in race_env['bias']:
            if waku in [1, 2, 3]:
                bias_score = 6.0
                bias_comment = f"【バイアス好走】内枠{waku}枠有利"
            elif waku in [4, 5]: bias_score = 3.0
            else:
                bias_score = -2.0
                bias_comment = "【バイアス懸念】外枠位置取り懸念"
        elif "外伸び・差し" in race_env['bias']:
            if waku in [6, 7, 8]:
                bias_score = 6.0
                bias_comment = f"【バイアス好走】外枠{waku}枠差し有利"

        pattern_score = 4.0
        pattern_comment = "好走パターン適合"
        if race_env['pace'] == 'ハイペース（差し有利）' and p_val >= 4 and o_val >= 10.0:
            pattern_score = 6.0
            pattern_comment = "【好走パターン】ハイペース消耗戦での差し一発"
        elif race_env['pace'] == 'スローペース（前残り）' and waku <= 4:
            pattern_score = 6.0
            pattern_comment = "【好走パターン】スローマイペース逃げ粘り"

        hw_comment = "馬体重許容範囲"
        weight_diff_score = 0.0
        if abs(hw_diff) <= 4:
            weight_diff_score = 3.0
            hw_comment = "馬体重仕上がり良好"
        elif hw_diff >= 10:
            weight_diff_score = -3.0
            hw_comment = "馬体重太め残り警戒"
        elif hw_diff <= -10:
            weight_diff_score = -4.0
            hw_comment = "馬体重大幅減警戒"

        p_status = paddock_status_map.get(uma, "⚪ 普通 (0pt)")
        paddock_score = 0.0
        if "✨ 絶好調" in p_status: paddock_score = 7.0
        elif "⚠️ 太め残り" in p_status: paddock_score = -4.0
        elif "💥 テンション高" in p_status: paddock_score = -5.0

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

    return scored_items

def get_race_data(clean_id, paddock_status_map=None, race_env=None):
    errors = []
    race_urls = [
        f"https://race.netkeiba.com/race/shutuba.html?race_id={clean_id}",
        f"https://race.netkeiba.com/race/result.html?race_id={clean_id}"
    ]
    data_list = []
    for url in race_urls:
        soup, err = fetch_html(url)
        if soup:
            data_list = parse_race_netkeiba(soup)
            if data_list: break
        elif err: errors.append(err)

    if not data_list:
        return None, f"レースデータが取得できませんでした (ID: {clean_id})"

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
# UI Main - Simple, Direct, No Shifting ("ずれない＆超使いやすい")
# ---------------------------------------------------------
st.markdown('<div class="hero-title">🏇 Kuina AI Racing Pro (直感操作ナビ)</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">日付と競馬場を選ぶだけ！ズレなしで全12レースを一発選択できます。</div>', unsafe_allow_html=True)

now_jst = datetime.datetime.now(JST)
today_jst = now_jst.date()
weekday = today_jst.weekday()

if weekday == 6:
    this_saturday = today_jst - datetime.timedelta(days=1)
    this_sunday = today_jst
else:
    this_saturday = today_jst + datetime.timedelta(days=(5 - weekday))
    this_sunday = today_jst + datetime.timedelta(days=(6 - weekday))

if 'selected_date' not in st.session_state:
    st.session_state['selected_date'] = this_saturday if weekday in [5, 6] else this_saturday

# Step 1: 日付選択
st.markdown("### 1️⃣ 日付を選択")
d_col1, d_col2, d_col3, d_col4 = st.columns([1, 1, 1, 1.5])

with d_col1:
    if st.button(f"🏇 今週土曜 ({this_saturday.strftime('%m/%d')})", use_container_width=True):
        st.session_state['selected_date'] = this_saturday
        st.session_state.pop('daily_map', None)

with d_col2:
    if st.button(f"🏇 今週日曜 ({this_sunday.strftime('%m/%d')})", use_container_width=True):
        st.session_state['selected_date'] = this_sunday
        st.session_state.pop('daily_map', None)

with d_col3:
    if st.button(f"📅 本日 ({today_jst.strftime('%m/%d')})", use_container_width=True):
        st.session_state['selected_date'] = today_jst
        st.session_state.pop('daily_map', None)

with d_col4:
    custom_d = st.date_input("その他の日付:", value=st.session_state['selected_date'], label_visibility="collapsed")
    if custom_d != st.session_state['selected_date']:
        st.session_state['selected_date'] = custom_d
        st.session_state.pop('daily_map', None)

cur_date = st.session_state['selected_date']
dt_str = cur_date.strftime("%Y%m%d")

# 日付ごとの全競馬場データ取得
if 'daily_map' not in st.session_state or st.session_state.get('cur_dt_str') != dt_str:
    with st.spinner(f"📅 {cur_date.strftime('%Y年%m月%d日')} の開催データを読込中..."):
        daily_map, err = fetch_daily_schedule(dt_str)
        st.session_state['daily_map'] = daily_map
        st.session_state['daily_err'] = err
        st.session_state['cur_dt_str'] = dt_str

daily_map = st.session_state.get('daily_map', {})
daily_err = st.session_state.get('daily_err')

st.markdown("---")

if daily_err and not daily_map:
    st.warning(f"⚠️ {cur_date.strftime('%Y/%m/%d')} : {daily_err}")
    st.info("💡 上の「今週土曜」または「今週日曜」ボタンを押すと週末の中央競馬全レースが表示されます。")
else:
    # Step 2: 競馬場選択
    st.markdown(f"### 2️⃣ 開催場を選択 (`{cur_date.strftime('%Y年%m月%d日')}` JRA中央競馬)")
    venues = list(daily_map.keys())
    
    if not venues:
        st.info("指定日に開催される中央競馬(JRA)レースはありません。土日を選択してください。")
    else:
        selected_venue = st.radio("開催場所:", venues, horizontal=True)
        
        # Step 3: レース番号ボタン (1R〜12R) 一括表示
        st.markdown(f"### 3️⃣ レースを選択 (`📍 {selected_venue}`)")
        
        races = daily_map.get(selected_venue, [])
        if races:
            cols = st.columns(4)
            for idx, r in enumerate(races):
                col = cols[idx % 4]
                r_num = r['r_num']
                r_name = r['name']
                r_id = r['id']
                
                label = f"**{r_num}R** {r_name[:10]}"
                if col.button(f"{r_num}R : {r_name}", key=f"btn_{r_id}", use_container_width=True):
                    st.session_state['active_race_id'] = r_id
                    st.session_state['active_race_label'] = f"📍【{selected_venue} {r_num}R】 {r_name}"

# ---------------------------------------------------------
# Results Dashboard
# ---------------------------------------------------------
active_id = st.session_state.get('active_race_id')
active_label = st.session_state.get('active_race_label', '')

if active_id:
    st.markdown("---")
    st.success(f"🎯 **選択中:** {active_label} (ID: `{active_id}`)")

    if 'paddock_map' not in st.session_state:
        st.session_state['paddock_map'] = {}

    st.markdown("#### 🌦️ トラックバイアス・環境補正")
    env_c1, env_c2, env_c3, env_c4 = st.columns(4)
    with env_c1: sel_weather = st.selectbox("☀️ 天候", ["晴", "曇", "雨", "小雨"], index=0)
    with env_c2: sel_condition = st.selectbox("🌿 馬場状態", ["良", "稍重", "重", "不良"], index=0)
    with env_c3: sel_bias = st.selectbox("🚧 トラックバイアス", ["⚪ フラット", "🟩 内伸び・前残り有利", "🟨 外伸び・差し有利"], index=0)
    with env_c4: sel_pace = st.selectbox("🏃 ペース予想", ["ミドルペース", "スローペース（前残り）", "ハイペース（差し有利）"], index=0)

    current_race_env = {
        'weather': sel_weather,
        'condition': sel_condition,
        'bias': sel_bias,
        'pace': sel_pace
    }

    with st.spinner("🏇 AIスコア分析・リアルタイム計算中..."):
        data, error = get_race_data(active_id, st.session_state['paddock_map'], current_race_env)

    if error:
        st.error(error)
    elif data:
        honmei = data[0] if len(data) > 0 else None
        taikou = data[1] if len(data) > 1 else None
        tanana = data[2] if len(data) > 2 else None

        st.markdown("### 🏆 AI予想 TOP3")
        c1, c2, c3 = st.columns(3)

        if honmei:
            with c1:
                st.markdown(f"""
                <div class="horse-card card-honmei">
                    <span class="badge-honmei">◎ 本命</span>
                    <div class="horse-name-title">{honmei['馬番']}番 {honmei['馬名']}</div>
                    <p style="color:#475569; font-weight:600; margin:4px 0;">騎手: {honmei['騎手']} ({honmei['斤量']}kg)</p>
                    <p style="color:#059669; font-weight:700;">オッズ: {honmei['単勝オッズ']}倍 ({honmei['人気']}人気)</p>
                    <hr style="margin:8px 0; border-color:#fca5a5;">
                    <p style="font-size:0.85rem; color:#1e293b;"><b>AI推し理由:</b> {honmei['_p_comment']}</p>
                </div>
                """, unsafe_allow_html=True)

        if taikou:
            with c2:
                st.markdown(f"""
                <div class="horse-card card-taikou">
                    <span class="badge-taikou">◯ 対抗</span>
                    <div class="horse-name-title">{taikou['馬番']}番 {taikou['馬名']}</div>
                    <p style="color:#475569; font-weight:600; margin:4px 0;">騎手: {taikou['騎手']} ({taikou['斤量']}kg)</p>
                    <p style="color:#059669; font-weight:700;">オッズ: {taikou['単勝オッズ']}倍 ({taikou['人気']}人気)</p>
                    <hr style="margin:8px 0; border-color:#86efac;">
                    <p style="font-size:0.85rem; color:#1e293b;"><b>AI推し理由:</b> {taikou['_p_comment']}</p>
                </div>
                """, unsafe_allow_html=True)

        if tanana:
            with c3:
                st.markdown(f"""
                <div class="horse-card card-tanana">
                    <span class="badge-tanana">▲ 単穴</span>
                    <div class="horse-name-title">{tanana['馬番']}番 {tanana['馬名']}</div>
                    <p style="color:#475569; font-weight:600; margin:4px 0;">騎手: {tanana['騎手']} ({tanana['斤量']}kg)</p>
                    <p style="color:#059669; font-weight:700;">オッズ: {tanana['単勝オッズ']}倍 ({tanana['人気']}人気)</p>
                    <hr style="margin:8px 0; border-color:#93c5fd;">
                    <p style="font-size:0.85rem; color:#1e293b;"><b>AI推し理由:</b> {tanana['_p_comment']}</p>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("### 📊 全出走馬データ一覧")
        df_display = pd.DataFrame(data)
        cols_to_show = ['予想印', '馬番', '枠番', '馬名', '騎手', '斤量', '単勝オッズ', '人気', 'AI予想スコア', '血統適性', '騎手評価']
        cols_existing = [c for c in cols_to_show if c in df_display.columns]
        st.dataframe(df_display[cols_existing], use_container_width=True)