import urllib.request
import urllib.parse
import json
import sys

BOT_TOKEN = "7815825495:AAEQ4d1I2hBjKrFLpoJcnXMK1iDXz1CQ7Jg"
CHAT_ID = "6483160"

text = ("📊 *Primeidea Live Market Brief*\n"
        "16 Apr 2026 | 09:35 PM IST\n\n"
        "Today's full HTML brief is ready. File: market_brief_2026-04-16_21-37-00.html")

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
data = {
    "chat_id": CHAT_ID,
    "text": text,
    "parse_mode": "Markdown",
}
req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(json.loads(resp.read()))
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
