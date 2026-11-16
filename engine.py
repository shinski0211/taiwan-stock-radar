"""VCP scan and broker-branch estimates.

The arithmetic matches the previous ``app.py``. Do not change the breakout
conditions or the cost pairing.
"""

import numpy as np
import pandas as pd


def scan(frame, seg, require_rs):
    frame = frame.copy()
    frame['date'] = pd.to_datetime(frame.date)
    frame = frame.sort_values('date')
    index = frame[frame.stock == 'TSE'].set_index('date').close
    rows = []
    for stock, group in frame.groupby('stock'):
        if stock == 'TSE' or len(group) < max(251, 3 * seg + 1):
            continue
        group = group.sort_values('date')
        latest = group.iloc[-1]
        prior = group.iloc[:-1]
        close = group.close

        def moving_average(window):
            return close.iloc[-window:].mean()

        low = group.low.iloc[-250:].min()
        high = group.high.iloc[-250:].max()
        trend = (
            latest.close > moving_average(50) > moving_average(150) > moving_average(200)
            and moving_average(200) > close.iloc[-220:-20].mean()
            and latest.close >= low * 1.3
            and latest.close >= high * 0.75
        )
        chunks = [
            prior.iloc[-3 * seg:-2 * seg],
            prior.iloc[-2 * seg:-seg],
            prior.iloc[-seg:],
        ]
        depths = [100 * (chunk.high.max() - chunk.low.min()) / chunk.high.max() for chunk in chunks]
        pivot = chunks[-1].high.max()
        average_volume = prior.volume.tail(50).mean()
        dry = prior.volume.tail(10).mean() / average_volume if average_volume > 0 else np.nan
        volume_ratio = latest.volume / average_volume if average_volume > 0 else np.nan
        roc = close.iloc[-1] / close.iloc[-251] - 1
        market = index.reindex([group.date.iloc[-251], latest.date])
        market_return = market.iloc[1] / market.iloc[0] - 1 if len(market) == 2 else np.nan
        if not trend or (require_rs and not (roc >= market_return)):
            continue
        contract = depths[0] >= 10 and depths[0] > depths[1] > depths[2] and depths[2] <= 10
        setup = contract and dry < 0.7
        breakout = setup and close.iloc[-2] <= pivot < latest.close and volume_ratio > 1.5 and latest.volume >= 500
        if breakout:
            status = '突破確認'
        elif setup and 0.95 * pivot <= latest.close <= pivot:
            status = '突破預警'
        elif setup:
            status = '潛伏觀察'
        else:
            status = '強勢股'
        rows.append({
            '代號': stock,
            '日期': str(latest.date.date()),
            '階段': status,
            '樞紐價': pivot,
            '末段收縮%': round(depths[-1], 2),
            '量縮比': round(dry, 2),
            '突破量比': round(volume_ratio, 2),
            '排序': {'突破確認': 0, '突破預警': 1, '潛伏觀察': 2, '強勢股': 3}[status],
        })
    if not rows:
        return pd.DataFrame(columns=['代號', '階段'])
    return pd.DataFrame(rows).sort_values('排序')


def branch(frame, broker, fee, tax):
    frame = frame[frame.broker == broker].sort_values('date')
    rows = []
    for stock, group in frame.groupby('stock'):
        quantity = cost = 0.0
        previous_buy = 0.0
        for _, row in group.iterrows():
            sold = min(quantity, row.sell_qty)
            average = cost / quantity if quantity else 0.0
            pnl = sold * (row.sell_price * (1 - fee - tax) - average)
            quantity -= sold
            cost -= sold * average
            unknown = row.sell_qty - sold
            quantity += row.buy_qty
            cost += row.buy_qty * row.buy_price * (1 + fee)
            rows.append({
                '日期': row.date,
                '股票': stock,
                '估算剩餘股數': quantity,
                '估算均價': cost / quantity if quantity else 0,
                '已配對估算損益': pnl,
                '未配對賣出股數': unknown,
                '前筆買量對應賣出比例': min(sold / previous_buy, 1) if previous_buy else None,
            })
            previous_buy = row.buy_qty
    return pd.DataFrame(rows)
