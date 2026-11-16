"""One page per existing section, plus a short overview."""

import pandas as pd
import streamlit as st
from backtest import chips, run
from broker_feed import (
    DEFAULT_CACHE,
    SOURCE_NOTE,
    BrokerSourceError,
    collect_recent,
    read_token,
)
from broker_profile import profile_signals, profiles
from combined import confluence, vcp_events
from data_access import get, institutional, load, tdcc
from engine import branch, scan
from market_history import history
from podcasts import render_podcast_card, render_podcasts
from robot_supply import render_robots
from present import (
    DOWN,
    UP,
    VOLUME,
    breadth_metrics,
    build_board,
    count_caption,
    institutional_config,
    load_frames,
    percent_column,
    present_institutional,
    present_quotes,
    present_tdcc,
    price_chart,
    quote_config,
    rank_chart,
    show_frame,
    show_movers,
    show_notes,
    signed_institutional,
    take_csv,
    tdcc_config,
)

SUPPLY_SOURCES = [
    ('2026-10-29', 'https://www.taiwannews.com.tw/news/6467688'),
    ('2025-11', 'https://money.udn.com/money/story/11162/9163631'),
    ('2025-12-03', 'https://english.cw.com.tw/article/article.action?id=4491'),
    ('2026-07-06', 'https://www.investing.com/news/stock-market-news/aws-trainium-3-demand-drives-taiwan-supplier-shipment-hike--digitimes-93CH-4776838'),
]

SUPPLY_CHAINS = {
    'Google TPU': [
        ('2454', '聯發科', 'ASIC設計', 0),
        ('2330', '台積電', '晶圓代工', 1),
        ('2368', '金像電', 'PCB', 1),
        ('2383', '台光電', 'CCL', 1),
        ('3037', '欣興', '載板', 1),
        ('6510', '精測', '測試', 1),
        ('6223', '旺矽', '測試', 1),
        ('6442', '光聖', '高速傳輸', 1),
        ('3081', '聯亞', '光通訊驗證', 1),
        ('2356', '英業達', '伺服器', 0),
        ('2382', '廣達', '伺服器', 0),
        ('2317', '鴻海', '伺服器', 0),
    ],
    'Amazon Trainium': [
        ('3661', '世芯-KY', 'ASIC設計', 2),
        ('2330', '台積電', '代工與封裝', 2),
        ('6669', '緯穎', 'AWS客製伺服器', 2),
        ('2345', '智邦', 'AWS網通', 2),
        ('2317', '鴻海', 'AWS伺服器', 0),
        ('2382', '廣達', 'AWS伺服器', 0),
        ('3017', '奇鋐', '散熱', 3),
        ('2059', '川湖', '滑軌', 3),
        ('8210', '勤誠', '機殼', 3),
    ],
}

PROFILE_LABELS = {
    'date': '日期',
    'broker': '分點',
    'stock': '股票',
    'active_days': '有資料天數',
    'concentration': '集中度',
    'accumulation': '累積比',
    'positive_days': '淨買日比例',
    'gross_offset': '當日對沖比',
    'accumulation_score': '累積分數',
    'profile': '行為類型',
    'company_affiliation': '公司關聯',
}

SUMMARY_LABELS = {
    'strategy': '策略',
    'days': '持有交易日',
    'samples': '樣本數',
    'mean': '平均淨報酬%',
    'median': '中位數%',
    'win_rate': '勝率%',
}


def selected_stock():
    return st.session_state.get('selected_stock') or ''


def _ready(board):
    return isinstance(board, pd.DataFrame) and '漲幅%' in board.columns


@st.fragment(run_every='5m')
def render_home():
    st.title('台股主力籌碼雷達')
    st.caption('市場總覽 · 籌碼追蹤 · 策略驗證')
    frames, notes = load_frames('上市＋上櫃', load)
    board, mismatch = build_board(frames)
    show_notes(notes, mismatch)
    if _ready(board):
        breadth_metrics(board)
        count_caption(board)
        gainers, losers, active = st.columns(3)
        with gainers:
            st.subheader('漲幅前5名')
            show_movers(board[board['漲幅%'] > 0].nlargest(5, '漲幅%'), 'change')
        with losers:
            st.subheader('跌幅前5名')
            show_movers(board[board['漲幅%'] < 0].nsmallest(5, '漲幅%'), 'change')
        with active:
            st.subheader('成交量前5名')
            show_movers(board.nlargest(5, '成交張數'), 'volume')
        st.caption('個股走勢、上市明細與三大法人在「每日行情與法人」。')
    render_podcast_card()


