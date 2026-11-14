import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from market_history import history
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
st.set_page_config(page_title='台股主力籌碼雷達',layout='wide')
st.title('台股主力籌碼雷達')
st.caption('V0.3｜公開資料與自備歷史資料｜非即時交易訊號')
@st.cache_data(ttl=300)
def get(url):
 r=requests.get(url,timeout=40); r.raise_for_status(); return pd.DataFrame(r.json())
@st.cache_data(ttl=300)
def institutional():
 today=datetime.now(ZoneInfo('Asia/Taipei')).date()
 for i in range(10):
  day=today-timedelta(days=i)
  if day.weekday()>4: continue
  response=requests.get('https://www.twse.com.tw/rwd/zh/fund/T86',params={'date':day.strftime('%Y%m%d'),'selectType':'ALLBUT0999','response':'json'},headers={'User-Agent':'Mozilla/5.0'},timeout=25)
  response.raise_for_status(); obj=response.json()
  if obj.get('data') and obj.get('fields'): return pd.DataFrame(obj['data'],columns=obj['fields']),day.isoformat()
 raise ValueError('最近十日無法人資料')
def load(url):
 try: return get(url)
 except Exception as e: st.warning(f'資料取得失敗：{e}'); return pd.DataFrame()
def csv(label):
 f=st.file_uploader(label,type='csv'); return pd.read_csv(f,dtype={'stock':str,'broker':str}) if f else None
stock=st.sidebar.text_input('股票代號','2313')
if st.sidebar.button('立即重新抓取'): st.cache_data.clear(); st.rerun()
@st.fragment(run_every='5m')
def dashboard():
 a,b,c,d=st.tabs(['每日行情與法人','集保大戶','VCP 全市場','券商分點'])
 with a:
  for title,url in [('上市每日行情','https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL'),]:
   st.subheader(title); df=load(url)
   if not df.empty:
    mask=df.astype(str).eq(stock).any(axis=1); st.dataframe(df[mask] if mask.any() else df.iloc[0:0],hide_index=True); st.caption('日期依來源欄位。')
  st.subheader('上市三大法人')
  try:
   df,day=institutional(); st.caption('資料日期：'+day); sub=df[df.iloc[:,0].astype(str).str.strip()==stock]; st.dataframe(sub,hide_index=True)
   if sub.empty: st.info('此代號無上市法人資料')
  except Exception as e: st.warning(f'法人資料取得失敗：{e}')
 with b:
  try:
   r=tdcc(); sub=r[r['證券代號'].astype(str)==stock]; st.dataframe(sub,hide_index=True)
   for n in [12,15]:
    vals=pd.to_numeric(sub.loc[pd.to_numeric(sub['持股分級'],errors='coerce').between(n,15),'占集保庫存數比例%'],errors='coerce'); st.metric('400張級距以上' if n==12 else '1000張以上級距',f'{vals.sum():.2f}%' if len(vals) else '無資料')
  except Exception as e: st.warning(f'集保資料無法解析：{e}')
  st.caption('歷史變化需另存每週快照。')
 with c:
  st.write('上傳全市場還原權息日線 CSV，欄位 stock,date,open,high,low,close,volume（張）。可另含 TSE 指數代號。')
  f=csv('日線歷史資料'); seg=st.number_input('每段天數',5,60,25); rs=st.checkbox('要求相對大盤強度',True)
  st.caption('免費歷史來源 Yahoo Finance，可能限流或缺漏；首次掃描耗時較長。')
  universe=st.selectbox('自動下載範圍',['指定股票','上市全部普通股','上櫃全部普通股','上市及上櫃普通股'])
  codes=st.text_input('指定股票（逗號分隔，上市 .TW／上櫃 .TWO）','2313.TW,2383.TW')
  if st.button('下載歷史資料並掃描'):
   try:
    symbols=[]
    if universe=='指定股票': symbols=[x.strip().upper() for x in codes.split(',') if x.strip()]
    else:
     if universe in ['上市全部普通股','上市及上櫃普通股']:
      q=get('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL'); symbols.extend([str(x)+'.TW' for x in q['Code'] if str(x).isdigit() and len(str(x))==4 and not str(x).startswith('0')])
     if universe in ['上櫃全部普通股','上市及上櫃普通股']:
      q=get('https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes'); symbols.extend([str(x)+'.TWO' for x in q['SecuritiesCompanyCode'] if str(x).isdigit() and len(str(x))==4 and not str(x).startswith('0')])
    symbols=list(dict.fromkeys(symbols+['^TWII']))
    with st.spinner('下載歷史行情，請保持頁面開啟'):
     data,failed=history(symbols)
    st.session_state['history_data']=data; st.session_state['history_status']=(len(symbols),failed)
   except Exception as e: st.error(f'自動下載失敗：{e}')
  if f is None and 'history_data' in st.session_state:
   f=st.session_state['history_data']; total,failed=st.session_state['history_status']; st.caption(f'成功 {total-len(failed)} / {total} 個代號（含指數）')
   if failed: st.warning('缺漏代號：'+', '.join(failed))
   if f.empty: f=None
  if f is not None:
   try: st.dataframe(scan(f,int(seg),rs),hide_index=True)
   except Exception as e: st.error(str(e))
 with d:
  st.write('上傳授權分點資料 CSV：date,stock,broker,buy_qty,sell_qty,buy_price,sell_price（股數與元）。')
  f=csv('分點歷史資料'); broker=st.text_input('分點名稱','凱基-城中'); fee=st.number_input('估算單邊手續費率 %',0.,1.,0.1425,format='%.4f'); tax=st.number_input('賣出稅率 %',0.,1.,0.3)
  if f is not None:
   try: st.dataframe(branch(f,broker,fee/100,tax/100),hide_index=True)
   except Exception as e: st.error(str(e))
  st.caption('以可觀察期間加權成本推估；未知期初庫存、跨分點、當日成交順序都可能造成誤差。')
