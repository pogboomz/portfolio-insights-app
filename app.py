import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import plotly.express as px
import os

st.set_page_config(page_title="Portfolio Insight Pro", layout="wide")
DATA_FILE = "transactions.csv"

# ---------------- LOAD / MIGRATE DATA ----------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return pd.DataFrame(columns=["Date","Ticker","Quantity","Price","Type"])

    df = pd.read_csv(DATA_FILE)

    if "Type" not in df.columns:
        df["Type"] = "BUY"

    if "Price" not in df.columns:
        if "BuyPrice" in df.columns:
            df["Price"] = df["BuyPrice"]
            df.drop(columns=["BuyPrice"], inplace=True)
        else:
            df["Price"] = 0

    df["Type"] = df["Type"].fillna("BUY").astype(str).str.upper().str.strip()
    df["Ticker"] = df["Ticker"].astype(str).str.upper().str.strip()
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    df["Price"] = pd.to_numeric(df["Price"], errors="coerce").fillna(0)

    return df

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# ---------------- TITLE ----------------
st.title("📊 Portfolio Insight Pro")

df = load_data()

# ---------------- SIDEBAR TRANSACTION ----------------
st.sidebar.header("Add Transaction")
ticker = st.sidebar.text_input("Stock Ticker (e.g. INFY.NS)")
qty = st.sidebar.number_input("Quantity", min_value=1)
price_input = st.sidebar.number_input("Price", min_value=0.0)
date = st.sidebar.date_input("Date")
txn_type = st.sidebar.selectbox("Transaction Type", ["BUY","SELL"])

if st.sidebar.button("Submit"):
    if ticker:
        new_row = pd.DataFrame([[date, ticker.upper(), qty, price_input, txn_type]],
                               columns=["Date","Ticker","Quantity","Price","Type"])
        df = pd.concat([df, new_row], ignore_index=True)
        save_data(df)
        st.rerun()

df = load_data()

if df.empty:
    st.warning("No transactions yet.")
    st.stop()

# ---------------- TRANSACTION HISTORY ----------------
st.subheader("Transaction History")
st.dataframe(df)

row_to_delete = st.selectbox("Select index to delete", df.index)
if st.button("Delete Transaction"):
    df = df.drop(row_to_delete).reset_index(drop=True)
    save_data(df)
    st.rerun()

# ---------------- HOLDINGS FIX ----------------
buy_df = df[df["Type"]=="BUY"]
sell_df = df[df["Type"]=="SELL"]

buy_qty = buy_df.groupby("Ticker")["Quantity"].sum()
sell_qty = sell_df.groupby("Ticker")["Quantity"].sum()

holdings = buy_qty.subtract(sell_qty, fill_value=0)
holdings = holdings.reset_index()
holdings.columns=["Ticker","NetQty"]
holdings = holdings[holdings["NetQty"]>0]

if holdings.empty:
    st.warning("No active holdings.")
    st.stop()

# ---------------- LIVE PRICE ----------------
@st.cache_data(ttl=3600)
def fetch_price(t):
    try:
        return float(yf.Ticker(t).history(period="1d")["Close"].iloc[-1])
    except:
        return 0

holdings["CurrentPrice"] = holdings["Ticker"].apply(fetch_price)
holdings["CurrentValue"] = holdings["NetQty"] * holdings["CurrentPrice"]

# ---------------- PORTFOLIO METRICS ----------------
buy_df["Invested"] = buy_df["Quantity"] * buy_df["Price"]
sell_df["Received"] = sell_df["Quantity"] * sell_df["Price"]

total_invested = buy_df["Invested"].sum() - sell_df["Received"].sum()
current_value = holdings["CurrentValue"].sum()
profit_loss = current_value - total_invested
return_pct = (profit_loss / total_invested * 100) if total_invested != 0 else 0

