# auto_append_btc_eth.py
# BTC/ETH hourly data append bot for Google Sheets
# Ready for GitHub Actions

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests

# -----------------------------
# CONFIGURATION
# -----------------------------
import os
# Use environment variable set by GitHub Actions, fallback to local path
JSON_KEY_PATH = os.environ.get("JSON_KEY_PATH", ".config/tradingbotdata.json")
SHEET_NAME = "BTC_ETH_1H_Data"
ASSETS = ["BTC/USD", "ETH/USD"]
CANDLE_INTERVAL = "60"  # 1-hour candles
ROLLING_TAIL = 20       # for combining prior data with new

# -----------------------------
# GOOGLE SHEETS AUTH
# -----------------------------
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file(JSON_KEY_PATH, scopes=scopes)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def fetch_kraken_ohlcv(pair, interval, since=None):
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": pair.replace("/", ""), "interval": interval}
    if since:
        params["since"] = int(since)
    resp = requests.get(url, params=params)
    data = resp.json()
    result = list(data['result'].values())[0]
    df = pd.DataFrame(result, columns=[
        "time","open","high","low","close","vwap","volume","count"
    ])
    df = df[["time","open","high","low","close","volume"]].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.rename(columns={
        "time":"time","open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"
    }, inplace=True)
    return df

def calculate_indicators(df):
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()
    df["H-L"] = df["High"] - df["Low"]
    df["H-PC"] = abs(df["High"] - df["Close"].shift(1))
    df["L-PC"] = abs(df["Low"] - df["Close"].shift(1))
    df["TR"] = df[["H-L","H-PC","L-PC"]].max(axis=1)
    df["ATR14"] = df["TR"].rolling(14).mean()
    df["Prev_20_High"] = df["High"].shift(1).rolling(20).max()
    df["Prev_20_Vol_Avg"] = df["Volume"].shift(1).rolling(20).mean()
    df["Trend"] = df.apply(lambda row: "Long" if row["EMA50"]>row["EMA200"] else "Short", axis=1)
    df["Entry_Signal"] = df.apply(lambda row: True if (row["Close"]>row["Prev_20_High"] and row["Trend"]=="Long") else False, axis=1)
    df["Stop_Price"] = df["Close"] - df["ATR14"]
    df["Target_Price"] = df["Close"] + 2*df["ATR14"]
    return df

def write_to_sheet(df, asset_name):
    df = df.replace([float('inf'), float('-inf')], None).fillna('')
    rows = []
    for _, row in df.iterrows():
        rows.append([
            row["time"].strftime("%Y-%m-%d %H:%M:%S"), asset_name,
            row["Open"], row["High"], row["Low"], row["Close"], row["Volume"],
            row["EMA50"], row["EMA200"], row["ATR14"], row["Prev_20_High"],
            row["Prev_20_Vol_Avg"], row["Trend"], row["Entry_Signal"],
            row["Stop_Price"], row["Target_Price"], ""
        ])
    if rows:
        sheet.append_rows(rows, value_input_option='USER_ENTERED')

# -----------------------------
# MAIN SCRIPT (runs once)
# -----------------------------
for asset in ASSETS:
    print(f"Processing {asset}...")
    all_records = sheet.get_all_records()
    df_existing = pd.DataFrame(all_records)
    df_existing_asset = df_existing[df_existing['Asset']==asset]

    last_time = pd.to_datetime(df_existing_asset['Timestamp'].iloc[-1]) if not df_existing_asset.empty else None
    since_unix = int(last_time.timestamp()) if last_time else None
    df_new = fetch_kraken_ohlcv(asset, CANDLE_INTERVAL, since=since_unix)

    if not df_new.empty:
        tail_rows = df_existing_asset.tail(ROLLING_TAIL).copy()
        if not tail_rows.empty:
            tail_rows.loc[:, "time"] = pd.to_datetime(tail_rows["Timestamp"])
            df_combined = pd.concat([tail_rows[["time","Open","High","Low","Close","Volume"]], df_new], ignore_index=True)
        else:
            df_combined = df_new.copy()
        df_combined = calculate_indicators(df_combined)
        df_to_append = df_combined.iloc[len(tail_rows):]
        write_to_sheet(df_to_append, asset)
        print(f"Appended {len(df_to_append)} rows for {asset}")
    else:
        print(f"No new candles for {asset}")


