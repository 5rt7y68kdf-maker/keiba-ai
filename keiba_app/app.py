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

# 日本標準時 (JST) 定義
JST = datetime.timezone(datetime.timedelta(hours=9))

# 全国10競馬場のコードマップ
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
        font-size: 2.3rem;
        font-weight: 800;
        color: #1e3a8a;
        margin-bottom: 1.5rem;
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
# Web Scraping & Data Extraction Core
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

def clean_text(element_or_str):
    if not element_or_str:
        return ""
    if hasattr(element_or_str, 'text'):
        text = element_or_str.text
    else:
        text = str(element_or_str)
    return re.sub(r'\s+', ' ', text).strip()

def parse_netkeiba_shutuba_table(soup, race_id):
    """
    出馬表HTMLから必要なtable部分のみを特定抽出し、CSS Class/構造を利用して高精度パースを行います。
    推測補完を行わず、厳格なDataFrameフォーマットで出力します。
    """
    race_number = int(race_id[-2:]) if race_id and len(race_id) >= 2 else None

    # 1. 必要なtable部分だけを抽出
    table = (
        soup.select_one('table.Shutuba_Table') or 
        soup.select_one('table.ShutubaTable') or 
        soup.select_one('table.race_table_01')
    )

    if not table:
        raise ValueError(f"出馬表テーブルが見つかりませんでした (Race ID: {race_id})。HTML構造変更または未配信の可能性があります。")

    # 2. ページ上の表記頭数を取得 (頭数照合用)
    page_text = soup.get_text()
    head_count_match = re.search(r'(\d{1,2})\s*頭', page_text)
    expected_head_count = int(head_count_match.group(1)) if head_count_match else None

    # 3. 出走馬の行要素のみを抽出 (ノイズ行・サイドバーの除外)
    rows = table.select('tr.HorseList')
    if not rows:
        all_trs = table.find_all('tr')
        rows = [tr for tr in all_trs if tr.select_one('a[href*="/horse/"]')]

    if not rows:
        raise ValueError(f"出馬表テーブル内に有効な競走馬データ行が見つかりませんでした (Race ID: {race_id})。")

    parsed_rows = []

    for idx, r in enumerate(rows, start=1):
        # 除外・出走取消馬の判定
        if 'Cancel' in r.get('class', []) or r.select_one('.Cancel'):
            continue

        tds = r.find_all(['td', 'th'])
        if len(tds) < 2:
            continue

        # A. 馬番 (horse_number) - CSS Class / 構造重視
        horse_num = None
        uma_td = (
            r.select_one('td[class*="Umaban"]') or 
            r.select_one('td.txt_c') or 
            r.select_one('td.umaban')
        )
        if uma_td:
            txt = clean_text(uma_td)
            if txt.isdigit():
                horse_num = int(txt)

        if horse_num is None:
            for td in tds:
                classes = [c.lower() for c in td.get('class', [])]
                if any('umaban' in c for c in classes):
                    txt = clean_text(td)
                    if txt.isdigit():
                        horse_num = int(txt)
                        break

        # B. 馬名 (horse_name)
        horse_name = None
        horse_a = (
            r.select_one('span.HorseName a') or 
            r.select_one('td.HorseInfo a[href*="/horse/"]') or 
            r.select_one('a[href*="/horse/"]')
        )
        if horse_a:
            horse_name = clean_text(horse_a)
            horse_name = re.sub(r'\(.*?\)', '', horse_name).strip()

        # C. 性齢 (sex_age)
        sex_age = None
        barei_el = (
            r.select_one('td.Barei') or 
            r.select_one('td[class*="Barei"]') or 
            r.select_one('span.Barei')
        )
        if barei_el:
            sex_age = clean_text(barei_el)
        else:
            for td in tds:
                txt = clean_text(td)
                m = re.search(r'([牡牝セ]\d+)', txt)
                if m:
                    sex_age = m.group(1)
                    break

        # D. 斤量 (weight) - 勝手な55.0補完は絶対に行わずNone/NaN扱い
        weight = None
        for td in tds:
            classes = [c.lower() for c in td.get('class', [])]
            txt = clean_text(td)
            if any(k in c for k in ['jockey', 'kinryo', 'weight', 'txt_c']):
                m = re.search(r'^([456]\d(?:\.\d)?)$', txt)
                if m:
                    weight = float(m.group(1))
                    break
        if weight is None:
            for td in tds:
                txt = clean_text(td)
                m = re.search(r'\b([456]\d(?:\.\d)?)\b', txt)
                if m:
                    try:
                        w_val = float(m.group(1))
                        if 40.0 <= w_val <= 65.0:
                            weight = w_val
                            break
                    except ValueError:
                        pass

        # E. 騎手 (jockey)
        jockey = None
        jockey_a = (
            r.select_one('td.Jockey a') or 
            r.select_one('a[href*="/jockey/"]')
        )
        if jockey_a:
            jockey = clean_text(jockey_a)
            jockey = re.sub(r'^[▲☆◇△◯▲\d\s]+', '', jockey).strip()

        # F. 人気 (popularity) - デフォルト補完せずNaN扱い
        popularity = None
        pop_el = (
            r.select_one('td.Popular') or 
            r.select_one('span[id^="ninki-"]') or 
            r.select_one('td[class*="pop"]')
        )
        if pop_el:
            txt = clean_text(pop_el)
            m = re.search(r'(\d+)', txt)
            if m:
                popularity = int(m.group(1))
        else:
            for td in tds:
                classes = [c.lower() for c in td.get('class', [])]
                if any('pop' in c or 'ninki' in c for c in classes):
                    txt = clean_text(td)
                    m = re.search(r'(\d+)', txt)
                    if m:
                        popularity = int(m.group(1))
                        break

        # G. オッズ (odds) - デフォルト20.0補完せずNaN扱い
        odds = None
        odds_el = (
            r.select_one('td.Odds') or 
            r.select_one('span[id^="odds-"]') or 
            r.select_one('td[class*="odds"]')
        )
        if odds_el:
            txt = clean_text(odds_el)
            m = re.search(r'(\d+\.\d+|\d+)', txt)
            if m:
                try:
                    odds = float(m.group(1))
                except ValueError:
                    odds = None
        else:
            for td in tds:
                classes = [c.lower() for c in td.get('class', [])]
                if any('odds' in c for c in classes):
                    txt = clean_text(td)
                    m = re.search(r'(\d+\.\d+)', txt)
                    if m:
                        try:
                            odds = float(m.group(1))
                            break
                        except ValueError:
                            pass

        # 必須項目 (馬番・馬名) の欠損チェック -> 欠損時は誤データ混入防止のため即座にエラー停止
        if horse_num is None or not horse_name:
            raise ValueError(
                f"【データ解析エラー】 {idx}行目の必須データ（馬番={horse_num}, 馬名='{horse_name}'）の抽出に失敗しました。"
                f"不正データの混入を防止するため処理を安全に停止します。"
            )

        parsed_rows.append({
            'race_id': str(race_id),
            'race_number': race_number,
            'horse_number': horse_num,
            'horse_name': horse_name,
            'sex_age': sex_age if sex_age else None,
            'weight': weight if weight is not None else np.nan,
            'jockey': jockey if jockey else None,
            'popularity': popularity if popularity is not None else np.nan,
            'odds': odds if odds is not None else np.nan
        })

    df = pd.DataFrame(parsed_rows)

    # 4. 頭数の照合チェック
    extracted_count = len(df)
    if expected_head_count is not None and extracted_count != expected_head_count:
        raise ValueError(
            f"【頭数不一致エラー】 出馬表上の頭数は {expected_head_count} 頭ですが、抽出されたデータは {extracted_count} 頭です。"
            f"データの欠落または重複が発生している可能性があるため処理を停止します。"
        )

    # 型の厳格化
    df['horse_number'] = df['horse_number'].astype(int)
    if df['race_number'].notna().all():
        df['race_number'] = df['race_number'].astype(int)

    return df

