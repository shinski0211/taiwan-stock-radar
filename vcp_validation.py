import pandas as pd
import numpy as np

def comparison_events(prices, require_rs=True):
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
        early=trend&setup&(c<=hi)&(c>=.95*hi)
        plain=trend&(c.shift(1)<=hi)&(c>hi)&(v>1.5*avg)&(v>=500)
        if require_rs:
            rs=c.pct_change(250,fill_method=None)>=ix.reindex(g.index).pct_change(250,fill_method=None)
            early &= rs
            plain &= rs
        early=early & ~early.shift(1,fill_value=False)
        for label,mask in [('VCP early',early),('VCP breakout',signal),('Plain breakout',plain)]:
            for day in g.index[mask.fillna(False)]:
                out.append(dict(stock=stock,available_date=day,strategy=label))
    return pd.DataFrame(out,columns=['stock','available_date','strategy'])


if __name__=='__main__':
    import sys, yfinance as yf
    from backtest import run
    tickers=['2330.TW','2317.TW','2454.TW','2308.TW','2382.TW','2383.TW','2313.TW','2303.TW','3231.TW','2379.TW','3034.TW','3661.TW','6669.TW','2345.TW','3017.TW','5274.TWO','3529.TWO','6488.TWO','6147.TWO','8299.TWO','^TWII']
    frames=[]; failed=[]
    for ticker in tickers:
        try:
            g=yf.download(ticker,start='2022-09-01',end='2026-11-15',auto_adjust=True,progress=False,threads=False)
            if isinstance(g.columns,pd.MultiIndex): g.columns=g.columns.get_level_values(0)
            g=g.rename(columns=str.lower).dropna(subset=['open','high','low','close','volume']).reset_index()
            if len(g)<270: raise ValueError('insufficient history')
            g=g.rename(columns={g.columns[0]:'date'})
            g['stock']='TSE' if ticker=='^TWII' else ticker.split('.')[0]
            g['volume']/=1000
            frames.append(g)
        except Exception as e:
            failed.append(ticker); print(ticker,e)
    print('Failed:',failed)
    if not frames or '^TWII' in failed: sys.exit('Missing required data')
    p=pd.concat(frames,ignore_index=True)
    s=comparison_events(p)
    s=s[s.available_date>=pd.Timestamp('2023-11-15')]
    summary,trades=run(p,s,horizons=(5,10,20))
    if trades.empty: sys.exit('No signals')
    ix=p[p.stock=='TSE'].set_index('date')
    trades['benchmark']=trades.exit_date.map(ix.close)/trades.entry_date.map(ix.open)-1
    trades['excess']=trades.net_return-trades.benchmark
    extra=trades.groupby(['strategy','days']).excess.agg(['mean','count']).reset_index()
    extra['mean']*=100
    summary=summary.merge(extra.rename(columns={'mean':'excess_pct','count':'benchmark_samples'}),on=['strategy','days'])
    print(summary.to_string(index=False))
    summary.to_csv('vcp_summary.csv',index=False)
    trades.to_csv('vcp_trades.csv',index=False)