@st.fragment(run_every='5m')
def render_market():
    st.header('每日行情與法人')
    scope = st.radio(
        '市場範圍',
        ['上市＋上櫃', '上市', '上櫃'],
        horizontal=True,
        key='radar_market',
    )
    frames, notes = load_frames(scope, load)
    board, mismatch = build_board(frames)
    show_notes(notes, mismatch)
    if _ready(board):
        count_caption(board)
        breadth_metrics(board)
        gainers, losers = st.columns(2)
        with gainers:
            st.subheader('漲幅前12名')
            rank_chart(
                board[board['漲幅%'] > 0].nlargest(12, '漲幅%'),
                '漲幅%',
                '漲幅 %',
                UP,
                '-漲幅%',
            )
        with losers:
            st.subheader('跌幅前12名')
            rank_chart(
                board[board['漲幅%'] < 0].nsmallest(12, '漲幅%'),
                '漲幅%',
                '漲幅 %',
                DOWN,
                '漲幅%',
            )
        st.subheader('成交量前12名')
        rank_chart(board.nlargest(12, '成交張數'), '成交張數', '成交張數', VOLUME, '-成交張數')
        leaders = board.nlargest(8, 'TradeVolume')
        for index, (_, row) in enumerate(leaders.iterrows()):
            if index % 4 == 0:
                cards = st.columns(4)
            with cards[index % 4]:
                change = float(row['漲幅%'])
                st.metric(
                    row['公司'],
                    f'{row.ClosingPrice:.2f}',
                    f'{change:+.2f}%',
                    delta_color='off' if change == 0 else 'inverse',
                )
                if st.button('查看走勢', key='radar_' + str(row.Code)):
                    st.session_state['radar_symbol'] = str(row.Code)
                    st.session_state['radar_suffix'] = '.TWO' if row['市場'] == '上櫃' else '.TW'
        if st.session_state.get('radar_symbol'):
            _show_history()
    st.divider()
    stock = _listed_detail()
    _listed_institutional(stock)


def _show_history():
    symbol = st.session_state['radar_symbol']
    suffix = st.session_state.get('radar_suffix', '.TW')
    try:
        # The shared downloader drops a symbol with fewer than 251 sessions.
        # One calendar year is often shorter than that, so request a longer window
        # and then keep the last year for the chart.
        prices, _failed = history([symbol + suffix], 500)
        st.subheader(symbol + ' 歷史行情')
        if prices.empty:
            st.warning('歷史行情無資料')
            return
        prices = prices.sort_values('date')
        cutoff = prices['date'].max() - pd.Timedelta(days=365)
        recent = prices[prices['date'] >= cutoff]
        prices = (recent if not recent.empty else prices).set_index('date')
        needed = {'open', 'high', 'low', 'close', 'volume'}
        if needed.issubset(prices.columns):
            st.altair_chart(price_chart(prices, symbol), width='stretch')
        else:
            st.line_chart(prices[['close']])
            st.bar_chart(prices[['volume']])
    except Exception as error:
        st.warning(str(error))


def _listed_detail():
    st.subheader('上市市場總覽')
    market = load('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL')
    stock = selected_stock()
    if not market.empty and 'TradeVolume' in market:
        ranked = market.copy()
        ranked['_volume'] = pd.to_numeric(
            ranked.TradeVolume.astype(str).str.replace(',', '', regex=False),
            errors='coerce',
        )
        ranked = ranked.sort_values('_volume', ascending=False).drop(columns='_volume').head(30)
        st.caption('上市成交量前 30 名，可直接點選一列瀏覽')
        shown = present_quotes(ranked)
        selected = show_frame(
            shown,
            column_config=quote_config(shown),
            signed=('漲跌',),
            key='market_rank',
            selectable=True,
        )
        if selected.selection.rows:
            stock = str(ranked.iloc[selected.selection.rows[0]]['Code'])
    st.subheader('上市每日行情')
    quotes = load('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL')
    if not quotes.empty:
        mask = quotes.astype(str).eq(stock).any(axis=1)
        matched = quotes[mask] if mask.any() else quotes.iloc[0:0]
        shown = present_quotes(matched)
        show_frame(shown, column_config=quote_config(shown), signed=('漲跌',))
        st.caption('日期依來源欄位。')
    return stock


