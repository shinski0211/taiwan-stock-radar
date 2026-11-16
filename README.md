# 台股主力籌碼雷達

公開行情、法人、集保與自備歷史資料的閱讀介面。不是投資建議，也不是即時交易訊號。

## 執行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 機器人供應鏈

概況裡的「機器人供應鏈」讀取 `config/robot_supply_chain.toml`。每一列要有環節、名稱、代號、角色、機器人營收占比、占比來源、資料日期、Optimus 關聯與備註。

沒有公開數字時，占比請維持 `未揭露`。有數字時要附上來源網址與日期。`optimus_tie` 只能填 `媒體報導`、`傳聞` 或 `無`。

收盤價與漲跌幅沿用每日行情已經抓取的上市、上櫃收盤，不另接新的報價來源。

## 券商分點

券商分點、主力屬性與籌碼回測的分點資料不再上傳 CSV。證交所買賣日報表要圖形驗證碼，櫃買中心下載前要驗證非機器人，程式不會破解。

有 FinMind Sponsor 權限時，把 token 放到環境變數 `FINMIND_TOKEN`，或 `.streamlit/secrets.toml`：

```toml
FINMIND_TOKEN = "你的 token"
```

資料集是 `TaiwanStockTradingDailyReport`，自 2021-06-30 起，一天一檔一次請求。頁面一次最多 5 檔、60 個交易日，請求間隔 0.4 秒，並存在本機 `.cache/broker_reports.sqlite`。這份分點資料只供 token 持有人自己使用，不要再轉出去。沒有 token 時，頁面會直接說明原因。
