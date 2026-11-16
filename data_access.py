"""Public-source downloads used by the radar. Fetching rules are unchanged."""

import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


@st.cache_data(ttl=300)
def get(url):
    response = requests.get(url, timeout=40)
    response.raise_for_status()
    return pd.DataFrame(response.json())


@st.cache_data(ttl=300)
def institutional():
    today = datetime.now(ZoneInfo('Asia/Taipei')).date()
    for offset in range(10):
        day = today - timedelta(days=offset)
        if day.weekday() > 4:
            continue
        response = requests.get(
            'https://www.twse.com.tw/rwd/zh/fund/T86',
            params={'date': day.strftime('%Y%m%d'), 'selectType': 'ALLBUT0999', 'response': 'json'},
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get('data') and payload.get('fields'):
            return pd.DataFrame(payload['data'], columns=payload['fields']), day.isoformat()
    raise ValueError('最近十日無法人資料')


def load(url):
    try:
        return get(url)
    except Exception as error:
        st.warning(f'資料取得失敗：{error}')
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def stock_choices():
    options = {}
    sources = [
        ('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL', 'Code', 'Name'),
        ('https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes', 'SecuritiesCompanyCode', 'CompanyName'),
    ]
    for url, code_column, name_column in sources:
        try:
            quotes = get(url)
        except Exception:
            continue
        for _, row in quotes.iterrows():
            code = str(row[code_column]).strip()
            if len(code) == 4 and code.isdigit():
                options[code] = str(row.get(name_column, code))
    return options


@st.cache_data(ttl=300)
def tdcc():
    response = requests.get(
        'https://opendata.tdcc.com.tw/getOD.ashx?id=1-5',
        headers={'User-Agent': 'Mozilla/5.0'},
        timeout=40,
    )
    response.raise_for_status()
    return pd.read_csv(io.BytesIO(response.content), encoding='utf-8-sig', dtype=str)
