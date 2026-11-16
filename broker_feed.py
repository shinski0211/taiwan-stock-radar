"""Broker-branch trades from FinMind's documented daily-report API.

Official TWSE and TPEx branch reports require a captcha or a robot check.
This module does not solve those. Without a Sponsor token it stops and
explains why.
"""

import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

ENDPOINT = 'https://api.finmindtrade.com/api/v4/taiwan_stock_trading_daily_report'
DEFAULT_CACHE = Path(__file__).resolve().parent / '.cache' / 'broker_reports.sqlite'
MAX_STOCKS = 5
MAX_DAYS = 60
PAUSE_SECONDS = 0.4
SOURCE_NOTE = (
    '分點買賣日報沒有免驗證碼的官方下載。'
    '證交所查詢要圖形驗證碼，櫃買中心查詢前要驗證非機器人，這個程式不會破解。'
    '可改用你自己的 FinMind Sponsor token：環境變數 FINMIND_TOKEN，'
    '或 .streamlit/secrets.toml 的 FINMIND_TOKEN。'
    '資料自 2021-06-30 起，一天一檔一次，僅供 token 持有人自己使用。'
)


class BrokerSourceError(Exception):
    pass


def read_token():
    token = os.environ.get('FINMIND_TOKEN', '').strip()
    if token:
        return token
    try:
        import streamlit as st
        return str(st.secrets.get('FINMIND_TOKEN', '')).strip()
    except Exception:
        return ''


def recent_weekdays(count, today=None):
    if count < 1 or count > MAX_DAYS:
        raise BrokerSourceError(f'交易日數必須介於 1 與 {MAX_DAYS}。')
    anchor = today or datetime.now(ZoneInfo('Asia/Taipei')).date()
    found = []
    cursor = anchor - timedelta(days=1)
    while len(found) < count:
        if cursor.weekday() < 5:
            found.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return list(reversed(found))


def parse_stocks(text):
    stocks = []
    for item in str(text).replace('，', ',').split(','):
        code = item.strip().upper().split('.')[0]
        if code and code not in stocks:
            stocks.append(code)
    if not stocks:
        raise BrokerSourceError('請輸入至少一個股票代號。')
    if len(stocks) > MAX_STOCKS:
        raise BrokerSourceError(f'一次最多 {MAX_STOCKS} 檔，以免連續請求過於頻繁。')
    return stocks


def rows_from_payload(rows):
    frame = pd.DataFrame(rows)
    if frame.empty:
        return _empty()
    for column in ('buy', 'sell', 'price'):
        frame[column] = pd.to_numeric(frame[column], errors='coerce').fillna(0)
    frame['stock'] = frame['stock_id'].astype(str).str.strip()
    frame['date'] = frame['date'].astype(str).str.slice(0, 10)
    frame['broker_id'] = frame['securities_trader_id'].astype(str).str.strip()
    frame['broker'] = frame['securities_trader'].astype(str).str.strip()
    grouped = []
    keys = ['stock', 'date', 'broker_id']
    for key, part in frame.groupby(keys, sort=False):
        buy_qty = float(part['buy'].sum())
        sell_qty = float(part['sell'].sum())
        grouped.append({
            'date': key[1],
            'stock': key[0],
            'broker_id': key[2],
            'broker': part['broker'].iloc[-1],
            'buy_qty': buy_qty,
            'sell_qty': sell_qty,
            'buy_price': _weighted(part, 'buy'),
            'sell_price': _weighted(part, 'sell'),
            'available_date': key[1],
        })
    return pd.DataFrame(grouped)


def _weighted(part, column):
    traded = part[part[column] > 0]
    priced = traded[traded['price'] > 0]
    if priced.empty or priced[column].sum() <= 0:
        return 0.0
    return float((priced['price'] * priced[column]).sum() / priced[column].sum())


