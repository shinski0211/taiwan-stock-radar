"""Small display helpers. Numbers and colors only; no extra calculations."""

import altair as alt
import pandas as pd
import streamlit as st

UP = '#C4312E'
DOWN = '#1F7A4D'
FLAT = '#78716C'
VOLUME = '#3E5568'

MARKETS = [
    ('上市', 'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL', {}),
    (
        '上櫃',
        'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes',
        {
            'SecuritiesCompanyCode': 'Code',
            'CompanyName': 'Name',
            'Close': 'ClosingPrice',
            'TradingShares': 'TradeVolume',
        },
    ),
]

QUOTE_RENAME = {
    'Date': '日期',
    'Code': '代號',
    'Name': '公司',
    'TradeVolume': '成交股數',
    'TradeValue': '成交金額',
    'OpeningPrice': '開盤',
    'HighestPrice': '最高',
    'LowestPrice': '最低',
    'ClosingPrice': '收盤',
    'Change': '漲跌',
    'Transaction': '成交筆數',
}

QUOTE_ORDER = ['日期', '代號', '公司', '收盤', '漲跌', '開盤', '最高', '最低', '成交股數', '成交金額', '成交筆數', '市場']

QUOTE_FORMATS = {
    '收盤': '%.2f',
    '漲跌': '%+.2f',
    '開盤': '%.2f',
    '最高': '%.2f',
    '最低': '%.2f',
    '成交股數': '%,.0f',
    '成交金額': '%,.0f',
    '成交筆數': '%,.0f',
}


