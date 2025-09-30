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

def build_chartdata_from_data_sheet(spreadsheet_id, creds, coins):
    """
    Đọc sheet 'Data' (dạng long), pivot thành sheet 'ChartData' (dạng wide):
    Date | coin1_price | coin1_pct | coin2_price | coin2_pct | ...
    """
    service = build("sheets", "v4", credentials=creds)
    sh = client.open_by_key(spreadsheet_id)

    # Lấy sheet Data (phải tồn tại)
    try:
        data_ws = sh.worksheet("Data")
    except gspread.exceptions.WorksheetNotFound:
        raise Exception("Sheet 'Data' không tồn tại. Script cần sheet 'Data' để build ChartData.")

    all_vals = data_ws.get_all_values()
    if len(all_vals) <= 1:
        dates = []
        rows = []
    else:
        header = all_vals[0]
        rows = all_vals[1:]

    # Build dict: date -> coin -> {price, pct}
    data_map = {}
    for r in rows:
        # kỳ vọng Data format: [Date, Coin, Giá, %24h, RSI, Insight]
        if len(r) < 4:
            continue
        date = r[0].strip()
        coin = r[1].strip().lower()
        price = r[2].strip()
        pct = r[3].strip()
        # chuyển giá/pct sang số nếu có thể
        try:
            price_val = float(price.replace(",", "").replace(" ", ""))
        except:
            price_val = None
        try:
            pct_val = float(pct.replace("%", "").replace(",", "").strip())
        except:
            pct_val = None

        data_map.setdefault(date, {})
        data_map[date][coin] = {"price": price_val, "pct": pct_val}

    dates = sorted(data_map.keys())  # format YYYY-MM-DD nên sort lexicographically ok

    # Tạo header cho ChartData
    header = ["Date"]
    for coin in coins:
        header.append(f"{coin}_price")
        header.append(f"{coin}_pct24")

    # Build rows
    chart_rows = []
    for date in dates:
        row = [date]
        for coin in coins:
            coin_lower = coin.lower()
            entry = data_map.get(date, {}).get(coin_lower, {})
            price_val = entry.get("price")
            pct_val = entry.get("pct")
            # đưa giá/pct lên string (so Google Sheets dễ nhận)
            row.append("" if price_val is None else float(price_val))
            row.append("" if pct_val is None else float(pct_val))
        chart_rows.append(row)

    # Ghi vào sheet ChartData (tạo nếu chưa có)
    try:
        chart_ws = sh.worksheet("ChartData")
    except gspread.exceptions.WorksheetNotFound:
        # đặt index=2 để Charts(0) và Data(1) có thể đứng trước (sau sẽ reorder)
        chart_ws = sh.add_worksheet(title="ChartData", rows=str(max(100, len(chart_rows)+5)), cols=str(len(header)), index=2)

    # Clear và ghi dữ liệu
    chart_ws.clear()
    # chuẩn bị range dữ liệu toàn bộ
    # append_row từng hàng hơi chậm, ta dùng batch_update values
    values = [header] + chart_rows
    chart_ws.update("A1", values, value_input_option="USER_ENTERED")

    print(f"✅ ChartData sheet updated ({len(chart_rows)} rows).")
    return chart_ws._properties["sheetId"], len(chart_rows)  # trả về sheetId và số hàng dữ liệu
