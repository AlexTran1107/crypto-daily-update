# crypto-daily-update
Update crypto chart daily

1. Create Google Service Account
- Vào Google Cloud Console
- Tạo một project mới → bật API Google Sheets API
- Vào APIs & Services > Credentials → tạo Service Account → download file JSON key về
- Trong Google Sheets (cái file bạn muốn cập nhật), share quyền Editor cho email của Service Account (kiểu như xxxx@project.iam.gserviceaccount.com)

2. Chuẩn bị Google Sheet
- Tạo sẵn 1 Google Sheet, ví dụ tên CryptoDailyReport
- Copy lại Spreadsheet ID (nằm trong URL: https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit)

3. Scripting by Python
4. Intergrate with Github Action
- Trong repo GitHub → Settings → Secrets → Actions → tạo secret:
- GSHEET_CREDENTIALS = nội dung file service_account.json
- Trong workflow report.yml, thay đoạn Run report bằng:
