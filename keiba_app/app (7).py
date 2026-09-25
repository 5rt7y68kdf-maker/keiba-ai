import re
import requests
from bs4 import BeautifulSoup
import urllib3
import streamlit as st
import datetime
import pandas as pd

# SSL証明書警告の非表示化
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 全国10競馬場 (JRA) の完全コードマップ
JRA_VENUES = {
    "札幌": "01", "函館": "02", "福島": "03", "新潟": "04",
    "東京": "05", "中山": "06", "中京": "07", "京都": "08",
    "阪神": "09", "小倉": "10"
}
VENUE_MAP = JRA_VENUES
VENUE_CODE_TO_NAME = {v: k for k, v in JRA_VENUES.items()}

ALL_TICKET_TYPES = ["単勝", "複勝", "枠連", "馬連", "ワイド", "馬単", "3連複", "3連単"]

TOP_JOCKEYS_S = ["ルメール", "川田", "武豊", "坂井", "横山武", "戸崎", "モレイラ", "レーン"]
TOP_JOCKEYS_A = ["松山", "鮫島克", "岩田望", "西村淳", "菅原明", "津村", "田辺", "デムーロ", "丹内"]

# ---------------------------------------------------------
# Streamlit Page Config & Mobile-First Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="Kuina AI Racing Pro (JRA中央競馬)",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .stApp {
        background-color: #f8fafc;
        color: #0f172a;
        font-family: 'Helvetica Neue', Arial, 'Hiragino Sans', sans-serif;
    }
    .hero-title {
        font-size: 2.2rem;
        font-weight: 900;
        color: #ffffff;
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
        padding: 18px 24px;
        border-radius: 16px;
        margin-bottom: 20px;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.25);
    }
    /* ボタンの文字色と背景を強制固定（スマホ視認性100%保証） */
    .stButton>button {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
        color: #ffffff !important;
        font-weight: 800 !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 10px 16px !important;
        box-shadow: 0 2px 6px rgba(37, 99, 235, 0.3) !important;
        font-size: 0.95rem !important;
        transition: all 0.2s ease !important;
    }
    .stButton>button:hover {
        background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%) !important;
        color: #ffffff !important;
        transform: translateY(-1px) !important;
    }
    /* 予想馬カード */
    .horse-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 18px;
        border: 1px solid #cbd5e1;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        margin-bottom: 14px;
    }
    .card-honmei { border-left: 6px solid #dc2626; background: #fff5f5; }
    .card-taikou { border-left: 6px solid #059669; background: #f0fdf4; }
    .card-tanana { border-left: 6px solid #2563eb; background: #eff6ff; }

    .badge-honmei { background: #dc2626; color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.85rem; }
    .badge-taikou { background: #059669; color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.85rem; }
    .badge-tanana { background: #2563eb; color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.85rem; }

    .bet-card {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
        margin-bottom: 10px;
    }
    .bet-title { font-weight: 700; font-size: 1.05rem; color: #1e40af; margin-bottom: 6px; }
    .bet-code {
        font-family: monospace; font-size: 1.05rem; background: #f1f5f9;
        padding: 8px 12px; border-radius: 8px; color: #0f172a; font-weight: bold;
        border: 1px solid #cbd5e1; margin: 6px 0; white-space: pre-line; word-break: break-all;
    }
    .calc-card {
        background: #ffffff; border-radius: 12px; padding: 16px;
        border: 1px solid #3b82f6; box-shadow: 0 4px 12px rgba(59, 130, 246, 0.08); margin-top: 12px;
    }
    .sim-card {
        background: #f0fdf4; border-radius: 12px; padding: 16px;
        border: 1px solid #10b981; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.08); margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Parsing Utility
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# Web Scraping & Data Fetching
# ---------------------------------------------------------
def fetch_html(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://race.netkeiba.com/'
    }
    try:
        session = requests.Session()
        session.headers.update(headers)
        res = session.get(url, verify=False, timeout=12)
        if res.status_code != 200: return None, f"アクセスエラー ({res.status_code})"
        html_text = None
        for enc in ['euc-jp', 'euc_jp', 'cp932', 'shift_jis', 'utf-8']:
            try:
                html_text = res.content.decode(enc)
                if 'netkeiba' in html_text or '馬名' in html_text or '出馬' in html_text: break
            except Exception: continue
        if not html_text: html_text = res.content.decode('euc-jp', errors='replace')
        return BeautifulSoup(html_text, 'html.parser'), None
    except Exception as e: return None, f"通信エラー: {e}"

def fetch_race_list_by_date(dt_str):
    clean_date = re.sub(r'\D', '', str(dt_str))
    if len(clean_date) != 8:
        return [], "日付は8桁の数字(YYYYMMDD)で指定してください。"

    venues_found = {}
    urls = [
        f"https://race.netkeiba.com/top/race_list.html?kaijo_date={clean_date}",
        f"https://db.netkeiba.com/race/list/{clean_date}/"
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
            if v_code in VENUE_CODE_TO_NAME:
                prefix = r_id[:10]
                venues_found[prefix] = VENUE_CODE_TO_NAME[v_code]

    # 万が一Webから拾えなくても全競馬場の1R〜12Rを自動補完・選択可能にするフォールバック
    races = []
    if venues_found:
        for prefix, venue_name in venues_found.items():
            for r_num in range(1, 13):
                r_id = f"{prefix}{r_num:02d}"
                races.append({
                    'id': r_id,
                    'name': f"📍【{venue_name}】 {r_num}R",
                    'venue': venue_name,
                    'r_num': r_num
                })
    else:
        # デフォルトフォールバック: 主要競馬場（東京・中山・阪神・京都）の全12Rを生成
        y = clean_date[:4]
        for v_name, v_code in [("東京", "05"), ("中山", "06"), ("阪神", "09"), ("京都", "08")]:
            prefix = f"{y}{v_code}0101"
            for r_num in range(1, 13):
                r_id = f"{prefix}{r_num:02d}"
                races.append({
                    'id': r_id,
                    'name': f"📍【{v_name}】 {r_num}R (想定ID: {r_id})",
                    'venue': v_name,
                    'r_num': r_num
                })

    races.sort(key=lambda x: x['id'])
    return races, None

def parse_db_netkeiba(soup):
    table = soup.select_one('table.race_table_01')
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

        hw_str, hw_diff = "計不", 0
        hw_idx = col_map.get('horse_weight')
        if hw_idx is not None and hw_idx < len(tds):
            txt = tds[hw_idx].text.strip()
            hw_str, hw_diff = parse_horse_weight_str(txt)

        data_list.append({
            '枠番': wakaban, '馬番': umaban, '馬名': horse_name,
            '騎手': jockey_name, '斤量': weight_val,
            '単勝オッズ': odds_val, '人気': pop_val,
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

        wakaban, umaban, odds_val, pop_val = None, None, None, None
        weight_val = 55.0
        hw_str, hw_diff = "計不", 0

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
                    hw_str, hw_diff = p_str, p_diff

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
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for r in rows:
            tds = r.find_all(['td', 'th'])
            if len(tds) >= 4:
                uma_txt = tds[1].text.strip() if len(tds) > 1 else ''
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
# AI Score Engine (血統・展開・オッズ・期待値)
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

        j_score = 7.0 if any(tj in jockey for tj in TOP_JOCKEYS_S) else (4.0 if any(tj in jockey for tj in TOP_JOCKEYS_A) else 1.0)
        j_comment = f"【鞍上】{jockey}"

        blood_score = 5.0
        blood_comment = "【血統】スピード・展開対応力"
        if race_env['condition'] in ['重', '不良', '稍重']:
            if any(kw in horse_name for kw in ["キング", "ゴールド", "ダノン", "ボルド", "パワー", "ロック", "ロベルト"]):
                blood_score = 7.0
                blood_comment = f"【血統特注】道悪({race_env['condition']})パワー巧者型"
            else:
                blood_score = 4.0
                blood_comment = f"【血統】{race_env['condition']}馬場順応"

        bias_score = 2.0
        bias_comment = "馬場フラット"
        if "内伸び" in race_env['bias']:
            if waku in [1, 2, 3]:
                bias_score = 6.0
                bias_comment = f"【バイアス最高】絶好の内枠{waku}枠"
            elif waku in [4, 5]: bias_score = 3.0
            else: bias_score = -2.0; bias_comment = "【バイアス懸念】外枠位置取りロス"
        elif "外伸び" in race_env['bias']:
            if waku in [6, 7, 8]:
                bias_score = 6.0
                bias_comment = f"【バイアス最高】伸び脚活きる外枠{waku}枠"
            else: bias_score = 1.0

        pattern_score = 4.0
        pattern_comment = "展開利順応"
        if race_env['pace'] == 'ハイペース（差し有利）':
            if p_val >= 3 and o_val >= 8.0:
                pattern_score = 7.0
                pattern_comment = "【展開利】ハイペース乱ペース差し一発"
        elif race_env['pace'] == 'スローペース（前残り）':
            if waku <= 4:
                pattern_score = 7.0
                pattern_comment = "【展開利】スロー絶好ポジションマイペース粘り"

        p_status = paddock_status_map.get(uma, "⚪ 普通 (0pt)")
        paddock_score = 8.0 if "絶好調" in p_status else (-4.0 if "太め" in p_status else (-5.0 if "テンション" in p_status else 0.0))

        raw_score = pop_score + odds_score + weight_bonus + j_score + blood_score + bias_score + pattern_score + paddock_score + 5
        score = round(min(99.9, max(10.0, raw_score)), 1)

        # AI想定勝率 & 期待値 (Expected Value) の精密算出
        est_win_prob = round(min(45.0, max(1.0, (score / 100.0) ** 1.8 * 42.0)), 1)
        expected_value = round((est_win_prob / 100.0) * o_val, 2)
        expected_return_pct = int(expected_value * 100)

        d_copy = dict(d)
        d_copy['AI予想スコア'] = score
        d_copy['AI想定勝率'] = f"{est_win_prob}%"
        d_copy['期待値(EV)'] = expected_value
        d_copy['期待回収率'] = f"{expected_return_pct}%"
        d_copy['パドック評価'] = p_status
        d_copy['血統適性'] = blood_comment
        d_copy['バイアス展開'] = f"{bias_comment} / {pattern_comment}"
        scored_items.append(d_copy)

    scored_items.sort(key=lambda x: x['AI予想スコア'], reverse=True)
    mark_list = ['◎ 本命', '◯ 対抗', '▲ 単穴', '△ 連下', '△ 連下', '☆ 穴馬']
    
    for idx, item in enumerate(scored_items):
        mark = mark_list[idx] if idx < len(mark_list) else 'ー'
        item['予想印'] = mark
        o_str = f"{item['単勝オッズ']}倍" if item['単勝オッズ'] != "未確定" else "未確定"
        
        ev_mark = "💥 妙味アリ" if item['期待値(EV)'] >= 1.2 else ("🔥 超高妙味" if item['期待値(EV)'] >= 1.5 else "")

        if idx == 0:
            item['予想根拠'] = f"【AI最高評価】単勝{o_str}。総合指数最高値({item['AI予想スコア']}pt / 勝率想定{item['AI想定勝率']})。{item['血統適性']}。{item['バイアス展開']}。{ev_mark}"
        elif idx == 1:
            item['予想根拠'] = f"【対抗有力】単勝{o_str}。スコア{item['AI予想スコア']}pt。{item['血統適性']}。逆転頭まで警戒。{ev_mark}"
        elif idx == 2:
            item['予想根拠'] = f"【単穴一発】単勝{o_str}。スコア{item['AI予想スコア']}pt。展開一つで突き抜ける爆発力。{ev_mark}"
        elif idx in [3, 4]:
            item['予想根拠'] = f"【連下押さえ】単勝{o_str}。ヒモ枠・相手として必須。{ev_mark}"
        elif idx == 5:
            item['予想根拠'] = f"【穴馬特注】単勝{o_str}。高配当をもたらすキーホース。{ev_mark}"
        else:
            item['予想根拠'] = f"静観評価（スコア {item['AI予想スコア']}pt）"

    scored_items.sort(key=lambda x: x['馬番'] if isinstance(x['馬番'], int) else 99)
    return scored_items

# ---------------------------------------------------------
# Betting Recommendations
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

    all_bets = {
        "馬単（1着固定）": {
            "方式": f"馬単 1着固定 (軸: {h_uma}番)",
            "買い目": f"1着: {h_uma} → 2着: " + ", ".join([str(u) for u in partner_umas[:4]]),
            "点数": f"{len(partner_umas[:4])} 点", "解説": "本命◎1着固定のハイレスポンス王道馬券", "想定オッズ": 14.5
        },
        "馬連（軸流し）": {
            "方式": f"馬連 流し (軸: {h_uma}番)",
            "買い目": f"{h_uma} － " + ", ".join([str(u) for u in partner_umas[:4]]),
            "点数": f"{len(partner_umas[:4])} 点", "解説": "本命軸からの安定感抜群の流し馬券", "想定オッズ": 10.5
        },
        "ワイド（堅実）": {
            "方式": f"ワイド 流し (軸: {h_uma}番)",
            "買い目": f"{h_uma} － " + ", ".join([str(u) for u in partner_umas[:3]]),
            "点数": f"{len(partner_umas[:3])} 点", "解説": "ダブル・トリプル的中も狙える収支安定型", "想定オッズ": 3.8
        },
        "3連複（1頭軸流し）": {
            "方式": f"3連複 1頭軸 (軸: {h_uma}番)",
            "買い目": f"{h_uma} ＝ " + ", ".join([str(u) for u in partner_umas]),
            "点数": f"{len(partner_umas)*(len(partner_umas)-1)//2 if len(partner_umas)>=2 else 1} 点", "解説": "相手をしっかり広げて高配当・万馬券を網羅", "想定オッズ": 28.5
        },
        "3連単（フォーメーション）": {
            "方式": "3連単 フォーメーション",
            "買い目": f"1着: {h_uma}\n2着: {', '.join([str(u) for u in [t_uma, a_uma] if u])}\n3着: {', '.join([str(u) for u in partner_umas])}",
            "点数": f"{max(1, (len([u for u in [t_uma, a_uma] if u]) * (len(partner_umas)-1)))} 点", "解説": "高回収率・ハイリターン特化買い目", "想定オッズ": 85.0
        }
    }
    return all_bets

def calculate_capital_allocation(tickets, total_budget):
    valid_tickets = [t for t in tickets if t.get('odds', 0) > 0]
    if not valid_tickets or total_budget <= 0: return [], 0, 0
    inv_sum = sum(1.0 / t['odds'] for t in valid_tickets)
    synthetic_odds = round(1.0 / inv_sum, 2) if inv_sum > 0 else 0
    results = []
    for t in valid_tickets:
        raw_alloc = total_budget / (t['odds'] * inv_sum)
        alloc_100 = max(100, round(raw_alloc / 100.0) * 100)
        expected_payout = round(alloc_100 * t['odds'])
        expected_profit = expected_payout - total_budget
        results.append({
            '買い目': t['name'], 'オッズ': f"{t['odds']}倍",
            '最適配分金額': f"{alloc_100:,}円", '的中時払戻想定': f"{expected_payout:,}円",
            '的中時推定純利益': f"{'+' if expected_profit > 0 else ''}{expected_profit:,}円",
            '_alloc': alloc_100
        })
    total_allocated = sum(r['_alloc'] for r in results)
    for r in results: del r['_alloc']
    return results, synthetic_odds, total_allocated

def get_race_data(input_id, paddock_status_map=None, race_env=None):
    clean_id = re.sub(r'\D', '', str(input_id))
    if len(clean_id) == 10 and clean_id.startswith(('20', '21', '22', '23', '24', '25', '26')):
        clean_id = '20' + clean_id

    if not clean_id or len(clean_id) != 12:
        return None, "有効な12桁（または10桁）のレースIDを入力してください。"

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
        return None, f"指定されたレースID ({clean_id}) の出馬表データを取得できませんでした。"

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
# UI Core Layout
# ---------------------------------------------------------
st.markdown('<div class="hero-title">🏇 Kuina AI Racing Pro (JRA中央競馬全12R)</div>', unsafe_allow_html=True)

today = datetime.date.today()
target_race_id = None

tab1, tab2, tab3 = st.tabs(["📅 開催日で全12R一括取得", "⚙️ 競馬場・レース番号で全12Rダイレクト指定", "🔢 12桁ID直接入力"])

with tab1:
    col_d1, col_d2 = st.columns([1, 2])
    with col_d1:
        selected_date = st.date_input("開催日を選択:", value=today, key="date_sel_tab1")
        if st.button("🔍 全競馬場のレース一覧を取得"):
            dt_str = selected_date.strftime("%Y%m%d")
            with st.spinner("JRA全12Rデータを収集・生成中..."):
                races, err = fetch_race_list_by_date(dt_str)
                st.session_state['fetched_races'] = races

    with col_d2:
        if 'fetched_races' in st.session_state and st.session_state['fetched_races']:
            race_opts = {f"{r['name']} (ID: {r['id']})": r['id'] for r in st.session_state['fetched_races']}
            sel_label = st.selectbox("🎯 レースを選択してください:", list(race_opts.keys()))
            if sel_label:
                target_race_id = race_opts[sel_label]
        else:
            st.info("👈 左側の「全競馬場のレース一覧を取得」ボタンを押すと、その日の全会場（1R〜12R）が一挙にリスト化されます！")

with tab2:
    st.markdown("##### 📍 競馬場と1R〜12Rのボタンで一瞬で呼び出し")
    c_v, c_y, c_k, c_n = st.columns(4)
    with c_v: venue_sel2 = st.selectbox("競馬場", list(JRA_VENUES.keys()), index=4) # 東京
    with c_y: year_sel2 = st.number_input("年", 2020, 2026, today.year)
    with c_k: kai_sel2 = st.number_input("回", 1, 12, 2)
    with c_n: nichi_sel2 = st.number_input("日目", 1, 12, 12)

    v_code = JRA_VENUES[venue_sel2]
    prefix_id = f"{year_sel2}{v_code}{kai_sel2:02d}{nichi_sel2:02d}"

    st.write(f"**【{venue_sel2}競馬場】のレースを選択 (1R〜12R):**")
    r_cols = st.columns(6)
    r_cols2 = st.columns(6)

    for r in range(1, 7):
        with r_cols[r-1]:
            if st.button(f"{r}R", key=f"btn_r_{r}"):
                target_race_id = f"{prefix_id}{r:02d}"

    for r in range(7, 13):
        with r_cols2[r-7]:
            if st.button(f"{r}R", key=f"btn_r_{r}"):
                target_race_id = f"{prefix_id}{r:02d}"

    st.caption(f"選択中のベースID: `{prefix_id}◯◯`")

with tab3:
    c_m1, c_m2 = st.columns(2)
    with c_m1:
        manual_id = st.text_input("12桁レースID:", value="202405021211")
        if st.button("🚀 この12桁IDでAI解析"):
            target_race_id = manual_id
    with c_m2:
        st.write("📌 サンプルレース一発読み込み:")
        if st.button("🏆 日本ダービー (2024年)"): target_race_id = "202405021211"
        if st.button("🏆 有馬記念 (2023年)"): target_race_id = "202306050811"

# ---------------------------------------------------------
# Results Area
# ---------------------------------------------------------
if target_race_id:
    st.markdown("---")
    if 'paddock_map' not in st.session_state: st.session_state['paddock_map'] = {}

    st.markdown(f"### 🎯 解析対象レースID: `{target_race_id}`")
    st.markdown("#### 🌦️ トラックバイアス・天候・展開ペルソナ調整")
    e1, e2, e3, e4 = st.columns(4)
    with e1: sel_weather = st.selectbox("☀️ 天候", ["晴", "曇", "雨", "小雨"], index=0)
    with e2: sel_condition = st.selectbox("🌿 馬場状態", ["良", "稍重", "重", "不良"], index=0)
    with e3: sel_bias = st.selectbox("🚧 トラックバイアス", ["⚪ フラット", "🟩 内伸び・前残り有利", "🟨 外伸び・差し有利"], index=0)
    with e4: sel_pace = st.selectbox("🏃 展開・ペース予想", ["ミドルペース", "スローペース（前残り）", "ハイペース（差し有利）"], index=0)

    current_race_env = {
        'weather': sel_weather, 'condition': sel_condition,
        'bias': sel_bias, 'pace': sel_pace
    }

    with st.spinner("🤖 AI多角分析エンジン実行中（リアルタイムオッズ・期待値・血統統合中）..."):
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
                        <div style="font-size: 1.4rem; font-weight: 800; margin: 10px 0 6px 0;">{horse['馬番']}番 {horse['馬名']}</div>
                        <p style="color: #2563eb; font-weight: 700; font-size: 1.05rem; margin-bottom: 6px;">
                            AIスコア: {horse['AI予想スコア']} pt (勝率想定: {horse['AI想定勝率']})
                        </p>
                        <p style="margin: 3px 0; color: #334155; font-size: 0.9rem;">
                            単勝オッズ: <strong>{horse['単勝オッズ']}倍</strong> ({horse['人気']}人気) | 期待値(EV): <strong>{horse['期待値(EV)']}</strong>
                        </p>
                        <p style="margin: 4px 0; color: #047857; font-size: 0.85rem;">
                            <strong>血統適性:</strong> {horse['血統適性']}
                        </p>
                        <p style="margin: 4px 0; color: #1e40af; font-size: 0.85rem;">
                            <strong>バイアス展開:</strong> {horse['バイアス展開']}
                        </p>
                        <hr style="border-color: #cbd5e1; margin: 10px 0;">
                        <p style="font-size: 0.88rem; color: #475569; line-height: 1.5;">
                            {horse['予想根拠']}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("### 📋 AI予想・詳細分析＆オッズ期待値一覧")
            
            cols = ['予想印', '枠番', '馬番', '馬名', 'AI予想スコア', 'AI想定勝率', '単勝オッズ', '期待値(EV)', '期待回収率', '騎手', '血統適性', 'バイアス展開', '人気', '馬体重', '予想根拠']
            df_display = df[[c for c in cols if c in df.columns]]

            def highlight_row(val):
                if '◎' in str(val): return 'background-color: #fee2e2; color: #991b1b; font-weight: bold;'
                elif '◯' in str(val): return 'background-color: #d1fae5; color: #065f46; font-weight: bold;'
                elif '▲' in str(val): return 'background-color: #dbeafe; color: #1e40af; font-weight: bold;'
                elif '☆' in str(val): return 'background-color: #fef9c3; color: #854d0e; font-weight: bold;'
                return ''

            st.dataframe(
                df_display.style.map(highlight_row, subset=['予想印']),
                use_container_width=True,
                hide_index=True,
                height=480
            )

            csv = df_display.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 分析結果（CSV）をダウンロード",
                data=csv,
                file_name=f"keiba_ai_{target_race_id}.csv",
                mime="text/csv"
            )