@st.cache_data(ttl=300)
def tdcc():
 r=requests.get('https://opendata.tdcc.com.tw/getOD.ashx?id=1-5',timeout=40); r.raise_for_status(); return pd.read_csv(io.BytesIO(r.content),encoding='utf-8-sig',dtype=str)
def scan(f,seg,rs):
 f=f.copy(); f['date']=pd.to_datetime(f.date); f=f.sort_values('date'); idx=f[f.stock=='TSE'].set_index('date').close; out=[]
 for s,g in f.groupby('stock'):
  if s=='TSE' or len(g)<max(251,3*seg+1): continue
  g=g.sort_values('date'); x=g.iloc[-1]; p=g.iloc[:-1]; c=g.close; ma=lambda n:c.iloc[-n:].mean(); lo=g.low.iloc[-250:].min(); hi=g.high.iloc[-250:].max()
  trend=x.close>ma(50)>ma(150)>ma(200) and ma(200)>c.iloc[-220:-20].mean() and x.close>=lo*1.3 and x.close>=hi*.75
  chunks=[p.iloc[-3*seg:-2*seg],p.iloc[-2*seg:-seg],p.iloc[-seg:]]; depths=[100*(q.high.max()-q.low.min())/q.high.max() for q in chunks]; pivot=chunks[-1].high.max(); v=p.volume.tail(50).mean(); dry=p.volume.tail(10).mean()/v if v>0 else np.nan; vr=x.volume/v if v>0 else np.nan
  roc=c.iloc[-1]/c.iloc[-251]-1; ix=idx.reindex([g.date.iloc[-251],x.date]); ir=ix.iloc[1]/ix.iloc[0]-1 if len(ix)==2 else np.nan
  if not trend or (rs and not (roc>=ir)): continue
  contract=depths[0]>=10 and depths[0]>depths[1]>depths[2] and depths[2]<=10
  setup=contract and dry<.7; breakout=setup and c.iloc[-2]<=pivot<x.close and vr>1.5 and x.volume>=500
  status='突破確認' if breakout else '突破預警' if setup and .95*pivot<=x.close<=pivot else '潛伏觀察' if setup else '強勢股'
  out.append({'代號':s,'日期':str(x.date.date()),'階段':status,'樞紐價':pivot,'末段收縮%':round(depths[-1],2),'量縮比':round(dry,2),'突破量比':round(vr,2),'排序':{'突破確認':0,'突破預警':1,'潛伏觀察':2,'強勢股':3}[status]})
 return pd.DataFrame(out).sort_values('排序') if out else pd.DataFrame(columns=['代號','階段'])
def branch(f,broker,fee,tax):
 f=f[f.broker==broker].sort_values('date'); out=[]
 for s,g in f.groupby('stock'):
  qty=cost=0.; prev=0.
  for _,r in g.iterrows():
   sold=min(qty,r.sell_qty); avg=cost/qty if qty else 0.; pnl=sold*(r.sell_price*(1-fee-tax)-avg); qty-=sold; cost-=sold*avg; unknown=r.sell_qty-sold; qty+=r.buy_qty; cost+=r.buy_qty*r.buy_price*(1+fee)
   out.append({'日期':r.date,'股票':s,'估算剩餘股數':qty,'估算均價':cost/qty if qty else 0,'已配對估算損益':pnl,'未配對賣出股數':unknown,'前筆買量對應賣出比例':min(sold/prev,1) if prev else None}); prev=r.buy_qty
 return pd.DataFrame(out)
dashboard()
