import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from datetime import date
import os

# MLB Stats API abbreviation -> FanGraphs abbreviation where they differ
MLB_TO_FG = {
    "OAK": "ATH",
    "CWS": "CHW",
    "KC":  "KCR",
    "TB":  "TBR",
    "SD":  "SDP",
    "SF":  "SFG",
    "WSH": "WSN",
}

HEADERS = {
    "User-Agent": "libcurl/8.6.0 r-curl/5.2.1 httr/1.4.7"
}

ALL_TEAMS_URL = "https://www.fangraphs.com/roster-resource/closer-depth-chart"

# Day abbreviation pattern so we can insert a space: "Sun6/8" -> "Sun 6/8"
DAY_RE = re.compile(r"^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s*(\d)")


def fmt_date_hdr(raw: str) -> str:
    """Insert a space between day name and date: 'Sun6/8' -> 'Sun 6/8'."""
    return DAY_RE.sub(r"\1 \2", raw)


def scrape_all_teams() -> pd.DataFrame:
    try:
        resp = requests.get(ALL_TEAMS_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception:
        return pd.DataFrame()

    soup = BeautifulSoup(resp.text, "lxml")

    tables = soup.select(".closer-depth-charts table")
    if not tables:
        tables = soup.select("table")
    if not tables:
        return pd.DataFrame()

    all_rows = []
    for table in tables:
        thead = table.select_one("thead")
        tbody = table.select_one("tbody")
        if not tbody:
            continue

        date_hdrs = []
        if thead:
            date_hdrs = [
                fmt_date_hdr(el.get_text(strip=True))
                for el in thead.select('[data-stat="specialBullpenUsage"]')
            ]
        date_hdrs = date_hdrs[:6]
        while len(date_hdrs) < 6:
            date_hdrs.append(f"D{len(date_hdrs) + 1}")

        def get_txt(tr, stat):
            el = tr.select_one(f'[data-stat="{stat}"]')
            return el.get_text(strip=True) if el else ""

        seen = set()
        for tr in tbody.select("tr"):
            player = get_txt(tr, "PLAYER")
            role   = get_txt(tr, "PROJECTED ROLE")
            team   = get_txt(tr, "TEAM")

            if not player:
                continue
            if "IL" in role:
                continue
            key = (team, player)
            if key in seen:
                continue
            seen.add(key)

            usage_els  = tr.select('[data-stat="specialBullpenUsage"]')
            usage_vals = [el.get_text(strip=True) for el in usage_els[:6]]
            while len(usage_vals) < 6:
                usage_vals.append("")

            row = {
                "Team":    team,
                "Player":  player,
                "Thr":     get_txt(tr, "THR"),
                "Role":    role,
                "P (L6)":  get_txt(tr, "pitcherTotalsP"),
                "IP (L6)": get_txt(tr, "pitcherTotalsIP"),
            }
            for hdr, val in zip(date_hdrs, usage_vals):
                row[hdr] = val

            all_rows.append(row)

    return pd.DataFrame(all_rows)


def get_cached(abbr: str) -> pd.DataFrame:
    today = date.today().strftime("%Y-%m-%d")
    os.makedirs("data", exist_ok=True)
    all_path = f"data/all_teams_{today}.csv"

    if not os.path.exists(all_path):
        df_all = scrape_all_teams()
        if not df_all.empty:
            df_all.to_csv(all_path, index=False)
    else:
        df_all = pd.read_csv(all_path)

    if df_all.empty or "Team" not in df_all.columns:
        return pd.DataFrame(), []

    fg_abbr = MLB_TO_FG.get(abbr, abbr)
    match = df_all[df_all["Team"] == fg_abbr].copy()
    if match.empty:
        return pd.DataFrame(), []

    match = match.drop(columns=["Team"]).drop_duplicates(subset="Player").reset_index(drop=True)

    # Identify date columns (formatted as "Day M/D")
    date_cols = [c for c in match.columns if DAY_RE.match(c)]

    return match, date_cols
