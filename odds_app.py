import math
import streamlit as st
import pandas as pd
import duckdb

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

PITCHER_MARKETS = {
    "pitcher_outs", "pitcher_strikeouts", "pitcher_walks",
    "pitcher_hits_allowed", "pitcher_earned_runs",
}
BATTER_MARKETS = {m for m, _, _ in MARKET_DEFS if m.startswith("batter_")}


# ── helpers ──────────────────────────────────────────────────────────────────

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
    pt = fmt_point(point)        if not pd.isna(point)      else ""
    ov = fmt_american(over_odds)  if not pd.isna(over_odds)  else ""
    un = fmt_american(under_odds) if not pd.isna(under_odds) else ""
    return pt, ov, un


def cell_alt(point, over_odds, show_point=False):
    ov = fmt_american(over_odds) if not pd.isna(over_odds) else ""
    pt = f"{math.ceil(float(point))}+" if (show_point and not pd.isna(point)) else ""
    return pt, ov, ""


def abbrev_name(full):
    parts = full.strip().split()
    return f"{parts[0][0]}. {' '.join(parts[1:])}" if len(parts) >= 2 else full


# ── data loading ─────────────────────────────────────────────────────────────

CSV_PATH = "odds_filtered.csv"
NEEDED_COLS = "id, commence_time, home_team, away_team, market, description, side, price, point"

@st.cache_resource
def get_con():
    return duckdb.connect(database=":memory:")


@st.cache_data(ttl=300)
def get_players():
    con = get_con()
    rows = con.execute(
        f"SELECT DISTINCT description FROM read_csv_auto('{CSV_PATH}') WHERE description IS NOT NULL ORDER BY description"
    ).fetchall()
    return [r[0] for r in rows]


@st.cache_data(ttl=300)
def build_pitcher_map():
    con = get_con()
    markets = ", ".join(f"'{m}'" for m in PITCHER_MARKETS)
    df = con.execute(
        f"SELECT id, description FROM read_csv_auto('{CSV_PATH}') WHERE market IN ({markets})"
    ).df()
    result = {}
    for gid, grp in df.groupby("id"):
        names = grp["description"].unique().tolist()
        result[gid] = " / ".join(abbrev_name(n) for n in names)
    return result


@st.cache_data(ttl=300)
def build_player_data(player):
    con = get_con()
    pf = con.execute(
        f"SELECT {NEEDED_COLS} FROM read_csv_auto('{CSV_PATH}') WHERE description = ?",
        [player]
    ).df()
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

    merged["Date"]      = pd.to_datetime(merged["commence_time"]).dt.strftime('%m-%d')
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

        if any(any(v) for v in col_cells.values()):
            col_order.append(actual_col)
            cell_data[actual_col] = col_cells

    return games, col_order, cell_data


# ── rendering ─────────────────────────────────────────────────────────────────

def render_cell(pt, ov, un):
    if not pt and not ov and not un:
        return "<td></td>"

    def odds_color(val):
        return "color:#ef5350" if val.startswith("+") else "color:#4caf50"

    if not pt and not un:
        color = odds_color(ov)
        return (
            f'<td style="text-align:center;vertical-align:middle;">'
            f'<span style="font-size:15px;font-weight:600;{color}">{ov}</span>'
            f'</td>'
        )

    pt_html = f'<span style="font-size:20px;font-weight:700;color:#e0e0e0;line-height:1">{pt}</span>'

    if pt and ov and not un:
        ov_html = f'<span style="font-size:13px;font-weight:600;{odds_color(ov)};line-height:1">{ov}</span>'
        return (
            f'<td style="text-align:center;vertical-align:middle;white-space:nowrap;">'
            f'<span style="display:inline-flex;align-items:center;justify-content:center;gap:5px">'
            f'{pt_html}{ov_html}'
            f'</span>'
            f'</td>'
        )

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