def _listed_institutional(stock):
    st.subheader('上市三大法人')
    try:
        frame, day = institutional()
        st.caption('資料日期：' + day)
        matched = frame[frame.iloc[:, 0].astype(str).str.strip() == stock]
        shown = present_institutional(matched)
        show_frame(
            shown,
            column_config=institutional_config(shown),
            signed=signed_institutional(shown),
        )
        if matched.empty:
            st.info('此代號無上市法人資料')
    except Exception as error:
        st.warning(f'法人資料取得失敗：{error}')


@st.fragment(run_every='5m')
def render_holders():
    st.header('集保大戶')
    stock = selected_stock()
    if not stock:
        st.caption('請在左側選擇個股。')
    try:
        frame = tdcc()
        frame['證券代號'] = frame['證券代號'].astype(str).str.strip()
        matched = frame[frame['證券代號'] == stock]
        left, right = st.columns(2)
        for column, level, label in (
            (left, 12, '400張級距以上'),
            (right, 15, '1000張以上級距'),
        ):
            grades = pd.to_numeric(matched['持股分級'], errors='coerce')
            values = pd.to_numeric(
                matched.loc[grades.between(level, 15), '占集保庫存數比例%'],
                errors='coerce',
            )
            column.metric(label, f'{values.sum():.2f}%' if len(values) else '無資料')
        shown = present_tdcc(matched)
        show_frame(shown, column_config=tdcc_config(shown))
    except Exception as error:
        st.warning(f'集保資料無法解析：{error}')
    st.caption('歷史變化需另存每週快照。')


def render_supply():
    st.header('雲端大廠產品供應鏈')
    st.caption('媒體報導，非原廠確認；AWS客戶關係不等於特定Trainium世代供貨。')
    selected = st.radio('產品平台', list(SUPPLY_CHAINS), horizontal=True, key='supply_theme')
    table = pd.DataFrame([
        {
            '代號': code,
            '公司': name,
            '環節': stage,
            '證據': '媒體報導',
            '來源日期': SUPPLY_SOURCES[source][0],
            '來源': SUPPLY_SOURCES[source][1],
        }
        for code, name, stage, source in SUPPLY_CHAINS[selected]
    ])
    query = st.text_input('搜尋公司或代號', key='supply_query').strip()
    if query:
        table = table[table.astype(str).apply(lambda column: column.str.contains(query, case=False, regex=False)).any(axis=1)]
    show_frame(
        table,
        column_config={
            '代號': st.column_config.TextColumn('代號', width='small'),
            '公司': st.column_config.TextColumn('公司', width='medium'),
            '來源': st.column_config.LinkColumn('來源'),
        },
    )
    st.download_button(
        '下載供應鏈清單',
        table.to_csv(index=False).encode('utf-8-sig'),
        'supply_chain.csv',
        'text/csv',
        key='supply_export',
    )