# ===============================
# Hàm vẽ Charts gom vào 1 sheet
# ===============================
def create_charts_in_one_sheet(spreadsheet_id, creds, coins):
    """
    Tạo (hoặc refresh) sheet 'Charts' và vẽ 1 chart/coin dựa trên ChartData:
    - X axis: Date (col A)
    - Series1: price (left axis)
    - Series2: %24 (right axis)
    """
    service = build("sheets", "v4", credentials=creds)

    # Đảm bảo ChartData tồn tại và được cập nhật
    chartdata_sheet_id, nrows = build_chartdata_from_data_sheet(spreadsheet_id, creds, coins)

    # Load spreadsheet metadata để tìm/tao sheet Charts
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = spreadsheet.get("sheets", [])
    sheet_map = {s["properties"]["title"]: s["properties"]["sheetId"] for s in sheets}

    if "Charts" not in sheet_map:
        # tạo sheet Charts (nếu chưa có) đặt index=0 tạm (sẽ reorder sau)
        resp = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={
            "requests": [{"addSheet": {"properties": {"title": "Charts"}}}]
        }).execute()
        charts_sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
        # refresh metadata
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet.get("sheets", [])
        sheet_map = {s["properties"]["title"]: s["properties"]["sheetId"] for s in sheets}
    else:
        charts_sheet_id = sheet_map["Charts"]

    # Xóa chart cũ trên sheet Charts (nếu có)
    charts_sheet_obj = next((s for s in sheets if s["properties"]["title"] == "Charts"), None)
    if charts_sheet_obj:
        existing_charts = charts_sheet_obj.get("charts", []) or []
        delete_reqs = [{"deleteEmbeddedObject": {"objectId": c["chartId"]}} for c in existing_charts]
        if delete_reqs:
            service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": delete_reqs}).execute()

    # Tạo chart cho mỗi coin (dựa trên sheet ChartData)
    requests = []
    # ChartData layout: A = Date, then for i, price at col 1 + i*2, pct at col 2 + i*2
    # startRowIndex = 1 (bỏ header), endRowIndex = nrows+1
    for i, coin in enumerate(coins):
        price_col = 1 + i * 2
        pct_col = price_col + 1

        chart_request = {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": f"{coin.capitalize()} — Price & %24",
                        "basicChart": {
                            "chartType": "LINE",
                            "legendPosition": "BOTTOM_LEGEND",
                            "axis": [
                                {"position": "BOTTOM_AXIS", "title": "Date"},
                                {"position": "LEFT_AXIS", "title": "Price (USD)"},
                                {"position": "RIGHT_AXIS", "title": "% Change (24h)"},
                            ],
                            "domains": [
                                {
                                    "domain": {
                                        "sourceRange": {
                                            "sources": [{
                                                "sheetId": chartdata_sheet_id,
                                                "startRowIndex": 1,
                                                "endRowIndex": max(2, nrows + 1),
                                                "startColumnIndex": 0,
                                                "endColumnIndex": 1
                                            }]
                                        }
                                    }
                                }
                            ],
                            "series": [
                                {
                                    "series": {
                                        "sourceRange": {
                                            "sources": [{
                                                "sheetId": chartdata_sheet_id,
                                                "startRowIndex": 1,
                                                "endRowIndex": max(2, nrows + 1),
                                                "startColumnIndex": price_col,
                                                "endColumnIndex": price_col + 1
                                            }]
                                        }
                                    },
                                    "targetAxis": "LEFT_AXIS"
                                },
                                {
                                    "series": {
                                        "sourceRange": {
                                            "sources": [{
                                                "sheetId": chartdata_sheet_id,
                                                "startRowIndex": 1,
                                                "endRowIndex": max(2, nrows + 1),
                                                "startColumnIndex": pct_col,
                                                "endColumnIndex": pct_col + 1
                                            }]
                                        }
                                    },
                                    "targetAxis": "RIGHT_AXIS"
                                }
                            ]
                        }
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": charts_sheet_id,
                                "rowIndex": i * 20,
                                "columnIndex": 0
                            }
                        }
                    }
                }
            }
        }
        requests.append(chart_request)

    if requests:
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()

    print("📊 Charts updated in 'Charts' sheet (price + %24 per coin).")
    return

# ===============================
# Hàm reorder sheet
# ===============================
def reorder_sheets(spreadsheet_id, creds):
    """
    Đặt thứ tự: Charts (index 0), Data (index 1), ChartData (index 2) nếu có
    """
    service = build("sheets", "v4", credentials=creds)
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()

    sheet_map = {s["properties"]["title"]: s["properties"]["sheetId"] for s in spreadsheet["sheets"]}
    requests = []

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
    if "ChartData" in sheet_map:
        requests.append({
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_map["ChartData"], "index": 2},
                "fields": "index"
            }
        })

    if requests:
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()
        print("📑 Sheets reordered: Charts first, Data second, ChartData third.")
        
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

    update_google_sheet(rows)  # ghi vào 'Data'
    create_charts_in_one_sheet(SPREADSHEET_ID, creds, coins)  # build ChartData + tạo charts
    reorder_sheets(SPREADSHEET_ID, creds)
