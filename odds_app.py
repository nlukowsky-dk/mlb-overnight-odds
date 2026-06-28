import streamlit as st
import pandas as pd

st.set_page_config(page_title="MLB Overnight Historical Odds", layout="wide")

TEAM_ABBR = {
    "San Francisco Giants": "SF",
    "New York Mets": "NYM",
    "Milwaukee Brewers": "MIL",
    "Chicago Cubs": "CHC",
    "Baltimore Orioles": "BAL",
    "Cincinnati Reds": "CIN",
    "Houston Astros": "HOU",
    "Philadelphia Phillies": "PHI",
    "St. Louis Cardinals": "STL",
    "San Diego Padres": "SD",
    "Los Angeles Dodgers": "LAD",
    "Seattle Mariners": "SEA",
    "Toronto Blue Jays": "TOR",
    "Miami Marlins": "MIA",
    "Atlanta Braves": "ATL",
    "Kansas City Royals": "KC",
    "Arizona Diamondbacks": "ARI",
    "Washington Nationals": "WSH",
    "Detroit Tigers": "DET",
    "New York Yankees": "NYY",
    "Boston Red Sox": "BOS",
    "Chicago White Sox": "CWS",
    "Texas Rangers": "TEX",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Pittsburgh Pirates": "PIT",
    "Minnesota Twins": "MIN",
    "Los Angeles Angels": "LAA",
    "Athletics": "ATH",
    "Tampa Bay Rays": "TB",
}

MARKET_DEFS = [
    ("batter_strikeouts_alternate",  "Strikeouts",    True),
    ("batter_walks",                 "Walks",         False),
    ("batter_hits",                  "Hits",          False),
    ("batter_home_runs_alternate",   "Home Runs",     True),
    ("batter_singles",               "Singles",       False),
    ("batter_doubles",               "Doubles",       False),
    ("batter_triples_alternate",     "Triples",       True),
    ("batter_total_bases_alternate", "Total Bases",   True),
    ("batter_runs_scored",           "Runs",          False),
    ("batter_rbis",                  "RBIs",          False),
    ("batter_hits_runs_rbis",        "H+R+RBIs",      False),
    ("batter_stolen_bases",          "Stolen Bases",  False),
    ("pitcher_outs",                 "Outs",          False),
    ("pitcher_strikeouts",           "Strikeouts",    False),
    ("pitcher_walks",                "Walks Allowed", False),
    ("pitcher_hits_allowed",         "Hits Allowed",  False),
    ("pitcher_earned_runs",          "ERs Allowed",   False),
]

MARKET_LOOKUP = {m: (col, alt) for m, col, alt in MARKET_DEFS}
MARKET_ORDER  = [m for m, _, _ in MARKET_DEFS]


def fmt_american(odds):
    try:
        v = int(odds)
        return f"+{v}" if v > 0 else str(v)
    except (ValueError, TypeError):
        return ""


def fmt_point(point):
    try:
        f = float(point)
        return str(int(f)) if f == int(f) else str(f)
    except (ValueError, TypeError):
        return ""


def cell_nonalt(point, over_odds, under_odds):
    """Returns (point_str, over_str, under_str) for HTML rendering."""
    pt = fmt_point(point)   if not pd.isna(point)      else ""
    ov = fmt_american(over_odds)  if not pd.isna(over_odds)  else ""
    un = fmt_american(under_odds) if not pd.isna(under_odds) else ""
    return pt, ov, un


def cell_alt(point, over_odds, show_point=False):
    """Returns (point_str, over_str, under_str) — alt markets have no under."""
    ov = fmt_american(over_odds) if not pd.isna(over_odds) else ""
    pt = f"{int(float(point))}+" if (show_point and not pd.isna(point)) else ""
    return pt, ov, ""


@st.cache_data(ttl=3 * 3600)
def load_data():
    return pd.read_csv("odds_filtered.csv")


@st.cache_data
def get_players(df):
    return sorted(df["description"].dropna().unique().tolist())


def build_player_data(df, player):
    """
    Returns (games_df, col_order, cell_data) where:
      games_df  — one row per game with Date, Game
      col_order — list of display column names in order
      cell_data — dict[col_name][game_id] = (point, over, under) tuples
    """
    pf = df[df["description"] == player].copy()
    if pf.empty:
        return None, [], {}

    pf["price"] = pd.to_numeric(pf["price"], errors="coerce")
    pf["point"] = pd.to_numeric(pf["point"], errors="coerce")

    over_df  = pf[pf["side"] == "over"][
        ["id","market","commence_time","home_team","away_team","point","price"]
    ].rename(columns={"price": "over_price"})
    under_df = pf[pf["side"] == "under"][
        ["id","market","price"]
    ].rename(columns={"price": "under_price"})

    merged = over_df.merge(under_df, on=["id","market"], how="left")
    merged = merged.drop_duplicates(subset=["id","market"])

    merged["Date"]      = merged["commence_time"].str[5:10]
    merged["away_abbr"] = merged["away_team"].map(TEAM_ABBR).fillna(merged["away_team"])
    merged["home_abbr"] = merged["home_team"].map(TEAM_ABBR).fillna(merged["home_team"])
    merged["Game"]      = merged["away_abbr"] + " @ " + merged["home_abbr"]
    merged = merged.sort_values("commence_time", ascending=False)

    games = (
        merged[["id","commence_time","Date","Game"]]
        .drop_duplicates("id")
        .reset_index(drop=True)
    )

    col_order = []
    cell_data = {}
    seen_cols = set()

    for raw_market in MARKET_ORDER:
        if raw_market not in MARKET_LOOKUP:
            continue
        col_name, is_alt = MARKET_LOOKUP[raw_market]

        actual_col = col_name
        if col_name in seen_cols:
            actual_col = col_name + "_2"
        seen_cols.add(actual_col)

        subset = merged[merged["market"] == raw_market].set_index("id")
        if subset.empty:
            continue

        col_cells = {}
        for gid in games["id"]:
            if gid not in subset.index:
                col_cells[gid] = ("", "", "")
            elif is_alt:
                show_pt = raw_market in ("batter_strikeouts_alternate", "batter_total_bases_alternate")
                col_cells[gid] = cell_alt(subset.loc[gid, "point"], subset.loc[gid, "over_price"], show_pt)
            else:
                row = subset.loc[gid]
                col_cells[gid] = cell_nonalt(
                    row["point"], row["over_price"],
                    row.get("under_price", float("nan"))
                )

        # Only include column if at least one game has a value
        if any(any(v) for v in col_cells.values()):
            col_order.append(actual_col)
            cell_data[actual_col] = col_cells

    return games, col_order, cell_data


