import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from market_history import history
from backtest import run, chips
from combined import vcp_events, confluence
from broker_profile import profiles, profile_signals
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
st.set_page_config(page_title='台股主力籌碼雷達',layout='wide')
st.title('台股主力籌碼雷達')
st.caption('V0.11｜公開資料與自備歷史資料｜非即時交易訊號')
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
st.markdown("""<style>
.block-container {max-width: 1440px; padding-top: 2rem;}
[data-testid="stMetric"] {border:1px solid #8793a333; border-radius:12px; padding:15px;}
.stTabs [data-baseweb="tab-list"] {gap:12px; overflow-x:auto;}
.stTabs [data-baseweb="tab"] {padding:12px 8px;}
</style>""",unsafe_allow_html=True)
@st.cache_data(ttl=3600)
def stock_choices():
 options={}
 for url,code,name in [
  ('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL','Code','Name'),
  ('https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes','SecuritiesCompanyCode','CompanyName')]:
  try:
   q=get(url)
   for _,v in q.iterrows():
    k=str(v[code]).strip()
    if len(k)==4 and k.isdigit(): options[k]=str(v.get(name,k))
  except Exception: continue
 return options
choices=stock_choices()
st.caption('市場總覽 · 籌碼追蹤 · 策略驗證')
if not choices: st.warning('市場名單暫時無法下載')
stock=st.selectbox('個股快速瀏覽（可直接選股票名稱）',list(choices) or ['2313','2383'],format_func=lambda k:f'{choices.get(k, {"2313":"華通","2383":"台光電"}.get(k,k))} · {k}',index=None,placeholder='選擇公司，不必輸入代號')
stock=stock or ''

