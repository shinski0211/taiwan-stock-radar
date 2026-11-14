import pandas as pd
import streamlit as st
import yfinance as yf
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

@st.cache_data(ttl=86400)
def history(symbols):
    frames=[]
    failures=[]
    end=datetime.now(ZoneInfo('Asia/Taipei')).date()+timedelta(days=1)
    for i in range(0,len(symbols),25):
        batch=symbols[i:i+25]
        try:
            data=yf.download(batch,start=end-timedelta(days=550),end=end,auto_adjust=True,group_by='ticker',threads=4,progress=False,timeout=20)
        except Exception:
            failures.extend(batch)
            continue
        for ticker in batch:
            try:
                g=data[ticker].copy() if isinstance(data.columns,pd.MultiIndex) else data.copy()
                g=g.dropna(subset=['Close','High','Low'])
                if len(g)<251:
                    failures.append(ticker)
                    continue
                g=g.rename(columns=str.lower).reset_index()
                g=g.rename(columns={g.columns[0]:'date'})
                g['stock']='TSE' if ticker=='^TWII' else ticker.split('.')[0]
                g['volume']=g['volume']/1000
                frames.append(g[['stock','date','open','high','low','close','volume']])
            except Exception:
                failures.append(ticker)
    return (pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(),failures)