c1,c2,c3,c4 = st.columns(4)
c1.metric("Total Invested", f"₹{total_invested:,.0f}")
c2.metric("Current Value", f"₹{current_value:,.0f}")
c3.metric("Profit / Loss", f"₹{profit_loss:,.0f}")
c4.metric("Return %", f"{return_pct:.2f}%")

# ---------------- ALLOCATION ----------------
st.subheader("Allocation")
fig_alloc = px.pie(holdings, values="CurrentValue", names="Ticker")
st.plotly_chart(fig_alloc, use_container_width=True)

# ---------------- RISK METRICS ----------------
st.subheader("Risk Metrics")
risk_data={}
for t in holdings["Ticker"]:
    data=yf.download(t,period="6mo",progress=False)
    if isinstance(data.columns,pd.MultiIndex):
        data.columns=data.columns.get_level_values(0)
    r=data["Close"].pct_change().dropna()
    if len(r)>0:
        vol=float(np.std(r)*np.sqrt(252))
        sharpe=float((np.mean(r)/np.std(r))*np.sqrt(252))
        risk_data[t]=[round(vol,3),round(sharpe,3)]

if risk_data:
    st.table(pd.DataFrame(risk_data,index=["Volatility","Sharpe"]).T)

# ---------------- TREND VIEWER ----------------
st.subheader("Stock Trend Viewer")
stock = st.selectbox("Select Stock", holdings["Ticker"])
hist = yf.download(stock,period="6mo",progress=False)

if isinstance(hist.columns,pd.MultiIndex):
    hist.columns=hist.columns.get_level_values(0)

hist["MA50"]=hist["Close"].rolling(50).mean()
hist["MA200"]=hist["Close"].rolling(200).mean()

st.plotly_chart(px.line(hist,y=["Close","MA50","MA200"]))

# ---------------- FUNDAMENTALS ----------------
st.subheader("Stock Fundamentals")

def format_market_cap(val):
    if val is None:
        return "N/A"
    if val>=1e12:
        return f"₹{val/1e12:.2f} T"
    if val>=1e9:
        return f"₹{val/1e9:.2f} B"
    return f"₹{val:,.0f}"

try:
    info=yf.Ticker(stock).info
    f1,f2,f3,f4=st.columns(4)
    f1.metric("PE",info.get("trailingPE","N/A"))
    f2.metric("EPS",info.get("trailingEps","N/A"))
    f3.metric("Market Cap",format_market_cap(info.get("marketCap")))
    f4.metric("Sector",info.get("sector","N/A"))
except:
    st.write("Fundamental data not available.")

# ---------------- PORTFOLIO HISTORY ----------------
st.subheader("Portfolio Historical Performance")
period=st.selectbox("Period",["3mo","6mo","1y","2y"])
pf=pd.DataFrame()

for _,row in holdings.iterrows():
    d=yf.download(row["Ticker"],period=period,progress=False)
    if isinstance(d.columns,pd.MultiIndex):
        d.columns=d.columns.get_level_values(0)
    pf[row["Ticker"]]=d["Close"]*row["NetQty"]

pf=pf.ffill().fillna(0)
pf["Value"]=pf.sum(axis=1)
pf=pf.reset_index()

st.plotly_chart(px.line(pf,x="Date",y="Value"))

# ---------------- NIFTY COMPARISON ----------------
nifty=yf.download("^NSEI",period=period,progress=False)
if isinstance(nifty.columns,pd.MultiIndex):
    nifty.columns=nifty.columns.get_level_values(0)

nifty=nifty["Close"].reset_index()
combo=pd.merge(pf,nifty,on="Date",how="left").dropna()

combo["Portfolio %"]=combo["Value"]/combo["Value"].iloc[0]*100
combo["Nifty %"]=combo["Close"]/combo["Close"].iloc[0]*100

st.plotly_chart(px.line(combo,x="Date",y=["Portfolio %","Nifty %"]))

st.caption("Educational use only. Not financial advice.")