TABLE_CSS = """
<style>
  .odds-table {
    border-collapse: collapse;
    width: 100%;
    font-size: 13px;
    font-family: monospace;
  }
  .odds-table th {
    background: #1a1d2e;
    color: #9aa0b4;
    border-bottom: 2px solid #2e3250;
    font-size: 12px;
    letter-spacing: 0.04em;
    position: sticky;
    top: 0;
    z-index: 1;
  }
  .odds-table td {
    border-bottom: 1px solid #23263a;
    padding: 10px 8px;
  }
  .odds-table tbody tr:hover td {
    background: #1e2130;
  }
</style>
"""


def build_html_table(games, col_order, cell_data, pitcher_map=None):
    col_labels = {c: c.replace("_2", "") for c in col_order}

    th_date     = '<th style="text-align:left;padding:8px 12px;white-space:nowrap;">Date</th>'
    th_game     = '<th style="text-align:left;padding:8px 12px;white-space:nowrap;">Game</th>'
    th_pitchers = '<th style="text-align:left;padding:8px 12px;white-space:nowrap;">Pitchers</th>' if pitcher_map is not None else ""
    market_ths  = "".join(
        f'<th style="text-align:center;padding:8px 10px;white-space:nowrap;">{col_labels[c]}</th>'
        for c in col_order
    )
    header = f"<thead><tr>{th_date}{th_game}{th_pitchers}{market_ths}</tr></thead>"

    rows = []
    for _, game_row in games.iterrows():
        gid     = game_row["id"]
        td_date = f'<td style="text-align:left;padding:10px 12px;font-weight:600;white-space:nowrap;color:#ccc">{game_row["Date"]}</td>'
        td_game = f'<td style="text-align:left;padding:10px 12px;font-weight:600;white-space:nowrap;color:#ccc">{game_row["Game"]}</td>'
        if pitcher_map is not None:
            pitchers_html = pitcher_map.get(gid, "").replace(" / ", "<br>")
            td_pitchers = f'<td style="text-align:left;padding:10px 12px;color:#aaa;font-size:12px;white-space:nowrap;line-height:1.6">{pitchers_html}</td>'
        else:
            td_pitchers = ""
        market_tds = "".join(render_cell(*cell_data[c].get(gid, ("","",""))) for c in col_order)
        rows.append(f"<tr>{td_date}{td_game}{td_pitchers}{market_tds}</tr>")

    tbody = "<tbody>" + "".join(rows) + "</tbody>"
    return f'{TABLE_CSS}<div style="overflow-y:auto;max-height:75vh;overflow-x:auto;"><table class="odds-table">{header}{tbody}</table></div>'


BATTER_COL_NAMES = {MARKET_LOOKUP[m][0] for m in BATTER_MARKETS if m in MARKET_LOOKUP}


def render_player_section(player, pitcher_map_cache, slot):
    games, col_order, cell_data = build_player_data(player)
    if games is None or games.empty:
        slot.warning(f"No data found for {player}.")
        return
    is_batter = any(c.replace("_2", "") in BATTER_COL_NAMES for c in col_order)
    pm        = pitcher_map_cache if is_batter else None
    slot.markdown(build_html_table(games, col_order, cell_data, pm), unsafe_allow_html=True)


# ── session state helpers ─────────────────────────────────────────────────────

def _init_key(key, default):
    if key not in st.session_state:
        st.session_state[key] = default


# ── UI ────────────────────────────────────────────────────────────────────────

st.title("MLB Overnight Historical Odds")

players     = get_players()
pitcher_map = build_pitcher_map()

tab_player, tab_lineup = st.tabs(["Player View", "Lineup View"])


# ════════════════════════════════════════════════════════════
#  PLAYER VIEW
# ════════════════════════════════════════════════════════════
with tab_player:
    _init_key("player_key", 0)

    col_search, col_clear = st.columns([6, 1])
    with col_search:
        selected = st.selectbox(
            "Search player",
            options=[""] + players,
            index=0,
            placeholder="Type to search...",
            key=f"player_{st.session_state.player_key}",
        )
    with col_clear:
        st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
        if st.button("Clear", key="pv_clear", use_container_width=True):
            st.session_state.player_key += 1
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    if selected:
        render_player_section(selected, pitcher_map, st)


