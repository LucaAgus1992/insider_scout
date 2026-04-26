"""
Insider Buying Scout
Scrapes OpenInsider for top insider purchases and sends a weekly email report.
"""

import os
import smtplib
import requests
from bs4 import BeautifulSoup
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta


# ── Config (set as GitHub Secrets or env vars) ──────────────────────────────
SENDER_EMAIL    = os.environ["SENDER_EMAIL"]     # your Gmail address
SENDER_PASSWORD = os.environ["SENDER_PASSWORD"]  # Gmail App Password
RECIPIENT_EMAIL = os.environ["RECIPIENT_EMAIL"]  # where to send the report

# How many top buys to include in the report
TOP_N = 20

# Minimum transaction value in USD (filters out tiny/cosmetic buys)
MIN_VALUE_USD = 50_000


def fetch_insider_buys() -> list[dict]:
    """
    Scrapes OpenInsider for the latest cluster/CEO/CFO buys sorted by value.
    Uses the free public screener — no API key needed.
    """
    url = (
        "http://openinsider.com/screener?"
        "s=&o=&pl=&ph=&ll=&lh=&fd=30&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago=&"
        "xp=1&xs=1&vl=50&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&"
        "nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=5&"
        "cnt=100&Action=Filter"
    )

    headers = {"User-Agent": "Mozilla/5.0 (compatible; InsiderScout/1.0)"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"class": "tinytable"})
    if not table:
        raise RuntimeError("Could not find insider table on OpenInsider.")

    rows = table.find_all("tr")[1:]  # skip header
    buys = []

    for row in rows:
        cols = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cols) < 13:
            continue

        # OpenInsider columns:
        # 0:filing_date 1:trade_date 2:ticker 3:company 4:insider_name
        # 5:title 6:trade_type 7:price 8:qty 9:owned 10:own_chg
        # 11:value 12:1d 13:1w 14:1m 15:6m

        trade_type = cols[6]
        if trade_type != "P - Purchase":
            continue

        raw_value = cols[11].replace("$", "").replace(",", "").replace("+", "")
        try:
            value_usd = int(float(raw_value))
        except ValueError:
            continue

        if value_usd < MIN_VALUE_USD:
            continue

        buys.append({
            "filing_date":  cols[0],
            "trade_date":   cols[1],
            "ticker":       cols[2],
            "company":      cols[3],
            "insider":      cols[4],
            "title":        cols[5],
            "price":        cols[7],
            "qty":          cols[8],
            "value_usd":    value_usd,
            "own_chg":      cols[10],
        })

    # Sort by value descending, take top N
    buys.sort(key=lambda x: x["value_usd"], reverse=True)
    return buys[:TOP_N]


def format_usd(n: int) -> str:
    if n >= 1_000_000:
        return f"${n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"${n/1_000:.0f}K"
    return f"${n}"


def build_html(buys: list[dict]) -> str:
    today = datetime.now().strftime("%d %B %Y")
    rows_html = ""

    for i, b in enumerate(buys, 1):
        bg = "#f9f9f9" if i % 2 == 0 else "#ffffff"
        value_str = format_usd(b["value_usd"])
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:8px 12px;font-weight:600;color:#1a1a1a;">{i}</td>
          <td style="padding:8px 12px;">
            <span style="font-weight:700;color:#1a56db;">{b['ticker']}</span><br>
            <span style="font-size:12px;color:#555;">{b['company']}</span>
          </td>
          <td style="padding:8px 12px;">
            {b['insider']}<br>
            <span style="font-size:12px;color:#888;">{b['title']}</span>
          </td>
          <td style="padding:8px 12px;text-align:right;font-weight:700;color:#0f7b3c;font-size:15px;">{value_str}</td>
          <td style="padding:8px 12px;text-align:right;color:#333;">{b['price']}</td>
          <td style="padding:8px 12px;text-align:right;color:#333;">{b['qty']}</td>
          <td style="padding:8px 12px;text-align:right;color:#888;font-size:12px;">{b['trade_date']}</td>
        </tr>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,sans-serif;
             background:#f4f6f8;margin:0;padding:20px;">
  <div style="max-width:800px;margin:0 auto;background:#fff;border-radius:12px;
              overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">

    <div style="background:#1a1a2e;padding:28px 32px;">
      <h1 style="margin:0;color:#fff;font-size:22px;font-weight:600;">
        Insider Buying Scout
      </h1>
      <p style="margin:6px 0 0;color:#a0aec0;font-size:14px;">
        Top {TOP_N} open-market purchases (codice P) — settimana del {today}
      </p>
    </div>

    <div style="padding:20px 32px 8px;">
      <p style="margin:0;font-size:13px;color:#888;">
        Filtro: acquisti &gt; {format_usd(MIN_VALUE_USD)} &bull; Solo codice P (open market) &bull;
        Fonte: <a href="http://openinsider.com" style="color:#1a56db;">OpenInsider</a> / SEC Form 4
      </p>
    </div>

    <div style="padding:0 16px 16px;">
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
          <tr style="background:#f0f4ff;">
            <th style="padding:10px 12px;text-align:left;color:#555;font-weight:600;">#</th>
            <th style="padding:10px 12px;text-align:left;color:#555;font-weight:600;">Ticker / Società</th>
            <th style="padding:10px 12px;text-align:left;color:#555;font-weight:600;">Insider</th>
            <th style="padding:10px 12px;text-align:right;color:#555;font-weight:600;">Valore</th>
            <th style="padding:10px 12px;text-align:right;color:#555;font-weight:600;">Prezzo</th>
            <th style="padding:10px 12px;text-align:right;color:#555;font-weight:600;">Qty</th>
            <th style="padding:10px 12px;text-align:right;color:#555;font-weight:600;">Data</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>

    <div style="padding:16px 32px;background:#f9fafb;border-top:1px solid #eee;">
      <p style="margin:0;font-size:11px;color:#aaa;">
        Questo report e' generato automaticamente a scopo informativo e non costituisce
        consulenza finanziaria. Verifica sempre i dati prima di prendere decisioni di investimento.
      </p>
    </div>

  </div>
</body>
</html>"""


def send_email(html_body: str, n_buys: int) -> None:
    today = datetime.now().strftime("%d/%m/%Y")
    subject = f"Insider Buying Scout — Top {n_buys} acquisti ({today})"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())

    print(f"Email inviata a {RECIPIENT_EMAIL} con {n_buys} insider buys.")


def main():
    print("Fetching insider buys from OpenInsider...")
    buys = fetch_insider_buys()

    if not buys:
        print("Nessun acquisto trovato con i filtri impostati.")
        return

    print(f"Trovati {len(buys)} acquisti. Costruisco email...")
    html = build_html(buys)
    send_email(html, len(buys))
    print("Fatto!")


if __name__ == "__main__":
    main()