def _empty():
    return pd.DataFrame(columns=['date', 'stock', 'broker', 'buy_qty', 'sell_qty', 'buy_price', 'sell_price', 'available_date'])


def rejection_message(body):
    message = str((body or {}).get('msg') or '')
    lowered = message.lower()
    if 'user level' in lowered or 'sponsor' in lowered:
        return 'FinMind 回覆這個 token 沒有分點資料權限（需要 Sponsor）。沒有改走驗證碼網站。'
    if 'token' in lowered or 'auth' in lowered:
        return 'FinMind 拒絕這個 token。'
    if message:
        return '分點資料取得失敗：' + message[:180]
    return '分點資料取得失敗。'


def _connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute(
        '''CREATE TABLE IF NOT EXISTS reports (
            stock TEXT, date TEXT, broker_id TEXT, broker TEXT,
            buy_qty REAL, sell_qty REAL, buy_price REAL, sell_price REAL,
            PRIMARY KEY (stock, date, broker_id)
        )'''
    )
    db.execute('CREATE TABLE IF NOT EXISTS fetched (stock TEXT, date TEXT, PRIMARY KEY (stock, date))')
    return db


def _cached(db, stock, day):
    row = db.execute('SELECT 1 FROM fetched WHERE stock=? AND date=?', (stock, day)).fetchone()
    return row is not None


def _store(db, stock, day, frame):
    db.execute('DELETE FROM reports WHERE stock=? AND date=?', (stock, day))
    if not frame.empty:
        db.executemany(
            '''INSERT INTO reports
               (stock, date, broker_id, broker, buy_qty, sell_qty, buy_price, sell_price)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            [
                (row.stock, row.date, row.broker_id, row.broker, row.buy_qty, row.sell_qty, row.buy_price, row.sell_price)
                for row in frame.itertuples(index=False)
            ],
        )
    db.execute('INSERT OR REPLACE INTO fetched (stock, date) VALUES (?, ?)', (stock, day))
    db.commit()


def _read(db, stocks, dates):
    marks = ','.join('?' for _ in stocks)
    days = ','.join('?' for _ in dates)
    query = f'''SELECT date, stock, broker, buy_qty, sell_qty, buy_price, sell_price, date AS available_date
                FROM reports WHERE stock IN ({marks}) AND date IN ({days})
                ORDER BY date, stock, broker'''
    found = pd.read_sql_query(query, db, params=[*stocks, *dates])
    return found if not found.empty else _empty()


def collect(stocks, dates, token, cache_path, transport=None, pause=PAUSE_SECONDS):
    if not token:
        raise BrokerSourceError(SOURCE_NOTE)
    stocks = parse_stocks(','.join(stocks))
    if len(dates) > MAX_DAYS:
        raise BrokerSourceError(f'一次最多 {MAX_DAYS} 個交易日。')
    caller = transport or _request
    db = _connect(cache_path)
    try:
        for stock in stocks:
            for day in dates:
                if _cached(db, stock, day):
                    continue
                status, body = caller(stock, day, token)
                data = (body or {}).get('data')
                ok = status == 200 and isinstance(data, list)
                if not ok:
                    raise BrokerSourceError(rejection_message(body))
                _store(db, stock, day, rows_from_payload(data))
                if pause:
                    time.sleep(pause)
        return _read(db, stocks, dates)
    finally:
        db.close()


def _request(stock, day, token):
    response = requests.get(
        ENDPOINT,
        params={'data_id': stock, 'date': day},
        headers={'Authorization': f'Bearer {token}', 'User-Agent': 'TaiwanStockRadar/0.11'},
        timeout=(5, 12),
    )
    try:
        body = response.json()
    except ValueError:
        body = {'msg': response.text[:180]}
    return response.status_code, body


def collect_recent(stock_text, count, token, cache_path, today=None, transport=None, pause=PAUSE_SECONDS):
    return collect(parse_stocks(stock_text), recent_weekdays(count, today), token, cache_path, transport, pause)
