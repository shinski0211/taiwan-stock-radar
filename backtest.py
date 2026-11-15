import pandas as pd
import numpy as np

def run(prices, signals, horizons=(1,3,5,10,20,60), fee=.001425, tax=.003):
    p=prices.copy()
    s=signals.copy()
    for f in (p,s):
        f['stock']=f.stock.astype(str)
    p['date']=pd.to_datetime(p.date).dt.normalize()
    s['available_date']=pd.to_datetime(s.available_date).dt.normalize()
    p=p.drop_duplicates(['stock','date']).sort_values('date')
    s=s.drop_duplicates(['stock','available_date','strategy'])
    groups={k:g.reset_index(drop=True) for k,g in p.groupby('stock')}
    rows=[]
    for r in s.itertuples():
        g=groups.get(r.stock)
        if g is None: continue
        i=g.date.searchsorted(r.available_date,side='right')
        if i>=len(g): continue
        entry=float(g.open.iloc[i])
        if not np.isfinite(entry) or entry<=0: continue
        for h in horizons:
            j=i+h-1
            if j>=len(g): continue
            exit=float(g.close.iloc[j])
            if not np.isfinite(exit) or exit<=0: continue
            ret=exit*(1-fee-tax)/(entry*(1+fee))-1
            rows.append(dict(stock=r.stock,strategy=r.strategy,available_date=r.available_date,entry_date=g.date.iloc[i],exit_date=g.date.iloc[j],days=h,net_return=ret))
    trades=pd.DataFrame(rows)
    if trades.empty: return trades,trades
    summary=trades.groupby(['strategy','days']).net_return.agg(samples='size',mean='mean',median='median',win_rate=lambda x:(x>0).mean()).reset_index()
    for col in ['mean','median','win_rate']: summary[col]*=100
    return summary,trades

def chips(brokers, holders, min_lots=500, min_change=.5):
    frames=[]
    if brokers is not None:
        b=brokers.copy()
        b['net_lots']=(pd.to_numeric(b.buy_qty)-pd.to_numeric(b.sell_qty))/1000
        for label,mask in [('分點買超',b.net_lots>=min_lots),('分點賣超',b.net_lots<=-min_lots)]:
            q=b.loc[mask,['stock','available_date']].copy()
            q['strategy']=label+'｜'+b.loc[mask,'broker'].astype(str)
            frames.append(q)
    if holders is not None:
        h=holders.copy()
        h['available_date']=pd.to_datetime(h.available_date)
        h=h.sort_values('available_date').drop_duplicates(['stock','available_date'])
        for col in ['pct400','pct1000']:
            h[col]=pd.to_numeric(h[col])
            d=h.groupby('stock')[col].diff()
            for label,mask in [('增加',d>=min_change),('減少',d<=-min_change)]:
                q=h.loc[mask,['stock','available_date']].copy()
                q['strategy']=col+' '+label
                frames.append(q)
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=['stock','available_date','strategy'])
