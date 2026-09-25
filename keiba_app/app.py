import re
import pandas as pd
import numpy as np

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
        raise ValueError(f"出馬表テーブルが見つかりませんでした (Race ID: {race_id})。")

    # 2. ページ上の表記頭数を取得 (頭数照合用)
    page_text = soup.get_text()
    head_count_match = re.search(r'(\d{1,2})\s*頭', page_text)
    expected_head_count = int(head_count_match.group(1)) if head_count_match else None

    # 3. 出走馬の行要素のみを抽出 (除外馬・ノイズ行の除外)
    rows = table.select('tr.HorseList')
    if not rows:
        all_trs = table.find_all('tr')
        rows = [tr for tr in all_trs if tr.select_one('a[href*="/horse/"]')]

    if not rows:
        raise ValueError(f"出馬表テーブル内に有効な競走馬データ行が見つかりませんでした (Race ID: {race_id})。")

    parsed_rows = []

    for idx, r in enumerate(rows, start=1):
        if 'Cancel' in r.get('class', []) or r.select_one('.Cancel'):
            continue

        tds = r.find_all(['td', 'th'])
        if len(tds) < 2:
            continue

        # A. 馬番 (horse_number)
        horse_num = None
        uma_td = r.select_one('td[class*="Umaban"]') or r.select_one('td.txt_c')
        if uma_td:
            txt = clean_text(uma_td)
            if txt.isdigit(): horse_num = int(txt)

        # B. 馬名 (horse_name)
        horse_name = None
        horse_a = r.select_one('span.HorseName a') or r.select_one('td.HorseInfo a[href*="/horse/"]')
        if horse_a:
            horse_name = clean_text(horse_a)
            horse_name = re.sub(r'\\(.*?\\)', '', horse_name).strip()

        # C. 性齢 (sex_age)
        sex_age = None
        barei_el = r.select_one('td.Barei') or r.select_one('span.Barei')
        if barei_el:
            sex_age = clean_text(barei_el)

        # D. 斤量 (weight) - デフォルト補完せずNaN扱い
        weight = None
        for td in tds:
            classes = [c.lower() for c in td.get('class', [])]
            txt = clean_text(td)
            if any(k in c for k in ['jockey', 'kinryo', 'weight', 'txt_c']):
                m = re.search(r'^([456]\d(?:\.\d)?)$', txt)
                if m:
                    weight = float(m.group(1))
                    break

        # E. 騎手 (jockey)
        jockey = None
        jockey_a = r.select_one('td.Jockey a') or r.select_one('a[href*="/jockey/"]')
        if jockey_a:
            jockey = clean_text(jockey_a)
            jockey = re.sub(r'^[▲☆◇△◯▲\d\s]+', '', jockey).strip()

        # F. 人気 (popularity) - デフォルト補完せずNaN扱い
        popularity = None
        pop_el = r.select_one('td.Popular') or r.select_one('span[id^="ninki-"]')
        if pop_el:
            txt = clean_text(pop_el)
            m = re.search(r'(\d+)', txt)
            if m: popularity = int(m.group(1))

        # G. オッズ (odds) - デフォルト20.0補完せずNaN扱い
        odds = None
        odds_el = r.select_one('td.Odds') or r.select_one('span[id^="odds-"]')
        if odds_el:
            txt = clean_text(odds_el)
            m = re.search(r'(\d+\.\d+|\d+)', txt)
            if m:
                try: odds = float(m.group(1))
                except ValueError: odds = None

        # 必須項目 (馬番・馬名) の欠損チェック -> 欠損時は即座にエラー停止
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

    return df