def fetch_race_list_by_date(dt_str):
    clean_date = re.sub(r'\D', '', str(dt_str))
    if len(clean_date) != 8:
        return [], "日付は8桁の数字(YYYYMMDD)で指定してください。"

    races_dict = {}
    urls = [
        f"https://race.netkeiba.com/top/race_list.html?kaisai_date={clean_date}",
        f"https://race.netkeiba.com/top/?kaisai_date={clean_date}"
    ]

    for target_url in urls:
        soup, _ = fetch_html(target_url)
        if not soup: continue

        # サイドバー・ヘッダーのノイズ要素を事前に破棄
        for noise in soup.select('#Header, #SideBar, .PickupRace, .Orepro, .Footer'):
            noise.decompose()

        main_box = soup.select_one('div.RaceList_Data') or soup.select_one('div.Race_List') or soup

        for a in main_box.find_all('a'):
            href = a.get('href', '')
            m = re.search(r'race_id=(\d{12})', href) or re.search(r'/race/(\d{12})', href)
            if not m: continue

            r_id = m.group(1)
            v_code = r_id[4:6]
            if v_code not in VENUE_CODE_TO_NAME: continue

            venue_name = VENUE_CODE_TO_NAME[v_code]
            r_num = int(r_id[10:12])

            raw_text = clean_text(a)
            clean_name = re.sub(r'^(📍|【.*?】|\d+R)\s*', '', raw_text).strip()
            clean_name = re.sub(r'(出馬表|オッズ|結果|映像|払戻|掲示板|データ|競馬新聞|予想|俺プロ)', '', clean_name).strip()

            display_title = f"📍【{venue_name} {r_num}R】 {clean_name}" if clean_name and len(clean_name) >= 2 else f"📍【{venue_name} {r_num}R】"

            if r_id not in races_dict or len(display_title) > len(races_dict[r_id]['name']):
                races_dict[r_id] = {
                    'id': r_id,
                    'name': display_title,
                    'venue': venue_name,
                    'r_num': r_num
                }

    if not races_dict:
        db_url = f"https://db.netkeiba.com/race/list/{clean_date}/"
        soup, _ = fetch_html(db_url)
        if soup:
            for noise in soup.select('#Header, #SideBar, .PickupRace, .Orepro'):
                noise.decompose()
            main_box = soup.select_one('div.db_main_race_list') or soup.select_one('div#main') or soup
            for a in main_box.find_all('a'):
                href = a.get('href', '')
                m = re.search(r'/race/(\d{12})', href)
                if m:
                    r_id = m.group(1)
                    v_code = r_id[4:6]
                    if v_code not in VENUE_CODE_TO_NAME: continue
                    venue_name = VENUE_CODE_TO_NAME[v_code]
                    r_num = int(r_id[10:12])

                    raw_text = clean_text(a)
                    clean_name = re.sub(r'^(📍|【.*?】|\d+R)\s*', '', raw_text).strip()
                    clean_name = re.sub(r'(出馬表|オッズ|結果|映像|払戻|掲示板|データ|競馬新聞|予想|俺プロ)', '', clean_name).strip()

                    display_title = f"📍【{venue_name} {r_num}R】 {clean_name}" if clean_name and len(clean_name) >= 2 else f"📍【{venue_name} {r_num}R】"

                    if r_id not in races_dict:
                        races_dict[r_id] = {
                            'id': r_id,
                            'name': display_title,
                            'venue': venue_name,
                            'r_num': r_num
                        }

    if not races_dict:
        return [], f"指定された日付 ({clean_date}) の中央競馬(JRA)レースデータは見つかりませんでした。"

    races = list(races_dict.values())
    races.sort(key=lambda x: x['id'])
    return races, None