def render_cell(pt, ov, un):
    """Render a mixed-number style cell: large point on left, small over/under stacked on right."""
    if not pt and not ov and not un:
        return "<td></td>"

    def odds_color(val):
        return "color:#ef5350" if val.startswith("+") else "color:#4caf50"

    # Alt market with no point: just odds centered
    if not pt and not un:
        color = odds_color(ov)
        return (
            f'<td style="text-align:center; vertical-align:middle;">'
            f'<span style="font-size:15px;font-weight:600;{color}">{ov}</span>'
            f'</td>'
        )

    pt_html = f'<span style="font-size:20px;font-weight:700;color:#e0e0e0;line-height:1">{pt}</span>'

    # Milestone alt cell: point + single odds truly centered beside it (no stacking slots)
    if pt and ov and not un:
        ov_html = f'<span style="font-size:13px;font-weight:600;{odds_color(ov)};line-height:1">{ov}</span>'
        return (
            f'<td style="text-align:center;vertical-align:middle;white-space:nowrap;">'
            f'<span style="display:inline-flex;align-items:center;justify-content:center;gap:5px">'
            f'{pt_html}{ov_html}'
            f'</span>'
            f'</td>'
        )

    # Non-alt: point large on left, over/under stacked small on right
    ov_html = f'<span style="font-size:11px;font-weight:600;{odds_color(ov)};display:block;line-height:1.3;text-align:center">{ov}</span>' if ov else '<span style="display:block;line-height:1.3">&nbsp;</span>'
    un_html = f'<span style="font-size:11px;font-weight:600;{odds_color(un)};display:block;line-height:1.3;text-align:center">{un}</span>' if un else '<span style="display:block;line-height:1.3">&nbsp;</span>'

    odds_stack = (
        f'<span style="display:inline-flex;flex-direction:column;justify-content:center;'
        f'align-items:center;vertical-align:middle;margin-left:4px">'
        f'{ov_html}{un_html}'
        f'</span>'
    )

    return (
        f'<td style="text-align:center;vertical-align:middle;white-space:nowrap;">'
        f'<span style="display:inline-flex;align-items:center;justify-content:center;">'
        f'{pt_html}{odds_stack}'
        f'</span>'
        f'</td>'
    )


def build_html_table(games, col_order, cell_data):
    col_labels = {c: c.replace("_2", "") for c in col_order}

    # Header
    th_date = '<th style="text-align:left;padding:8px 12px;white-space:nowrap;">Date</th>'
    th_game = '<th style="text-align:left;padding:8px 12px;white-space:nowrap;">Game</th>'
    market_ths = "".join(
        f'<th style="text-align:center;padding:8px 10px;white-space:nowrap;">{col_labels[c]}</th>'
        for c in col_order
    )
    header = f"<thead><tr>{th_date}{th_game}{market_ths}</tr></thead>"

    # Rows
    rows = []
    for _, game_row in games.iterrows():
        gid = game_row["id"]
        td_date = f'<td style="text-align:left;padding:10px 12px;font-weight:600;white-space:nowrap;color:#ccc">{game_row["Date"]}</td>'
        td_game = f'<td style="text-align:left;padding:10px 12px;font-weight:600;white-space:nowrap;color:#ccc">{game_row["Game"]}</td>'
        market_tds = "".join(
            render_cell(*cell_data[c].get(gid, ("","","")))
            for c in col_order
        )
        rows.append(f"<tr>{td_date}{td_game}{market_tds}</tr>")

    tbody = "<tbody>" + "".join(rows) + "</tbody>"

    return f"""
    <style>
      .odds-table {{
        border-collapse: collapse;
        width: 100%;
        font-size: 13px;
        font-family: monospace;
      }}
      .odds-table th {{
        background: #1a1d2e;
        color: #9aa0b4;
        border-bottom: 2px solid #2e3250;
        font-size: 12px;
        letter-spacing: 0.04em;
      }}
      .odds-table td {{
        border-bottom: 1px solid #23263a;
        padding: 10px 8px;
      }}
      .odds-table tbody tr:hover td {{
        background: #1e2130;
      }}
    </style>
    <table class="odds-table">{header}{tbody}</table>
    """


# ---- UI ----
st.title("MLB Overnight Historical Odds")

raw = load_data()
players = get_players(raw)

selected = st.selectbox(
    "Search player",
    options=[""] + players,
    index=0,
    placeholder="Type to search...",
)

if selected:
    games, col_order, cell_data = build_player_data(raw, selected)
    if games is None or games.empty:
        st.warning(f"No data found for {selected}.")
    else:
        st.markdown(f"### {selected}")
        html = build_html_table(games, col_order, cell_data)
        st.markdown(html, unsafe_allow_html=True)