def render_vcp():
    st.header('VCP 全市場')
    with st.expander('VCP 三年回測｜初步結果', expanded=True):
        st.caption('2023-11-15 起，20 檔人工選股試跑；非全市場，存在選股偏誤。已扣交易成本，VCP 樣本不足。')
        validation = pd.DataFrame(
            [
                ['單純突破', 5, 257, 0.629907, 50.583658, -0.249038],
                ['單純突破', 10, 257, 2.495773, 57.198444, 0.540741],
                ['單純突破', 20, 257, 8.413159, 64.980545, 3.99365],
                ['VCP突破', 5, 2, -0.435713, 50, -0.239084],
                ['VCP突破', 10, 2, -1.031407, 50, -1.346763],
                ['VCP突破', 20, 2, -0.699714, 50, -2.001223],
                ['VCP前期', 5, 7, -2.748743, 0, -2.702461],
                ['VCP前期', 10, 7, -1.679284, 42.857143, -3.071645],
                ['VCP前期', 20, 7, -2.203317, 57.142857, -3.067454],
            ],
            columns=['策略', '持有交易日', '樣本數', '平均淨報酬%', '勝率%', '超額報酬%'],
        )
        horizon = st.radio('持有期間', [5, 10, 20], index=2, horizontal=True, key='validation_horizon')
        shown = validation[validation['持有交易日'] == horizon].round(2)
        show_frame(
            shown,
            column_config={
                '樣本數': st.column_config.NumberColumn('樣本數', format='%,d'),
                '平均淨報酬%': percent_column('平均淨報酬%'),
                '勝率%': st.column_config.NumberColumn('勝率%', format='%.2f'),
                '超額報酬%': percent_column('超額報酬%'),
            },
            signed=('平均淨報酬%', '超額報酬%'),
        )
        st.markdown('[回測執行紀錄與原始資料](https://github.com/shinski0211/taiwan-stock-radar/actions/runs/43701627229)')
    st.write('自動下載上市及上櫃還原權息日線，不需自行準備 CSV。')
    with st.expander('進階：手動上傳 CSV（備用）'):
        manual = take_csv('日線歷史資料', 'vcp_manual')
    segment = st.number_input('每段天數', 5, 60, 25, key='vcp_seg')
    require_rs = st.checkbox('要求相對大盤強度', True, key='vcp_rs')
    st.caption('免費歷史來源 Yahoo Finance，可能限流或缺漏；首次掃描耗時較長。')
    universe = st.selectbox(
        '自動下載範圍',
        ['指定股票', '上市全部普通股', '上櫃全部普通股', '上市及上櫃普通股'],
        index=3,
        key='vcp_universe',
    )
    years = st.selectbox('歷史資料期間', ['約一年半（掃描）', '約六年（五年回測含暖機）'], key='vcp_years')
    codes = ''
    if universe == '指定股票':
        codes = st.text_input('指定股票（逗號分隔，上市 .TW／上櫃 .TWO）', '2313.TW,2383.TW', key='vcp_codes')
    if st.button('下載歷史資料並掃描', type='primary'):
        _download_history(universe, codes, years)
    source = manual
    if source is None and 'history_data' in st.session_state:
        source = st.session_state['history_data']
        total, failed = st.session_state['history_status']
        st.caption(f'成功 {total - len(failed)} / {total} 個代號（含指數）')
        if failed:
            st.warning('缺漏代號：' + ', '.join(failed))
        if source.empty:
            source = None
    if source is None:
        return
    st.download_button(
        '下載還原權息日線 CSV',
        source.to_csv(index=False).encode('utf-8-sig'),
        'adjusted_daily.csv',
        'text/csv',
    )
    try:
        result = scan(source, int(segment), require_rs)
        show_frame(
            result,
            column_config={
                '樞紐價': st.column_config.NumberColumn('樞紐價', format='%.2f'),
                '末段收縮%': st.column_config.NumberColumn('末段收縮%', format='%.2f'),
                '量縮比': st.column_config.NumberColumn('量縮比', format='%.2f'),
                '突破量比': st.column_config.NumberColumn('突破量比', format='%.2f'),
                '排序': None,
            },
        )
    except Exception as error:
        st.error(str(error))


def _download_history(universe, codes, years):
    try:
        symbols = []
        if universe == '指定股票':
            symbols = [item.strip().upper() for item in codes.split(',') if item.strip()]
        else:
            if universe in ['上市全部普通股', '上市及上櫃普通股']:
                quotes = get('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL')
                symbols.extend(
                    str(code) + '.TW'
                    for code in quotes['Code']
                    if str(code).isdigit() and len(str(code)) == 4 and not str(code).startswith('0')
                )
            if universe in ['上櫃全部普通股', '上市及上櫃普通股']:
                quotes = get('https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes')
                symbols.extend(
                    str(code) + '.TWO'
                    for code in quotes['SecuritiesCompanyCode']
                    if str(code).isdigit() and len(str(code)) == 4 and not str(code).startswith('0')
                )
        symbols = list(dict.fromkeys(symbols + ['^TWII']))
        with st.spinner('下載歷史行情，請保持頁面開啟'):
            data, failed = history(symbols, 550 if years.startswith('約一年') else 2250)
        st.session_state['history_data'] = data
        st.session_state['history_status'] = (len(symbols), failed)
    except Exception as error:
        st.error(f'自動下載失敗：{error}')


def broker_panel(prefix):
    token = read_token()
    if not token:
        st.warning(SOURCE_NOTE)
        return None
    stocks = st.text_input('股票代號（逗號分隔，最多 5 檔）', '2330', key=prefix + '_stocks')
    days = st.selectbox('往回交易日數', [5, 20, 60], index=0, key=prefix + '_days')
    st.caption('一天一檔一次請求，間隔 0.4 秒。60 個交易日大約是三個月，不是一到兩年。')
    if st.button('取得分點資料', type='primary', key=prefix + '_fetch'):
        try:
            frame = collect_recent(stocks, int(days), token, DEFAULT_CACHE)
            st.session_state['broker_trades'] = frame
            if frame.empty:
                st.warning('這段期間沒有分點成交。')
            else:
                st.caption(f"已取得 {frame['date'].nunique()} 個交易日、{frame['broker'].nunique()} 個分點。")
        except BrokerSourceError as error:
            st.error(str(error))
    frame = st.session_state.get('broker_trades')
    return frame if isinstance(frame, pd.DataFrame) else None