def get_race_data(input_id):
    clean_id = re.sub(r'\D', '', str(input_id))
    if len(clean_id) == 10 and clean_id.startswith(('20', '21', '22', '23', '24', '25', '26')):
        clean_id = '20' + clean_id

    if not clean_id or len(clean_id) != 12:
        return None, "有効な12桁（または10桁）のレースIDを入力してください。"

    errors = []
    race_urls = [
        f"https://race.netkeiba.com/race/shutuba.html?race_id={clean_id}",
        f"https://db.netkeiba.com/race/{clean_id}/"
    ]

    df = None
    for url in race_urls:
        soup, err = fetch_html(url)
        if soup:
            try:
                df = parse_netkeiba_shutuba_table(soup, clean_id)
                if df is not None and not df.empty:
                    break
            except Exception as e:
                errors.append(f"Parse error ({url}): {e}")
        elif err:
            errors.append(f"HTTP error ({url}): {err}")

    if df is None or df.empty:
        return None, f"レースデータの取り込みに失敗しました。(ID: {clean_id})\n" + "\n".join(errors)

    return df, None

# ---------------------------------------------------------
# UI Core Component
# ---------------------------------------------------------
st.markdown('<div class="hero-title">🏇 Kuina AI Racing Pro (出馬表データ解析エンジン)</div>', unsafe_allow_html=True)

