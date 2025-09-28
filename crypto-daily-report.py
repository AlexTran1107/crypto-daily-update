import os
import requests
import gspread
import json
from google.oauth2 import service_account
import pandas as pd
from datetime import datetime
from googleapiclient.discovery import build

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
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# ===============================
# Hàm sinh Insight
# ===============================
def generate_insight(coin_name, price, change_24h, rsi):
    analysis = []

    # Xu hướng 24h
    if change_24h > 5:
        analysis.append("Đà tăng mạnh, hút dòng tiền.")
    elif change_24h < -5:
        analysis.append("Áp lực bán cao, rủi ro giảm thêm.")
    else:
        analysis.append("Biến động nhẹ, xu hướng chưa rõ ràng.")

    # RSI
    if rsi > 70:
        analysis.append("RSI quá mua → khả năng điều chỉnh.")
    elif rsi < 30:
        analysis.append("RSI quá bán → có thể hồi phục ngắn hạn.")
    else:
        analysis.append("RSI cân bằng → xu hướng bền vững.")

    # Đề xuất hành động
    if change_24h > 3 and rsi < 70:
        analysis.append("Có thể cân nhắc mua thêm.")
    elif change_24h < -3 and rsi > 30:
        analysis.append("Có thể chờ thêm để mua vùng thấp hơn.")
    else:
        analysis.append("Nên quan sát thêm trước khi hành động.")

    return f"🔎 {coin_name}: " + " ".join(analysis)

# ===============================
# Hàm tính RSI (giản lược)
# ===============================
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50  # default trung tính

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
# Lấy dữ liệu từ CoinGecko
# ===============================
def fetch_crypto_data(coin_ids):
    url = f"https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ",".join(coin_ids),
        "vs_currencies": "usd",
        "include_24hr_change": "true"
    }
    response = requests.get(url, params=params)
    data = response.json()

    # Giả lập giá lịch sử để tính RSI (demo)
    results = []
    for coin in coin_ids:
        price = data[coin]["usd"]
        change_24h = data[coin].get("usd_24h_change", 0)
        fake_prices = [price * (1 + (change_24h/100) * (i/15)) for i in range(15)]  # mô phỏng
        rsi = calculate_rsi(fake_prices)

        results.append({
            "name": coin,
            "price": price,
            "change_24h": round(change_24h, 2),
            "rsi": rsi
        })

    return results

# ===============================
# Update Google Sheet
# ===============================
def update_google_sheet(rows):
    sh = client.open_by_key(SPREADSHEET_ID)
    
    # Nếu chưa có sheet Data thì tạo
    try:
        worksheet = sh.worksheet("Data")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title="Data", rows="1000", cols="20")

        # Tạo header
        header = ["Date", "Coin", "Giá (USD)", "% 24h", "RSI", "Phân tích"]
        worksheet.append_row(header)

    # Thêm dữ liệu mới (append theo ngày)
    today = datetime.now().strftime("%Y-%m-%d")
    for row in rows:
        worksheet.append_row([today] + row)

    # ===== Format Header =====
    fmt = {
        "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.86},  # xanh dương đậm
        "horizontalAlignment": "CENTER",
        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
    }
    worksheet.format("A1:E1", fmt)

    # ===== Auto resize columns =====
    worksheet.resize(len(rows) + 1, len(header))
    worksheet.spreadsheet.batch_update({
        "requests": [
            {"autoResizeDimensions": {
                "dimensions": {"sheetId": worksheet._properties['sheetId'], "dimension": "COLUMNS", "startIndex": 0, "endIndex": len(header)}
            }}
        ]
    })

    print("✅ Google Sheet updated with formatting!")
# ===============================
# Hàm vẽ Charts gom vào 1 sheet
# ===============================
def create_charts_in_one_sheet(spreadsheet_id, creds, coins):
    service = build("sheets", "v4", credentials=creds)

    # Lấy spreadsheet info
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_map = {s["properties"]["title"]: s["properties"]["sheetId"] for s in spreadsheet["sheets"]}

    # Nếu chưa có sheet "Charts" thì tạo
    if "Charts" not in sheet_map:
        add_sheet_req = {
            "addSheet": {"properties": {"title": "Charts"}}
        }
        resp = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [add_sheet_req]}
        ).execute()
        charts_sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    else:
        charts_sheet_id = sheet_map["Charts"]

    # Xóa chart cũ trong sheet "Charts"
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id, includeGridData=False).execute()
    charts = spreadsheet.get("sheets", [])[0].get("charts", [])
    delete_reqs = [{"deleteEmbeddedObject": {"objectId": chart["chartId"]}} for chart in charts]
    if delete_reqs:
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": delete_reqs}).execute()

    # Tạo chart mới cho mỗi coin
    requests = []
    start_row = 0
    for coin in coins:
        requests.append({
            "addChart": {
                "chart": {
                    "spec": {
                        "title": f"Price history of {coin}",
                        "basicChart": {
                            "chartType": "LINE",
                            "legendPosition": "BOTTOM_LEGEND",
                            "axis": [
                                {"position": "BOTTOM_AXIS", "title": "Date"},
                                {"position": "LEFT_AXIS", "title": "Price (USD)"}
                            ],
                            "domains": [{
                                "domain": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": sheet_map["Data"],
                                            "startRowIndex": 1,
                                            "endRowIndex": 1000,  # đủ dữ liệu 1000 ngày
                                            "startColumnIndex": 0,
                                            "endColumnIndex": 1
                                        }]
                                    }
                                }
                            }],
                            "series": [{
                                "series": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": sheet_map["Data"],
                                            "startRowIndex": 1,
                                            "endRowIndex": 1000,
                                            "startColumnIndex": coins.index(coin)+1,
                                            "endColumnIndex": coins.index(coin)+2
                                        }]
                                    }
                                },
                                "targetAxis": "LEFT_AXIS"
                            }]
                        }
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": charts_sheet_id,
                                "rowIndex": start_row,
                                "columnIndex": 0
                            }
                        }
                    }
                }
            }
        })
        start_row += 20  # dịch vị trí chart xuống để không chồng nhau

    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()
    print("📊 Charts updated!")

# ===============================
# Hàm reorder sheet
# ===============================
def reorder_sheets(spreadsheet_id, creds):
    service = build("sheets", "v4", credentials=creds)
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()

    requests = []
    sheet_map = {s["properties"]["title"]: s["properties"]["sheetId"] for s in spreadsheet["sheets"]}

    if "Charts" in sheet_map:
        requests.append({
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_map["Charts"], "index": 0},
                "fields": "index"
            }
        })
    if "Data" in sheet_map:
        requests.append({
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_map["Data"], "index": 1},
                "fields": "index"
            }
        })

    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()
        print("📑 Sheets reordered!")
        
# ===============================
# Main
# ===============================
if __name__ == "__main__":
    coins = ["bitcoin", "ethereum", "render-token"]

    data = fetch_crypto_data(coins)
    rows = []
    for coin in data:
        insight = generate_insight(coin["name"], coin["price"], coin["change_24h"], coin["rsi"])
        rows.append([coin["name"], coin["price"], coin["change_24h"], coin["rsi"], insight])

    update_google_sheet(rows)  # B1: update data
    create_charts_in_one_sheet(SPREADSHEET_ID, creds, coins)  # B2: update charts
    reorder_sheets(SPREADSHEET_ID, creds)  # B3: reorder vị trí sheet
