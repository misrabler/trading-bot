# auto_append_btc_eth.py



import pandas as pd

import gspread

from google.oauth2.service\_account import Credentials

import requests



\# -----------------------------

\# CONFIGURATION

\# -----------------------------

JSON\_KEY\_PATH = "/github/home/.config/tradingbotdata.json"  # path in GitHub Actions

SHEET\_NAME = "BTC\_ETH\_1H\_Data"

ASSETS = \["BTC/USD", "ETH/USD"]

CANDLE\_INTERVAL = "60"

ROLLING\_TAIL = 20



\# -----------------------------

\# GOOGLE SHEETS AUTH

\# -----------------------------

scopes = \[

    "https://www.googleapis.com/auth/spreadsheets",

    "https://www.googleapis.com/auth/drive"

]

creds = Credentials.from\_service\_account\_file(JSON\_KEY\_PATH, scopes=scopes)

client = gspread.authorize(creds)

sheet = client.open(SHEET\_NAME).sheet1



\# -----------------------------

\# HELPER FUNCTIONS

\# -----------------------------

def fetch\_kraken\_ohlcv(pair, interval, since=None):

    url = "https://api.kraken.com/0/public/OHLC"

    params = {"pair": pair.replace("/", ""), "interval": interval}

    if since: params\["since"] = int(since)

    resp = requests.get(url, params=params)

    data = resp.json()

    result = list(data\['result'].values())\[0]

    df = pd.DataFrame(result, columns=\[

        "time","open","high","low","close","vwap","volume","count"

    ])

    df = df\[\["time","open","high","low","close","volume"]].astype(float)

    df\["time"] = pd.to\_datetime(df\["time"], unit="s")

    df.rename(columns={

        "time":"time","open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"

    }, inplace=True)

    return df



def calculate\_indicators(df):

    df\["EMA50"] = df\["Close"].ewm(span=50, adjust=False).mean()

    df\["EMA200"] = df\["Close"].ewm(span=200, adjust=False).mean()

    df\["H-L"] = df\["High"] - df\["Low"]

    df\["H-PC"] = abs(df\["High"] - df\["Close"].shift(1))

    df\["L-PC"] = abs(df\["Low"] - df\["Close"].shift(1))

    df\["TR"] = df\[\["H-L","H-PC","L-PC"]].max(axis=1)

    df\["ATR14"] = df\["TR"].rolling(14).mean()

    df\["Prev\_20\_High"] = df\["High"].shift(1).rolling(20).max()

    df\["Prev\_20\_Vol\_Avg"] = df\["Volume"].shift(1).rolling(20).mean()

    df\["Trend"] = df.apply(lambda row: "Long" if row\["EMA50"]>row\["EMA200"] else "Short", axis=1)

    df\["Entry\_Signal"] = df.apply(lambda row: True if (row\["Close"]>row\["Prev\_20\_High"] and row\["Trend"]=="Long") else False, axis=1)

    df\["Stop\_Price"] = df\["Close"] - df\["ATR14"]

    df\["Target\_Price"] = df\["Close"] + 2\*df\["ATR14"]

    return df



def write\_to\_sheet(df, asset\_name):

    df = df.replace(\[float('inf'), float('-inf')], None).fillna('')

    rows = \[]

    for \_, row in df.iterrows():

        rows.append(\[

            row\["time"].strftime("%Y-%m-%d %H:%M:%S"), asset\_name,

            row\["Open"], row\["High"], row\["Low"], row\["Close"], row\["Volume"],

            row\["EMA50"], row\["EMA200"], row\["ATR14"], row\["Prev\_20\_High"],

            row\["Prev\_20\_Vol\_Avg"], row\["Trend"], row\["Entry\_Signal"],

            row\["Stop\_Price"], row\["Target\_Price"], ""

        ])

    if rows: sheet.append\_rows(rows, value\_input\_option='USER\_ENTERED')



\# -----------------------------

\# MAIN SCRIPT (runs once)

\# -----------------------------

for asset in ASSETS:

    print(f"Processing {asset}...")

    all\_records = sheet.get\_all\_records()

    df\_existing = pd.DataFrame(all\_records)

    df\_existing\_asset = df\_existing\[df\_existing\['Asset']==asset]



    last\_time = pd.to\_datetime(df\_existing\_asset\['Timestamp'].iloc\[-1]) if not df\_existing\_asset.empty else None

    since\_unix = int(last\_time.timestamp()) if last\_time else None

    df\_new = fetch\_kraken\_ohlcv(asset, CANDLE\_INTERVAL, since=since\_unix)



    if not df\_new.empty:

        tail\_rows = df\_existing\_asset.tail(ROLLING\_TAIL).copy()

        if not tail\_rows.empty:

            tail\_rows.loc\[:, "time"] = pd.to\_datetime(tail\_rows\["Timestamp"])

            df\_combined = pd.concat(\[tail\_rows\[\["time","Open","High","Low","Close","Volume"]], df\_new], ignore\_index=True)

        else:

            df\_combined = df\_new.copy()

        df\_combined = calculate\_indicators(df\_combined)

        df\_to\_append = df\_combined.iloc\[len(tail\_rows):]

        write\_to\_sheet(df\_to\_append, asset)

        print(f"Appended {len(df\_to\_append)} rows for {asset}")

    else:

        print(f"No new candles for {asset}")


