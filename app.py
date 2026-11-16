import streamlit as st

st.set_page_config(page_title='台股主力籌碼雷達', layout='wide', initial_sidebar_state='expanded')

from data_access import stock_choices
from pages import PAGES

st.markdown(
    """
    <style>
    .block-container {max-width: 1180px; padding-top: 1.5rem; padding-bottom: 3rem;}
    [data-testid="stMetricValue"], [data-testid="stMetricDelta"] {font-variant-numeric: tabular-nums;}
    </style>
    """,
    unsafe_allow_html=True,
)

choices = stock_choices()
st.sidebar.caption('V0.11｜公開資料與自備歷史資料')
st.sidebar.caption('非即時交易訊號')
if st.sidebar.button('立即重新抓取', width='stretch'):
    st.cache_data.clear()
    st.rerun()
if not choices:
    st.sidebar.warning('市場名單暫時無法下載')
fallback = {'2313': '華通', '2383': '台光電'}
stock = st.sidebar.selectbox(
    '個股快速瀏覽（可直接選股票名稱）',
    list(choices) or ['2313', '2383'],
    format_func=lambda code: f'{choices.get(code, fallback.get(code, code))} · {code}',
    index=None,
    placeholder='選擇公司，不必輸入代號',
    key='quick_stock',
)
st.session_state['selected_stock'] = stock or ''

page = st.navigation(PAGES, expanded=True)
page.run()