def _paint(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ''
    if pd.isna(number):
        return ''
    if number > 0:
        return f'color: {UP}'
    if number < 0:
        return f'color: {DOWN}'
    return f'color: {FLAT}'


def show_frame(df, column_config=None, signed=(), key=None, selectable=False):
    data = df
    signed_columns = [column for column in signed if column in df.columns]
    if signed_columns and len(df):
        data = df.style.map(_paint, subset=signed_columns)
    arguments = {
        'hide_index': True,
        'width': 'stretch',
        'column_config': column_config,
    }
    if selectable:
        arguments.update(on_select='rerun', selection_mode='single-row', key=key)
    return st.dataframe(data, **arguments)


def present_quotes(df):
    view = df.copy()
    for column in ['TradeVolume', 'TradeValue', 'OpeningPrice', 'HighestPrice', 'LowestPrice', 'ClosingPrice', 'Change', 'Transaction']:
        if column in view.columns:
            view[column] = pd.to_numeric(
                view[column].astype(str).str.replace(',', '', regex=False).str.strip(),
                errors='coerce',
            )
    view = view.rename(columns=QUOTE_RENAME)
    ordered = [column for column in QUOTE_ORDER if column in view.columns]
    ordered += [column for column in view.columns if column not in ordered]
    return view[ordered]


def quote_config(df):
    config = {}
    if '代號' in df.columns:
        config['代號'] = st.column_config.TextColumn('代號', width='small', pinned=True)
    if '公司' in df.columns:
        config['公司'] = st.column_config.TextColumn('公司', width='medium', pinned=True)
    for name, fmt in QUOTE_FORMATS.items():
        if name in df.columns:
            config[name] = st.column_config.NumberColumn(name, format=fmt)
    return config


def present_institutional(df):
    view = df.copy()
    keep = {'證券代號', '證券名稱'}
    for column in view.columns:
        if column in keep:
            continue
        converted = pd.to_numeric(
            view[column].astype(str).str.replace(',', '', regex=False).str.strip(),
            errors='coerce',
        )
        if len(view) and converted.notna().sum() >= max(1, int(0.6 * len(view))):
            view[column] = converted
    return view


def institutional_config(df):
    config = {}
    if '證券代號' in df.columns:
        config['證券代號'] = st.column_config.TextColumn('證券代號', width='small', pinned=True)
    if '證券名稱' in df.columns:
        config['證券名稱'] = st.column_config.TextColumn('證券名稱', width='medium', pinned=True)
    for column in df.columns:
        if column in config or not pd.api.types.is_numeric_dtype(df[column]):
            continue
        fmt = '%+,.0f' if '買賣超' in column else '%,.0f'
        config[column] = st.column_config.NumberColumn(column, format=fmt)
    return config


def signed_institutional(df):
    return tuple(
        column for column in df.columns
        if '買賣超' in column and pd.api.types.is_numeric_dtype(df[column])
    )


def present_tdcc(df):
    view = df.copy()
    keep = {'證券代號', '證券名稱', '資料日期', '國際證券編碼', '持股分級'}
    for column in view.columns:
        if column in keep:
            continue
        converted = pd.to_numeric(
            view[column].astype(str).str.replace(',', '', regex=False).str.replace('%', '', regex=False).str.strip(),
            errors='coerce',
        )
        if len(view) and converted.notna().sum() >= max(1, int(0.6 * len(view))):
            view[column] = converted
    return view


def tdcc_config(df):
    config = {}
    if '證券代號' in df.columns:
        config['證券代號'] = st.column_config.TextColumn('證券代號', width='small', pinned=True)
    if '證券名稱' in df.columns:
        config['證券名稱'] = st.column_config.TextColumn('證券名稱', width='medium', pinned=True)
    for column in df.columns:
        if column in config or not pd.api.types.is_numeric_dtype(df[column]):
            continue
        if '比例' in column:
            fmt = '%.2f%%'
        elif '分級' in column:
            fmt = '%d'
        else:
            fmt = '%,.0f'
        config[column] = st.column_config.NumberColumn(column, format=fmt)
    return config


def load_frames(scope, load):
    frames = []
    notes = []
    for market_name, url, rename in MARKETS:
        if scope != '上市＋上櫃' and scope != market_name:
            continue
        part = load(url).rename(columns=rename)
        if not {'Code', 'Name', 'ClosingPrice', 'Change', 'TradeVolume'}.issubset(part.columns) or part.empty:
            notes.append(('warning', market_name + '行情缺漏，以下統計不包含該市場'))
            continue
        part = part.copy()
        part['市場'] = market_name
        part['Code'] = part['Code'].astype(str).str.strip()
        if 'Date' in part:
            notes.append(('caption', market_name + '行情日期：' + str(part['Date'].iloc[0])))
        frames.append(part)
    return frames, notes


def build_board(frames):
    mismatch = None
    board = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(frames) == 2 and all('Date' in frame.columns for frame in frames):
        dates = [str(frame['Date'].iloc[0]).strip() for frame in frames]
        if dates[0] != dates[1]:
            mismatch = '上市與上櫃行情日期不同，請分開查看。'
            board = pd.DataFrame()
    needed = {'Code', 'Name', 'ClosingPrice', 'Change', 'TradeVolume'}
    if needed.issubset(board.columns):
        board = board.copy()
        board = board[board.Code.astype(str).str.fullmatch(r'[1-9][0-9]{3}')]
        for column in ['ClosingPrice', 'Change', 'TradeVolume']:
            board[column] = pd.to_numeric(
                board[column].astype(str).str.replace(',', '', regex=False),
                errors='coerce',
            )
        board = board.dropna(subset=['ClosingPrice', 'Change', 'TradeVolume'])
        board = board[board.ClosingPrice - board.Change > 0].copy()
        board['漲幅%'] = 100 * board.Change / (board.ClosingPrice - board.Change)
        board['成交張數'] = board.TradeVolume / 1000
        board['公司'] = board.Name + ' ' + board.Code.astype(str) + ' (' + board['市場'] + ')'
    return board, mismatch


def show_notes(notes, mismatch):
    for kind, text in notes:
        if kind == 'warning':
            st.warning(text)
        else:
            st.caption(text)
    if mismatch:
        st.warning(mismatch)


def breadth_metrics(board):
    columns = st.columns(4)
    items = [
        ('上漲', int((board.Change > 0).sum())),
        ('下跌', int((board.Change < 0).sum())),
        ('平盤', int((board.Change == 0).sum())),
        ('行情統計家數', int(len(board))),
    ]
    for column, (label, value) in zip(columns, items):
        column.metric(label, value, format='%,d')


def count_caption(board):
    listed = int((board['市場'] == '上市').sum())
    otc = int((board['市場'] == '上櫃').sum())
    st.caption(f'上市 {listed} 家｜上櫃 {otc} 家（依所選範圍及有效行情）')


def rank_chart(frame, value, y_label, color, sort):
    if frame.empty:
        st.caption('無資料')
        return
    plot = frame[[value]].copy()
    plot['名稱'] = frame['Name'].astype(str).str.strip() + ' ' + frame['Code'].astype(str)
    st.bar_chart(
        plot,
        x='名稱',
        y=value,
        horizontal=True,
        color=color,
        sort=sort,
        x_label='',
        y_label=y_label,
        height=360,
    )


def price_chart(frame, symbol):
    data = frame.reset_index()
    date_column = 'date' if 'date' in data.columns else data.columns[0]
    data = data.rename(columns={date_column: '日期'})
    dates = pd.to_datetime(data['日期'])
    if dates.dt.tz is not None:
        dates = dates.dt.tz_convert('Asia/Taipei').dt.tz_localize(None)
    data['日期'] = dates
    data = data.sort_values('日期')
    color = alt.condition('datum.close >= datum.open', alt.value(UP), alt.value(DOWN))
    tooltip = [
        alt.Tooltip('日期:T', title='日期', format='%Y-%m-%d'),
        alt.Tooltip('open:Q', title='開盤', format='.2f'),
        alt.Tooltip('high:Q', title='最高', format='.2f'),
        alt.Tooltip('low:Q', title='最低', format='.2f'),
        alt.Tooltip('close:Q', title='收盤', format='.2f'),
        alt.Tooltip('volume:Q', title='成交量（張）', format=',.0f'),
    ]
    axis = alt.X('日期:T', title='日期')
    base = alt.Chart(data).encode(x=axis, tooltip=tooltip)
    price = (
        base.mark_rule().encode(y=alt.Y('low:Q', title='價格', scale=alt.Scale(zero=False)), y2='high:Q', color=color)
        + base.mark_bar(size=3).encode(y='open:Q', y2='close:Q', color=color)
    ).properties(height=300)
    volume = base.mark_bar(size=3).encode(
        y=alt.Y('volume:Q', title='成交量（張）'),
        color=color,
    ).properties(height=100)
    return alt.vconcat(price, volume).resolve_scale(x='shared')


def take_csv(label, key):
    slot = key + '_df'

    def remember():
        uploaded = st.session_state.get(key)
        if uploaded is None:
            st.session_state.pop(slot, None)
            return
        st.session_state[slot] = pd.read_csv(uploaded, dtype={'stock': str, 'broker': str})

    st.file_uploader(label, type='csv', key=key, on_change=remember)
    frame = st.session_state.get(slot)
    if frame is not None and st.session_state.get(key) is None:
        st.caption('沿用本頁已上傳的檔案。重新上傳可取代。')
    return frame


def percent_column(label):
    return st.column_config.NumberColumn(label, format='%+.2f%%')


def show_movers(frame, kind):
    if kind == 'volume':
        view = frame.loc[:, ['公司', '成交張數', '漲幅%']].reset_index(drop=True)
        config = {
            '成交張數': st.column_config.NumberColumn('成交張數', format='%,.0f'),
            '漲幅%': percent_column('漲幅%'),
        }
        signed = ('漲幅%',)
    else:
        view = frame.loc[:, ['公司', '漲幅%']].reset_index(drop=True)
        config = {'漲幅%': percent_column('漲幅%')}
        signed = ('漲幅%',)
    show_frame(view, column_config=config, signed=signed)
