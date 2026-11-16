"""Robot supply-chain list. Edit config/robot_supply_chain.toml to change it."""

import re
import tomllib
from pathlib import Path

import pandas as pd
import streamlit as st

from data_access import load
from present import build_board, load_frames, show_frame

ROOT = Path(__file__).resolve().parent
DEFAULT_PATH = ROOT / 'config' / 'robot_supply_chain.toml'
FIELDS = (
    'segment',
    'name',
    'code',
    'role',
    'robot_revenue_share',
    'share_source_url',
    'share_as_of',
    'optimus_tie',
    'note',
)
TIES = {'媒體報導', '傳聞', '無'}
UNDISCLOSED = '未揭露'


def load_companies(path=None):
    source = Path(path) if path else DEFAULT_PATH
    payload = tomllib.loads(source.read_text(encoding='utf-8'))
    rows = payload.get('company') or []
    if not rows:
        raise ValueError('機器人供應鏈設定是空的')
    cleaned = []
    for index, row in enumerate(rows, start=1):
        missing = [field for field in FIELDS if field not in row]
        if missing:
            raise ValueError(f'第 {index} 列缺少欄位：{", ".join(missing)}')
        code = str(row['code']).strip()
        if not re.fullmatch(r'\d{4}', code):
            raise ValueError(f'第 {index} 列代號必須是四位數字：{code}')
        tie = str(row['optimus_tie']).strip()
        if tie not in TIES:
            raise ValueError(f'第 {index} 列 Optimus 關聯只能是 {"、".join(sorted(TIES))}')
        share = str(row['robot_revenue_share']).strip()
        url = str(row['share_source_url']).strip()
        as_of = str(row['share_as_of']).strip()
        if share != UNDISCLOSED and not (url and as_of):
            raise ValueError(f'{row["name"]} 的占比需要來源網址與日期')
        cleaned.append({
            'segment': str(row['segment']).strip(),
            'name': str(row['name']).strip(),
            'code': code,
            'role': str(row['role']).strip(),
            'robot_revenue_share': share,
            'share_source_url': url,
            'share_as_of': as_of,
            'optimus_tie': tie,
            'note': str(row['note']).strip(),
        })
    return cleaned


def quote_lookup():
    frames, _notes = load_frames('上市＋上櫃', load)
    board, _mismatch = build_board(frames)
    if '漲幅%' not in getattr(board, 'columns', []):
        return {}
    quotes = {}
    for _, row in board.iterrows():
        quotes[str(row['Code'])] = (row['ClosingPrice'], row['漲幅%'])
    return quotes


def companies_frame(companies, quotes):
    records = []
    for company in companies:
        close, change = quotes.get(company['code'], (None, None))
        records.append({
            '名稱': company['name'],
            '代號': company['code'],
            '環節': company['segment'],
            '角色': company['role'],
            '機器人營收占比': company['robot_revenue_share'],
            '占比來源': company['share_source_url'],
            'Optimus 關聯': company['optimus_tie'],
            '收盤': close,
            '漲跌幅': change,
            '備註': company['note'],
        })
    return pd.DataFrame.from_records(records)


def render_robots():
    st.header('機器人供應鏈')
    st.caption('多數公司的機器人營收占比很小或未揭露。Optimus 關聯多半是媒體報導或傳聞，未經公司確認，不是投資建議。')
    companies = load_companies()
    segments = ['全部'] + list(dict.fromkeys(company['segment'] for company in companies))
    selected = st.selectbox('環節', segments, key='robot_segment')
    if selected != '全部':
        companies = [company for company in companies if company['segment'] == selected]
    try:
        quotes = quote_lookup()
    except Exception as error:
        quotes = {}
        st.warning(f'行情暫時無法併入：{error}')
    if not quotes:
        st.caption('這次沒有併入收盤價。')
    table = companies_frame(companies, quotes)
    show_frame(
        table,
        column_config={
            '代號': st.column_config.TextColumn('代號', width='small'),
            '名稱': st.column_config.TextColumn('名稱', width='small'),
            '收盤': st.column_config.NumberColumn('收盤', format='%.2f'),
            '漲跌幅': st.column_config.NumberColumn('漲跌幅', format='%+.2f%%'),
            '占比來源': st.column_config.TextColumn('占比來源', width='medium'),
            '備註': st.column_config.TextColumn('備註', width='medium'),
        },
        signed=('漲跌幅',),
    )
    st.caption('清單在 config/robot_supply_chain.toml，改完重新整理即可。收盤與漲跌幅沿用每日行情的上市、上櫃收盤。')
