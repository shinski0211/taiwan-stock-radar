import pandas as pd
import numpy as np

def vcp_events(prices, require_rs=True):
    p=prices.copy()
    p['date']=pd.to_datetime(p.date).dt.normalize()
    p=p.sort_values('date').drop_duplicates(['stock','date'])
    ix=p[p.stock=='TSE'].set_index('date').close
    out=[]
    for stock,g in p.groupby('stock'):
        if stock=='TSE': continue
        g=g.set_index('date').sort_index()
        c=g.close; v=g.volume
        m50=c.rolling(50).mean(); m150=c.rolling(150).mean(); m200=c.rolling(200).mean()
        trend=(c>m50)&(m50>m150)&(m150>m200)&(m200>m200.shift(20))&(c>=1.3*g.low.rolling(250).min())&(c>=.75*g.high.rolling(250).max())
        hi=g.high.shift(1).rolling(25).max(); lo=g.low.shift(1).rolling(25).min()
        depth=(hi-lo)/hi
        avg=v.shift(1).rolling(50).mean()
        setup=(depth.shift(50)>=.10)&(depth.shift(50)>depth.shift(25))&(depth.shift(25)>depth)&(depth<=.10)&(v.shift(1).rolling(10).mean()<.7*avg)
        signal=trend&setup&(c.shift(1)<=hi)&(c>hi)&(v>1.5*avg)&(v>=500)
        if require_rs: signal &= c.pct_change(250,fill_method=None)>=ix.reindex(g.index).pct_change(250,fill_method=None)
        for day in g.index[signal.fillna(False)]:
            out.append(dict(stock=stock,available_date=day,strategy='VCP 突破'))
    return pd.DataFrame(out,columns=['stock','available_date','strategy'])

def confluence(signals, lookback=14):
    s=signals.copy()
    s['available_date']=pd.to_datetime(s.available_date).dt.normalize()
    out=[]
    for stock,g in s.groupby('stock'):
        g=g.sort_values('available_date')
        for day,now in g.groupby('available_date'):
            w=g[(g.available_date<=day)&(g.available_date>=day-pd.Timedelta(days=lookback))]
            labels=w.strategy.astype(str)
            b=labels.str.startswith('分點買超').any()
            h=labels.isin(['pct400 增加','pct1000 增加']).any()
            v=now.strategy.eq('VCP 突破').any()
            fresh=now.strategy.astype(str).str.startswith('分點買超').any() or now.strategy.isin(['pct400 增加','pct1000 增加']).any()
            if b and h and fresh: out.append((stock,day,'分點買超＋大戶增加'))
            if b and h and v: out.append((stock,day,'分點買超＋大戶增加＋VCP'))
    return pd.DataFrame(out,columns=['stock','available_date','strategy']).drop_duplicates()