if st.sidebar.button('立即重新抓取'): st.cache_data.clear(); st.rerun()
@st.fragment(run_every='5m')
def dashboard():
 a,b,c,d,e,profile_tab=st.tabs(['每日行情與法人','集保大戶','VCP 全市場','券商分點','籌碼回測','主力屬性'])
 with a:
  st.subheader('市場雷達｜上市＋上櫃')
  scope=st.radio('市場範圍',['上市＋上櫃','上市','上櫃'],horizontal=True,key='radar_market')
  frames=[]
  for market_name,url,rename in [
   ('上市','https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',{}),
   ('上櫃','https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes',{'SecuritiesCompanyCode':'Code','CompanyName':'Name','Close':'ClosingPrice','TradingShares':'TradeVolume'})]:
   if scope!='上市＋上櫃' and scope!=market_name: continue
   part=load(url).rename(columns=rename)
   if not {'Code','Name','ClosingPrice','Change','TradeVolume'}.issubset(part.columns) or part.empty:
    st.warning(market_name+'行情缺漏，以下統計不包含該市場'); continue
   part=part.copy()
   part['市場']=market_name
   part['Code']=part['Code'].astype(str).str.strip()
   if 'Date' in part: st.caption(market_name+'行情日期：'+str(part['Date'].iloc[0]))
   frames.append(part)
  q=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
  if len(frames)==2 and all('Date' in f for f in frames):
   dates=[str(f['Date'].iloc[0]).strip() for f in frames]
   if dates[0]!=dates[1]:
    st.warning('上市與上櫃行情日期不同，請分開查看。')
    q=pd.DataFrame()
  if {'Code','Name','ClosingPrice','Change','TradeVolume'}.issubset(q.columns):
   q=q.copy()
   q=q[q.Code.astype(str).str.fullmatch(r'[1-9][0-9]{3}')]
   for k in ['ClosingPrice','Change','TradeVolume']:
    q[k]=pd.to_numeric(q[k].astype(str).str.replace(',','',regex=False),errors='coerce')
   q=q.dropna(subset=['ClosingPrice','Change','TradeVolume'])
   q=q[q.ClosingPrice-q.Change>0].copy()
   q['漲幅%']=100*q.Change/(q.ClosingPrice-q.Change)
   q['成交張數']=q.TradeVolume/1000
   q['公司']=q.Name+' '+q.Code.astype(str)+' ('+q['市場']+')'
   st.caption('上市 '+str((q['市場']=='上市').sum())+' 家｜上櫃 '+str((q['市場']=='上櫃').sum())+' 家（依所選範圍及有效行情）')
   for col,label,value in zip(st.columns(4),['上漲','下跌','平盤','行情統計家數'],[(q.Change>0).sum(),(q.Change<0).sum(),(q.Change==0).sum(),len(q)]):
    col.metric(label,int(value))
   l,m,r=st.columns(3)
   with l:
    st.subheader('漲幅前12名')
    st.bar_chart(q[q['漲幅%']>0].nlargest(12,'漲幅%').set_index('公司')['漲幅%'],color='#d94b4b',horizontal=True)
   with m:
    st.subheader('跌幅前12名')
    st.bar_chart(q[q['漲幅%']<0].nsmallest(12,'漲幅%').set_index('公司')['漲幅%'],color='#279765',horizontal=True)
   with r:
    st.subheader('成交量前12名')
    st.bar_chart(q.nlargest(12,'成交張數').set_index('公司')['成交張數'],horizontal=True)
   for i,(_,v) in enumerate(q.nlargest(8,'TradeVolume').iterrows()):
    if i%4==0: cards=st.columns(4)
    with cards[i%4]:
     st.metric(v['公司'],f"{v.ClosingPrice:.2f}",f"{v['漲幅%']:+.2f}%")
     if st.button('查看走勢',key='radar_'+str(v.Code)): st.session_state['radar_symbol']=str(v.Code); st.session_state['radar_suffix']='.TWO' if v['市場']=='上櫃' else '.TW'
   if st.session_state.get('radar_symbol'):
    try:
     symbol=st.session_state['radar_symbol']
     h,failed=history([symbol+st.session_state.get('radar_suffix','.TW')],365)
     st.subheader(symbol+' 歷史行情')
     if not h.empty:
      h=h.sort_values('date').set_index('date')
      st.line_chart(h[['close']]); st.bar_chart(h[['volume']])
     else: st.warning('歷史行情無資料')
    except Exception as err: st.warning(str(err))
  st.subheader('上市市場總覽')
  market=load('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL')
  if not market.empty and 'TradeVolume' in market:
   ranked=market.copy()
   ranked['_volume']=pd.to_numeric(ranked.TradeVolume.astype(str).str.replace(',',''),errors='coerce')
   ranked=ranked.sort_values('_volume',ascending=False).drop(columns='_volume').head(30)
   st.caption('上市成交量前 30 名，可直接點選一列瀏覽')
   selected=st.dataframe(ranked,hide_index=True,on_select='rerun',selection_mode='single-row',key='market_rank')
   if selected.selection.rows: stock_selected=str(ranked.iloc[selected.selection.rows[0]]['Code'])
   else: stock_selected=stock
  else: stock_selected=stock
  for title,url in [('上市每日行情','https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL'),]:
   st.subheader(title); df=load(url)
   if not df.empty:
    mask=df.astype(str).eq(stock_selected).any(axis=1); st.dataframe(df[mask] if mask.any() else df.iloc[0:0],hide_index=True); st.caption('日期依來源欄位。')
  st.subheader('上市三大法人')
  try:
   df,day=institutional(); st.caption('資料日期：'+day); sub=df[df.iloc[:,0].astype(str).str.strip()==stock_selected]; st.dataframe(sub,hide_index=True)
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
  st.write('自動下載上市及上櫃還原權息日線，不需自行準備 CSV。')
  with st.expander('進階：手動上傳 CSV（備用）'):
   f=csv('日線歷史資料')
  seg=st.number_input('每段天數',5,60,25); rs=st.checkbox('要求相對大盤強度',True)
  st.caption('免費歷史來源 Yahoo Finance，可能限流或缺漏；首次掃描耗時較長。')
  universe=st.selectbox('自動下載範圍',['指定股票','上市全部普通股','上櫃全部普通股','上市及上櫃普通股'],index=3)
  years=st.selectbox('歷史資料期間',['約一年半（掃描）','約六年（五年回測含暖機）'])
  codes=st.text_input('指定股票（逗號分隔，上市 .TW／上櫃 .TWO）','2313.TW,2383.TW') if universe=='指定股票' else ''
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
     data,failed=history(symbols,550 if years.startswith('約一年') else 2250)
    st.session_state['history_data']=data; st.session_state['history_status']=(len(symbols),failed)
   except Exception as e: st.error(f'自動下載失敗：{e}')
  if f is None and 'history_data' in st.session_state:
   f=st.session_state['history_data']; total,failed=st.session_state['history_status']; st.caption(f'成功 {total-len(failed)} / {total} 個代號（含指數）')
   if failed: st.warning('缺漏代號：'+', '.join(failed))
   if f.empty: f=None
  if f is not None:
   st.download_button('下載還原權息日線 CSV',f.to_csv(index=False).encode('utf-8-sig'),'adjusted_daily.csv','text/csv')
   try: st.dataframe(scan(f,int(seg),rs),hide_index=True)
   except Exception as e: st.error(str(e))
 with d:
  st.write('上傳授權分點資料 CSV：date,stock,broker,buy_qty,sell_qty,buy_price,sell_price（股數與元）。')
  f=csv('分點歷史資料'); broker=st.text_input('分點名稱','凱基-城中'); fee=st.number_input('估算單邊手續費率 %',0.,1.,0.1425,format='%.4f'); tax=st.number_input('賣出稅率 %',0.,1.,0.3)
  if f is not None:
   try: st.dataframe(branch(f,broker,fee/100,tax/100),hide_index=True)
   except Exception as e: st.error(str(e))
  st.caption('以可觀察期間加權成本推估；未知期初庫存、跨分點、當日成交順序都可能造成誤差。')
 with profile_tab:
  st.subheader('主力行為與公司關聯候選')
  st.caption('分點包含多位客戶，無法確認公司派、市場派或實際隔日沖。以下為未校準行為指標，不是身分機率。')
  pf=csv('主力行為歷史 CSV（date,stock,broker,buy_qty,sell_qty）')
  window=st.selectbox('觀察日曆天數',[30,60,90,180],index=1)
  if pf is not None and st.button('分析主力行為'):
   try:
    p=profiles(pf,window)
    if p.empty: st.warning('至少需要15個有分點資料的日期')
    else:
     latest=p.sort_values('date').drop_duplicates(['broker','stock'],keep='last')
     st.dataframe(latest.sort_values('accumulation_score',ascending=False),hide_index=True)
     st.caption('集中度依上傳股票涵蓋率而變動；公司所在地與內部人持股證據尚未串接，身分一律未確認。')
   except Exception as err: st.error(str(err))
 with e:
  st.subheader('歷史籌碼事件回測')
  st.caption('訊號公布日後的下一交易日開盤進場，第 N 個交易日收盤出場；包含手續費與交易稅。賣超訊號也以做多報酬觀察，不代表放空交易。')
  st.write('價格 CSV：stock,date,open,close（還原權息）。分點 CSV：stock,available_date,broker,buy_qty,sell_qty（股數）。集保 CSV：stock,available_date,pct400,pct1000（百分比）。available_date 必須是實際公布日，不是資料統計日。')
  prices=csv('回測股價 CSV'); brokers=csv('回測分點 CSV'); holders=csv('回測大戶 CSV')
  if prices is None and 'history_data' in st.session_state and not st.session_state['history_data'].empty:
   prices=st.session_state['history_data']; st.caption('使用 VCP 頁面已自動下載的歷史行情。')
  lots=st.number_input('分點淨買賣超門檻（張）',1,100000,500)
  change=st.number_input('大戶持股變化門檻（百分點）',0.01,100.,0.5)
  include_vcp=st.checkbox('加入歷史 VCP 突破（價格需含 high,low,volume 張）',False)
  relative=st.checkbox('VCP 要求相對大盤強度（需 TSE 指數）',True)
  lookback=st.number_input('籌碼交叉訊號有效日曆天數',1,60,14)
  if st.button('開始籌碼回測'):
   try:
    if prices is None or (brokers is None and holders is None and not include_vcp): st.warning('必須先提供真實歷史股價及至少一種籌碼資料。')
    else:
     signals=chips(brokers,holders,lots,change)
     if brokers is not None and 'date' in brokers.columns:
      signals=pd.concat([signals,profile_signals(brokers,lots)],ignore_index=True)
     if include_vcp:
      if relative and not prices.stock.eq('TSE').any(): raise ValueError('相對強度需要 TSE 指數資料')
      signals=pd.concat([signals,vcp_events(prices,relative)],ignore_index=True)
     signals=pd.concat([signals,confluence(signals,lookback)],ignore_index=True)
     summary,trades=run(prices,signals)
     if summary.empty: st.warning('沒有足夠可配對的歷史樣本')
     else:
      st.dataframe(summary.sort_values(['days','mean'],ascending=[True,False]),hide_index=True)
      st.caption('排名依平均報酬，未控制樣本數及多重比較；不能直接視為投資建議。')
      st.download_button('下載逐筆回測結果',trades.to_csv(index=False).encode('utf-8-sig'),'backtest.csv','text/csv')
   except Exception as err: st.error(str(err))
  st.caption('事件樣本可能重疊；目前不是資金配置回測，不計算資產最大回撤。尚未加入下市股完整樣本。')
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