def render_broker():
    st.header('券商分點')
    st.caption('自動取得分點買賣，再估算單一券商的庫存與損益。')
    trades = broker_panel('branch')
    if trades is None or trades.empty:
        return
    ranked = (trades['buy_qty'] - trades['sell_qty']).abs().groupby(trades['broker']).sum().sort_values(ascending=False)
    broker = st.selectbox('分點名稱', list(ranked.index), key='broker_pick')
    fee_column, tax_column = st.columns(2)
    fee = fee_column.number_input('估算單邊手續費率 %', 0.0, 1.0, 0.1425, format='%.4f', key='broker_fee')
    tax = tax_column.number_input('賣出稅率 %', 0.0, 1.0, 0.3, key='broker_tax')
    try:
        result = branch(trades, broker, fee / 100, tax / 100)
        show_frame(
            result,
            column_config={
                '估算剩餘股數': st.column_config.NumberColumn('估算剩餘股數', format='%,.0f'),
                '估算均價': st.column_config.NumberColumn('估算均價', format='%,.2f'),
                '已配對估算損益': st.column_config.NumberColumn('已配對估算損益', format='%,.0f'),
                '未配對賣出股數': st.column_config.NumberColumn('未配對賣出股數', format='%,.0f'),
                '前筆買量對應賣出比例': st.column_config.NumberColumn('前筆買量對應賣出比例', format='percent'),
            },
            signed=('已配對估算損益',),
        )
    except Exception as error:
        st.error(str(error))
    st.caption('以可觀察期間加權成本推估；未知期初庫存、跨分點、當日成交順序都可能造成誤差。')


def render_profile():
    st.header('主力行為與公司關聯候選')
    st.caption('分點包含多位客戶，無法確認公司派、市場派或實際隔日沖。以下為未校準行為指標，不是身分機率。')
    trades = broker_panel('profile')
    window = st.selectbox('觀察日曆天數', [30, 60, 90, 180], index=1, key='profile_window')
    if trades is not None and not trades.empty and st.button('分析主力行為', type='primary'):
        try:
            result = profiles(trades, window)
            if result.empty:
                st.warning('至少需要15個有分點資料的日期')
            else:
                latest = result.sort_values('date').drop_duplicates(['broker', 'stock'], keep='last')
                latest = latest.sort_values('accumulation_score', ascending=False)
                shown = latest.rename(columns=PROFILE_LABELS)
                order = [column for column in PROFILE_LABELS.values() if column in shown.columns]
                shown = shown[order]
                show_frame(
                    shown,
                    column_config={
                        '有資料天數': st.column_config.NumberColumn('有資料天數', format='%d'),
                        '集中度': st.column_config.NumberColumn('集中度', format='percent'),
                        '累積比': st.column_config.NumberColumn('累積比', format='percent'),
                        '淨買日比例': st.column_config.NumberColumn('淨買日比例', format='percent'),
                        '當日對沖比': st.column_config.NumberColumn('當日對沖比', format='percent'),
                        '累積分數': st.column_config.NumberColumn('累積分數', format='%.1f'),
                    },
                )
                st.caption('集中度依上傳股票涵蓋率而變動；公司所在地與內部人持股證據尚未串接，身分一律未確認。')
        except Exception as error:
            st.error(str(error))


