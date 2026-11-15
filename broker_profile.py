import pandas as pd
import numpy as np

def profiles(data, window=60, min_days=15):
    d=data.copy()
    d['date']=pd.to_datetime(d.date)
    for c in ['buy_qty','sell_qty']:
        d[c]=pd.to_numeric(d[c],errors='raise')
        if (d[c]<0).any(): raise ValueError('成交股數不可為負')
    d=d.groupby(['broker','stock','date'],as_index=False)[['buy_qty','sell_qty']].sum()
    d['gross']=d.buy_qty+d.sell_qty
    d['net']=d.buy_qty-d.sell_qty
    out=[]
    for broker,b in d.groupby('broker'):
        dates=sorted(b.date.unique())
        for day in dates:
            w=b[(b.date<=day)&(b.date>pd.Timestamp(day)-pd.Timedelta(days=window))]
            total=w.gross.sum()
            for stock,g in w.groupby('stock'):
                if g.date.nunique()<min_days or g.gross.sum()<=0: continue
                gross=g.gross.sum()
                concentration=gross/total
                accumulation=g.net.sum()/gross
                positive=(g.net>0).mean()
                # Same-day gross offset is not proof of matched trades.
                offset=2*np.minimum(g.buy_qty,g.sell_qty).sum()/gross
                score=100*(.4*concentration+.35*max(0,accumulation)+.25*positive)
                label='長期累積型' if accumulation>=.35 and positive>=.65 else '高周轉型' if offset>=.65 else '波段型候選' if abs(accumulation)>=.15 else '混合／不明'
                out.append(dict(date=day,broker=broker,stock=stock,active_days=g.date.nunique(),concentration=concentration,accumulation=accumulation,positive_days=positive,gross_offset=offset,accumulation_score=score,profile=label,company_affiliation='未確認'))
    return pd.DataFrame(out)

def profile_signals(data, min_lots=500, window=60):
    if 'available_date' not in data: raise ValueError('回測需要實際公布日 available_date')
    d=data.copy()
    d['date']=pd.to_datetime(d.date)
    d['available_date']=pd.to_datetime(d.available_date)
    if (d.available_date<d.date).any(): raise ValueError('公布日不得早於交易日')
    for c in ['buy_qty','sell_qty']: d[c]=pd.to_numeric(d[c])
    # Build snapshots from data already available on each publication date.
    out=[]
    for day,g in d.groupby('available_date'):
        p=profiles(d[d.available_date<=day],window)
        if p.empty: continue
        p=p.sort_values('date').drop_duplicates(['broker','stock'],keep='last')
        q=g.groupby(['broker','stock'],as_index=False)[['buy_qty','sell_qty']].sum()
        q=q.merge(p[['broker','stock','profile']],on=['broker','stock'])
        q=q[q.buy_qty-q.sell_qty>=min_lots*1000].copy()
        q['available_date']=day
        q['strategy']='分點行為｜'+q.profile
        out.append(q[['stock','available_date','strategy']])
    return pd.concat(out,ignore_index=True) if out else pd.DataFrame(columns=['stock','available_date','strategy'])
