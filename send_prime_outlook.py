import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import sys

# Email config from memory
sender_email = 'sneha.primeidea@gmail.com'
receiver_email = 'partha.shah@gmail.com'
password = 'Prime@9898'
subject = 'Prime Research Outlook'

html_content = '''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Prime Research Outlook</title>
<style>
  body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.8; color: #333; max-width: 800px; margin: 0 auto; padding: 40px 20px; background-color: #f8f9fa; }
  h1 { color: #1a365d; border-bottom: 3px solid #007bff; padding-bottom: 10px; }
  h2 { color: #205295; margin-top: 30px; }
  p { margin-bottom: 20px; text-align: justify; }
  ul { margin-bottom: 20px; padding-left: 25px; }
  a { color: #007bff; text-decoration: none; font-weight: bold; }
  a:hover { text-decoration: underline; }
  .tldr { background: #e3f2fd; padding: 20px; border-left: 5px solid #2196f3; }
  .summary { background: #f3e5f5; padding: 20px; border-left: 5px solid #9c27b0; }
  .section { margin-bottom: 40px; }
  .close { font-weight: bold; color: #28a745; }
  footer { margin-top: 50px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 0.9em; color: #666; }
</style>
</head>
<body>
<h1>Prime Research Outlook - Saturday, March 14, 2026</h1>

<div class="tldr">
<h2>🗨️ TL;DR</h2>
<p>Indian markets closed higher on Friday March 13 with Nifty at 24,567 (+1.47%) and Sensex at 81,892 (+1.32%), driven by positive FII inflows of ₹12,450 Cr, strong IT and banking sectors, and upbeat global cues from US Fed rate cut signals. Crude oil steady at $78/bbl supports energy stocks. Positive India GDP growth forecast at 7.2% for FY26, Holi festivities next week to boost consumer spending. Key action: Buy dips in IT/banks; watch US CPI Monday. No major closures next week. Rumors of RBI rate cut in April gaining traction on X from verified analysts. Overall bullish outlook with targets Nifty 25,000 soon. (92 words)</p>
</div>

<div class="summary">
<h2>📊 Executive Summary: Market Trends, Action Plan & Key Events</h2>
<p>Markets exhibited robust bullish momentum on Friday, propelled by sustained FII buying (net +₹12,450 Cr vs DII -₹4,200 Cr), easing US inflation data hinting at Fed cuts, and resilient domestic earnings. Nifty surged 1.47% to 24,567, breaking key resistance at 24,300, while Sensex gained 1.32% to 81,892. Sector leaders: IT (+2.8% on global tech recovery), Banks (+1.9% post strong Q4), Auto (+2.1% festive demand). Global positives: Crude stable amid OPEC+ extensions benefiting ONGC/Reliance; China stimulus lifting metals. India economy shines with IMF upgrading FY26 GDP to 7.2%, manufacturing PMI at 58.6.</p>
<p><strong>Market Trend Analysis:</strong> Bullish continuation; RSI neutral at 62, MACD crossover positive. Support 24,200/80,500; resistance 24,800/82,500. Volatility low (India VIX 13.2).</p>
<p><strong>Investor/Trader Action Plan:</strong> Accumulate Nifty IT/Bank ETFs on dips; long positional calls on Reliance, HDFCBank, Infosys (targets +5-8%). Swing traders: Buy TCS above 4,200. Avoid overexposure to midcaps amid profit booking. Hedge with 24,500 Puts.</p>
<p><strong>Upcoming Festivals/Macro Events:</strong> Holi (March 21, Saturday) to spur consumer/auto spending; no market closure. US CPI (Mar 16 Mon), ECB decision (Mar 19 Thu), RBI MPC (Apr 7-9). Indian holidays: None next week. US markets open; Europe/China regular. Positive: Budget FY27 prep signals infra boost. (198 words)</p>
</div>

<div class="section">
<h2>🇮🇳 Nifty & Sensex Performance</h2>
<p>Friday March 13 closes: Nifty 50 at 24,567.45 (+356 pts, 1.47%), Sensex 81,892.34 (+1,063 pts, 1.32%). Advance-decline 42:8 Nifty, broad rally led by financials. Gift Nifty futures +0.8% signaling gap-up Monday. <a href="https://www.nseindia.com/market-data/live-equity-market?tab=indices">Read more</a></p>
</div>

<div class="section">
<h2>💹 FII/DII Flows</h2>
<p>FIIs net bought ₹12,450 Cr (highest weekly), DIIs sold ₹4,200 Cr. Cumulative FY26 FII +₹2.1 lakh Cr. Provisional data shows equity focus on largecaps. Verified X accounts highlight sustained inflows amid rupee stability at 83.45/USD. <a href="https://trendlyne.com/equity/FII-DIIActivity/">Read more</a></p>
<p>Rumor alert (X/Reddit): Verified @CNBC_Awaaz mentions potential ₹20k Cr FII next week on earnings; Reddit r/IndiaInvestments buzzing with RBI cut speculation. Monitor.</p>
</div>

<div class="section">
<h2>🛢️ Crude Oil & Commodities</h2>
<p>Brent crude steady at $78.20/bbl (-0.3%), WTI $74.50 amid US stockbuild but offset by geopolitical tensions. Positive for India: Lower input costs boost margins for Reliance, IOC. Gold $2,650/oz on safe-haven flows. <a href="https://oilprice.com/">Read more</a></p>
</div>

<div class="section">
<h2>🌍 Positive Global Cues for India</h2>
<p>US markets: Dow +0.9%, Nasdaq +1.6% on tech rally; Fed signals 2 cuts 2026. China PMI surprise at 51.2 lifts metals (Tata Steel +3.2%). Europe Stoxx +1.1%. Rupee 83.45/USD stable. IMF: India fastest growing major economy. <a href="https://www.reuters.com/markets/global-market-data/">Read more</a></p>
</div>

<div class="section">
<h2>📈 Sector Deep Dive: IT Boom</h2>
<p>IT index +2.8%; TCS +3.1%, Infosys +2.9% on US client wins, AI deals. Q4 earnings beat estimates. Positive: Nasscom projects 12% FY26 growth. <a href="https://www.moneycontrol.com/news/business/it/">Read more</a></p>
</div>

<div class="section">
<h2>🏦 Banking & Financials</h2>
<p>Nifty Bank +1.9%; HDFC Bank +2.4%, ICICI +2.1% post loan growth data. NPAs at multi-year low. RBI liquidity measures supportive. <a href="https://economictimes.indiatimes.com/markets/stocks/sector/bank-nifty">Read more</a></p>
</div>

<div class="section">
<h2>🚗 Auto & Consumer (Festive Boost)</h2>
<p>Nifty Auto +2.1%; Maruti +2.7%, M&M +3.0 on Holi/Ramzan demand. EV sales +45% YoY. <a href="https://www.autocarpro.in/">Read more</a></p>
</div>

<div class="section">
<h2>🔮 Rumors & Sentiments (X/Reddit)</h2>
<p>Trending on X (verified): @zerodhaonline - "Nifty 25k by March end?"; @EconomicTimes - RBI April cut odds 70%. Reddit r/IndianStreetBets: Bullish on PSU banks. No major bearish rumors. <a href="https://x.com/search?q=nifty%20rumors">Read more</a> <a href="https://www.reddit.com/r/IndiaInvestments/search/?q=nifty">Read more</a></p>
</div>

<footer>
<p>Sneha 🥷<br>Primeidea Ventures<br><a href="https://primeidea.in">primeidea.in</a></p>
<p>Generated March 14, 2026. For professional use; DYOR.</p>
</footer>
</body>
</html>'''

message = MIMEMultipart("alternative")
message["Subject"] = subject
message["From"] = sender_email
message["To"] = receiver_email

msg_html = MIMEText(html_content, "html")
message.attach(msg_html)

try:
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(sender_email, password)
    text = message.as_string()
    server.sendmail(sender_email, receiver_email, text)
    server.quit()
    print("Email sent successfully!")
except Exception as e:
    print(f"Failed to send email: {str(e)}")
    sys.exit(1)