def render_backtest():
    st.header('歷史籌碼事件回測')
    st.caption('訊號公布日後的下一交易日開盤進場，第 N 個交易日收盤出場；包含手續費與交易稅。賣超訊號也以做多報酬觀察，不代表放空交易。')
    st.write('股價 CSV：stock,date,open,close（還原權息）。沒有上傳時，會用已下載或 Yahoo 的日線。集保 CSV：stock,available_date,pct400,pct1000（百分比）。分點不再上傳，改由下方自動取得；available_date 用成交日，因為來源於當日晚間更新，回測改在下一交易日進場。')
    prices = take_csv('回測股價 CSV', 'bt_prices')
    holders = take_csv('回測大戶 CSV', 'bt_holders')
    brokers = broker_panel('backtest')
    if prices is None and 'history_data' in st.session_state and not st.session_state['history_data'].empty:
        prices = st.session_state['history_data']
        st.caption('使用 VCP 頁面已自動下載的歷史行情。')
    lots = st.number_input('分點淨買賣超門檻（張）', 1, 100000, 500, key='bt_lots')
    change = st.number_input('大戶持股變化門檻（百分點）', 0.01, 100.0, 0.5, key='bt_change')
    include_vcp = st.checkbox('加入歷史 VCP 突破（價格需含 high,low,volume 張）', False, key='bt_vcp')
    relative = st.checkbox('VCP 要求相對大盤強度（需 TSE 指數）', True, key='bt_relative')
    lookback = st.number_input('籌碼交叉訊號有效日曆天數', 1, 60, 14, key='bt_lookback')
    if st.button('開始籌碼回測', type='primary'):
        use_prices = prices
        use_brokers = None if brokers is None or brokers.empty else brokers
        if use_prices is None and use_brokers is not None:
            use_prices = _prices_for(use_brokers)
            if use_prices is None:
                st.warning('股價下載失敗，無法回測。')
                return
            st.caption('股價使用 Yahoo Finance 還原日線。')
        _run_backtest(use_prices, use_brokers, holders, lots, change, include_vcp, relative, lookback)
    st.caption('事件樣本可能重疊；目前不是資金配置回測，不計算資產最大回撤。尚未加入下市股完整樣本。')


def _prices_for(brokers):
    codes = [str(code) for code in brokers['stock'].astype(str).unique()]
    data, failed = history([code + '.TW' for code in codes] + ['^TWII'], 800)
    missing = [code + '.TWO' for code in codes if code + '.TW' in failed]
    if missing:
        more, _failed = history(missing, 800)
        if more is not None and not more.empty:
            data = more if data is None or data.empty else pd.concat([data, more], ignore_index=True)
    if data is None or data.empty:
        return None
    return data


def _run_backtest(prices, brokers, holders, lots, change, include_vcp, relative, lookback):
    try:
        if prices is None or (brokers is None and holders is None and not include_vcp):
            st.warning('必須先提供真實歷史股價及至少一種籌碼資料。')
            return
        signals = chips(brokers, holders, lots, change)
        if brokers is not None and 'date' in brokers.columns:
            signals = pd.concat([signals, profile_signals(brokers, lots)], ignore_index=True)
        if include_vcp:
            if relative and not prices.stock.eq('TSE').any():
                raise ValueError('相對強度需要 TSE 指數資料')
            signals = pd.concat([signals, vcp_events(prices, relative)], ignore_index=True)
        signals = pd.concat([signals, confluence(signals, lookback)], ignore_index=True)
        summary, trades = run(prices, signals)
        if summary.empty:
            st.warning('沒有足夠可配對的歷史樣本')
            return
        ordered = summary.sort_values(['days', 'mean'], ascending=[True, False]).rename(columns=SUMMARY_LABELS)
        columns = [column for column in SUMMARY_LABELS.values() if column in ordered.columns]
        ordered = ordered[columns]
        show_frame(
            ordered,
            column_config={
                '持有交易日': st.column_config.NumberColumn('持有交易日', format='%d'),
                '樣本數': st.column_config.NumberColumn('樣本數', format='%,d'),
                '平均淨報酬%': percent_column('平均淨報酬%'),
                '中位數%': percent_column('中位數%'),
                '勝率%': st.column_config.NumberColumn('勝率%', format='%.2f'),
            },
            signed=('平均淨報酬%', '中位數%'),
        )
        st.caption('排名依平均報酬，未控制樣本數及多重比較；不能直接視為投資建議。')
        st.download_button(
            '下載逐筆回測結果',
            trades.to_csv(index=False).encode('utf-8-sig'),
            'backtest.csv',
            'text/csv',
        )
    except Exception as error:
        st.error(str(error))


PAGES = {
    '概況': [
        st.Page(render_home, title='總覽', url_path='overview', default=True),
        st.Page(render_podcasts, title='財經 Podcast 重點', url_path='podcasts'),
        st.Page(render_market, title='每日行情與法人', url_path='market'),
        st.Page(render_holders, title='集保大戶', url_path='holders'),
        st.Page(render_supply, title='供應鏈總整理', url_path='supply'),
        st.Page(render_robots, title='機器人供應鏈', url_path='robots'),
    ],
    '策略': [
        st.Page(render_vcp, title='VCP 全市場', url_path='vcp'),
        st.Page(render_broker, title='券商分點', url_path='brokers'),
        st.Page(render_backtest, title='籌碼回測', url_path='backtest'),
        st.Page(render_profile, title='主力屬性', url_path='profile'),
    ],
}