today = datetime.datetime.now(JST).date()

st.markdown("### 📅 対象レース選択")
mode = st.radio("検索モードを選択:", ["📅 開催日付から選択", "⚙️ 競馬場・レース番号を直接指定"], horizontal=True)

target_race_id = None

if "日付" in mode:
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        selected_date = st.date_input("開催日を選択:", value=today)
        if st.button("🔍 レース一覧を取得"):
            dt_str = selected_date.strftime("%Y%m%d")
            with st.spinner("netkeibaから全開催レースを取得中..."):
                races, err = fetch_race_list_by_date(dt_str)
                if err:
                    st.error(err)
                else:
                    st.session_state['fetched_races'] = races

    with col_d2:
        if 'fetched_races' in st.session_state and st.session_state['fetched_races']:
            race_options = {f"{r['name']} (ID: {r['id']})": r['id'] for r in st.session_state['fetched_races']}
            selected_race_label = st.selectbox("レースを選択してください:", list(race_options.keys()))
            if selected_race_label:
                target_race_id = race_options[selected_race_label]

else:
    col1, col2, col3 = st.columns(3)
    with col1:
        sel_year = st.number_input("年", 2020, 2026, today.year)
    with col2:
        sel_venue = st.selectbox("競馬場", list(VENUE_MAP.keys()), index=4) # 東京
    with col3:
        sel_race_num = st.number_input("レース番号 (1R〜12R)", 1, 12, 11)

    col4, col5 = st.columns(2)
    with col4:
        sel_kai = st.number_input("回 (例: 4回)", 1, 12, 4)
    with col5:
        sel_nichi = st.number_input("日目 (例: 6日目)", 1, 12, 6)

    target_race_id = f"{sel_year}{VENUE_MAP[sel_venue]}{sel_kai:02d}{sel_nichi:02d}{sel_race_num:02d}"
    st.info(f"📍 生成レースID: `{target_race_id}` ({sel_venue} {sel_race_num}R)")

# ---------------------------------------------------------
# Results & Verification Area
# ---------------------------------------------------------
if target_race_id:
    st.markdown("---")
    st.markdown(f"### 📊 レース出馬表データ解析結果 (ID: `{target_race_id}`)")

    with st.spinner("🔍 HTMLテーブルから出馬表データを厳格抽出中..."):
        df, error = get_race_data(target_race_id)

        if error:
            st.error(error)
        else:
            st.success("✅ 出馬表データの正常取得および品質検証をクリアしました。")
            
            # 7. 人間が確認できるように先頭5行を表示
            st.markdown("#### 🔍 人間によるデータ確認用 (先頭5行プレビュー)")
            st.caption("AI学習データ混入前に、カラムと数値が正しくマッピングされているか確認してください。")
            st.dataframe(df.head(5), use_container_width=True)

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("取得全頭数", f"{len(df)} 頭")
            col_m2.metric("必須項目欠損率", "0.0 % (完全取得)")
            col_m3.metric("データ品質ステータス", "PASSED (適合)")

            st.markdown("#### 📋 全出走馬 統一データフレーム一覧")
            st.dataframe(df, use_container_width=True, hide_index=True)

            csv = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 統一出馬表データ (CSV) をダウンロード",
                data=csv,
                file_name=f"shutuba_{target_race_id}.csv",
                mime="text/csv"
            )