# ════════════════════════════════════════════════════════════
#  LINEUP VIEW
# ════════════════════════════════════════════════════════════
with tab_lineup:
    NUM_SLOTS = 9

    for i in range(NUM_SLOTS):
        _init_key(f"lv_player_{i}", "")
        _init_key(f"lv_key_{i}", 0)
        _init_key(f"lv_expanded_{i}", False)
    _init_key("lv_sp_player", "")
    _init_key("lv_sp_key", 0)
    _init_key("lv_sp_expanded", False)

    # Maximize / Minimize all checkbox
    all_expanded = st.checkbox("Maximize all", key="lv_maximize")
    if all_expanded:
        st.session_state["lv_sp_expanded"] = True
        for i in range(NUM_SLOTS):
            st.session_state[f"lv_expanded_{i}"] = True
    else:
        if "lv_maximize_prev" in st.session_state and st.session_state["lv_maximize_prev"]:
            st.session_state["lv_sp_expanded"] = False
            for i in range(NUM_SLOTS):
                st.session_state[f"lv_expanded_{i}"] = False
    st.session_state["lv_maximize_prev"] = all_expanded

    # ── SP slot ──────────────────────────────────────────────
    sp_val = st.session_state["lv_sp_player"]
    col_arrow, col_search, col_clear = st.columns([1, 8, 1])

    with col_arrow:
        sp_expanded = st.session_state["lv_sp_expanded"]
        sp_arrow    = "▼ SP" if sp_expanded else "▶ SP"
        if st.button(sp_arrow, key="lv_sp_arrow", use_container_width=True):
            st.session_state["lv_sp_expanded"] = not sp_expanded
            st.rerun()

    with col_search:
        sp_chosen = st.selectbox(
            "SP",
            options=[""] + players,
            index=(players.index(sp_val) + 1) if sp_val in players else 0,
            placeholder="Type to search...",
            label_visibility="collapsed",
            key=f"lv_sp_sel_{st.session_state['lv_sp_key']}",
        )
        if sp_chosen != sp_val:
            st.session_state["lv_sp_player"] = sp_chosen
            st.rerun()

    with col_clear:
        if st.button("✕", key="lv_sp_clear", use_container_width=True):
            st.session_state["lv_sp_player"]   = ""
            st.session_state["lv_sp_expanded"]  = False
            st.session_state["lv_sp_key"]      += 1
            st.rerun()

    if st.session_state["lv_sp_expanded"] and st.session_state["lv_sp_player"]:
        render_player_section(st.session_state["lv_sp_player"], pitcher_map, st)
        st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)

    # ── Batter slots 1-9 ─────────────────────────────────────
    for i in range(NUM_SLOTS):
        player_val = st.session_state[f"lv_player_{i}"]

        col_arrow, col_search, col_clear = st.columns([1, 8, 1])

        with col_arrow:
            expanded = st.session_state[f"lv_expanded_{i}"]
            arrow    = f"▼ {i+1}." if expanded else f"▶ {i+1}."
            if st.button(arrow, key=f"lv_arrow_{i}", use_container_width=True):
                st.session_state[f"lv_expanded_{i}"] = not expanded
                st.rerun()

        with col_search:
            chosen = st.selectbox(
                f"Player {i+1}",
                options=[""] + players,
                index=(players.index(player_val) + 1) if player_val in players else 0,
                placeholder="Type to search...",
                label_visibility="collapsed",
                key=f"lv_sel_{i}_{st.session_state[f'lv_key_{i}']}",
            )
            if chosen != player_val:
                st.session_state[f"lv_player_{i}"] = chosen
                st.rerun()

        with col_clear:
            if st.button("✕", key=f"lv_clear_{i}", use_container_width=True):
                st.session_state[f"lv_player_{i}"]   = ""
                st.session_state[f"lv_expanded_{i}"]  = False
                st.session_state[f"lv_key_{i}"]      += 1
                st.rerun()

        if st.session_state[f"lv_expanded_{i}"] and st.session_state[f"lv_player_{i}"]:
            render_player_section(st.session_state[f"lv_player_{i}"], pitcher_map, st)
            st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)
