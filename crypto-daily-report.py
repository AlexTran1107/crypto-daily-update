import os
import requests
import gspread
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime

# ===============================
# Google Sheet Setup
# ===============================
SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GSHEET_CREDENTIALS = os.getenv("GSHEET_CREDENTIALS")

if not SPREADSHEET_ID or not GSHEET_CREDENTIALS:
    raise Exception("⚠️ Missing GOOGLE_SHEET_ID or GSHEET_CREDENTIALS environment variables!")

creds_dict = json.loads(GSHEET_CREDENTIALS)
creds = service_account.Credentials.from_service_account_info(
    creds_dict,
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
)
client = gspread.authorize(creds)
sheets_api = build("sheets", "v4", credentials=creds)

# ===============================
# RSI Calculation
# ===============================
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)

# ===============================
# Fetch Data
# ===============================
def fetch_crypto_data(coin_ids):
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ",".join(coin_ids),
        "vs_currencies": "usd",
        "include_24hr_change": "true"
    }
    response = requests.get(url, params=params)
    data = response.json()

    results = []
    for coin in coin_ids:
        price = data[coin]["usd"]
        change_24h = data[coin].get("usd_24h_change", 0)
        fake_prices = [price * (1 + (change_24h/100) * (i/15)) for i in range(15)]
        rsi = calculate_rsi(fake_prices)
        results.append({
            "name": coin,
            "price": round(price, 2),
            "change_24h": round(change_24h, 2),
            "rsi": rsi
        })
    return results

# ===============================
# Update Data Sheet
# ===============================
def update_google_sheet(rows):
    sh = client.open_by_key(SPREADSHEET_ID)

    # Tạo hoặc lấy sheet Data
    try:
        worksheet = sh.worksheet("Data")
    except gspread.WorksheetNotFound:
        worksheet = sh.add_worksheet(title="Data", rows="1000", cols="10")

    # Nếu sheet trống → thêm header
    if not worksheet.get_all_values():
        header = ["Date", "Coin", "Price (USD)", "% 24h", "RSI", "Insight"]
        worksheet.append_row(header)
        worksheet.format("A1:F1", {
            "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.86},
            "horizontalAlignment": "CENTER",
            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
        })

    # Append dữ liệu mới
    today = datetime.now().strftime("%Y-%m-%d")
    for row in rows:
        worksheet.append_row([today] + row)

    print("✅ Data sheet updated!")
    return worksheet


# ===============================
# Create Charts
# ===============================
def create_charts_in_one_sheet(spreadsheet_id, creds, coin_ids):
    service = build("sheets", "v4", credentials=creds)

    # Lấy sheet list
    sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = sheet_metadata.get("sheets", [])
    sheet_map = {s["properties"]["title"]: s["properties"]["sheetId"] for s in sheets}

    # Đảm bảo có sheet Chart
    if "Chart" not in sheet_map:
        body = {"requests": [{"addSheet": {"properties": {"title": "Chart"}}}]}
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()

    # Refresh lại map
    sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_map = {s["properties"]["title"]: s["properties"]["sheetId"] for s in sheet_metadata.get("sheets", [])}

    data_sheet_id = sheet_map["Data"]
    chart_sheet_id = sheet_map["Chart"]

    requests = []
    start_row = 1

    for coin in coin_ids:
        chart_title = f"{coin.upper()} - Price vs %24h Change"
        requests.append({
            "addChart": {
                "chart": {
                    "spec": {
                        "title": chart_title,
                        "basicChart": {
                            "chartType": "LINE",
                            "legendPosition": "BOTTOM_LEGEND",
                            "axis": [
                                {"position": "BOTTOM_AXIS", "title": "Date"},
                                {"position": "LEFT_AXIS", "title": "Price (USD)"},
                                {"position": "RIGHT_AXIS", "title": "% 24h"}
                            ],
                            "domains": [
                                {"domain": {"sourceRange": {"sources": [{
                                    "sheetId": data_sheet_id,
                                    "startRowIndex": 1,
                                    "startColumnIndex": 0,   # Date
                                    "endColumnIndex": 1
                                }]}}}
                            ],
                            "series": [
                                {   # Giá
                                    "series": {"sourceRange": {"sources": [{
                                        "sheetId": data_sheet_id,
                                        "startRowIndex": 1,
                                        "startColumnIndex": 2,
                                        "endColumnIndex": 3
                                    }]}},
                                    "targetAxis": "LEFT_AXIS",
                                    "type": "LINE"
                                },
                                {   # % 24h
                                    "series": {"sourceRange": {"sources": [{
                                        "sheetId": data_sheet_id,
                                        "startRowIndex": 1,
                                        "startColumnIndex": 3,
                                        "endColumnIndex": 4
                                    }]}},
                                    "targetAxis": "RIGHT_AXIS",
                                    "type": "LINE"
                                }
                            ]
                        }
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {"sheetId": chart_sheet_id, "rowIndex": start_row, "columnIndex": 0}
                        }
                    }
                }
            }
        })
        start_row += 20  # để chừa khoảng cách giữa các chart

    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()
    print("📊 Charts updated!")

# ===============================
# Main
# ===============================
if __name__ == "__main__":
    coins = ["bitcoin", "ethereum", "render-token"]
    data = fetch_crypto_data(coins)

    rows = []
    for coin in data:
        rows.append([
            coin["name"],
            coin["price"],
            coin["change_24h"],
            coin["rsi"]
        ])

    update_google_sheet(rows)
    create_charts_in_one_sheet(SPREADSHEET_ID, creds, coins)
