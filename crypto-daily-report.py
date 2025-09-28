import requests
import gspread
from google.oauth2 import service_account
from datetime import datetime

COINS = ["bitcoin", "ethereum", "render-token"]
CURRENCY = "usd"
DAYS = 1   # chỉ cần giá 24h

# Google Sheets config
SPREADSHEET_ID = "1gTApRPuekyFfPEUAvOe8yTx5WZoE-WYepzC1InZCr-c"
NEW_SHEET_NAME = datetime.now().strftime("%Y-%m-%d")  # mỗi ngày 1 sheet mới
SERVICE_ACCOUNT_FILE = "/Users/alextran/Downloads/Automation/crypto-daily-update/crypto-daily-update.json"  # file json bạn tải từ Google

def fetch_data(coin):
    url = f"https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": coin, "vs_currencies": CURRENCY, "include_24hr_change": "true"}
    r = requests.get(url, params=params).json()
    price = r[coin][CURRENCY]
    change = r[coin][f"{CURRENCY}_24h_change"]
    return price, change

def update_google_sheet(data):
    SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)

    sh = client.open_by_key(SPREADSHEET_ID)
    try:
        worksheet = sh.add_worksheet(title=NEW_SHEET_NAME, rows="100", cols="10")
    except:
        worksheet = sh.worksheet(NEW_SHEET_NAME)

    worksheet.update("A1", [["Coin", "Price (USD)", "Change 24h (%)"]])
    worksheet.update(f"A2:C{len(data)+1}", data)

if __name__ == "__main__":
    rows = []
    for coin in COINS:
        price, change = fetch_data(coin)
        rows.append([coin.upper(), f"{price:,.2f}", f"{change:+.2f}%"])
    update_google_sheet(rows)
    print("✅ Report updated to Google Sheet!")
