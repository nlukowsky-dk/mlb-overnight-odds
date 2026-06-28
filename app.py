import streamlit as st
import requests
import pandas as pd
from datetime import date, datetime, timezone, timedelta
from scraper import get_cached

st.set_page_config(page_title="MLB Bullpen Depth", layout="wide")

st.markdown("""
<style>
  .team-name { font-size: 20px; font-weight: 700; }
  .record    { font-size: 16px; color: #ccc; margin-top: 2px; }
  .pitcher   { font-size: 15px; color: #bbb; font-style: italic; margin-top: 2px; }
  .gametime  { font-size: 15px; color: #4da6ff; font-weight: 600; }
  .status    { font-size: 13px; color: #aaa; }
</style>
""", unsafe_allow_html=True)

PDT = timezone(timedelta(hours=-7))

# Team primary colors for player cell highlighting
TEAM_COLORS = {
    "ATH": "#003831", "BAL": "#DF4601", "BOS": "#BD3039", "CHW": "#27251F",
    "CLE": "#00385D", "DET": "#0C2340", "HOU": "#002D62", "KCR": "#004687",
    "LAA": "#BA0021", "MIN": "#002B5C", "NYY": "#003087", "SEA": "#0C2C56",
    "TBR": "#092C5C", "TEX": "#003278", "TOR": "#134A8E", "ARI": "#A71930",
    "ATL": "#CE1141", "CHC": "#0E3386", "CIN": "#C6011F", "COL": "#33006F",
    "LAD": "#005A9C", "MIA": "#00A3E0", "MIL": "#12284B", "NYM": "#002D72",
    "PHI": "#E81828", "PIT": "#27251F", "SDP": "#2F241D", "SFG": "#FD5A1E",
    "STL": "#C41E3A", "WSN": "#AB0003",
}

# MLB Stats API abbreviation -> FanGraphs abbreviation
MLB_TO_FG = {
    "OAK": "ATH", "CWS": "CHW", "KC": "KCR",
    "TB":  "TBR", "SD":  "SDP", "SF": "SFG", "WSH": "WSN",
}


def to_pst(utc_str: str) -> str:
    if not utc_str:
        return ""
    try:
        dt_utc = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        dt_pst = dt_utc.astimezone(PDT)
        hour   = dt_pst.hour % 12 or 12
        minute = dt_pst.strftime("%M")
        ampm   = "AM" if dt_pst.hour < 12 else "PM"
        return f"{hour}:{minute} {ampm} PT"
    except Exception:
        return ""


@st.cache_data(ttl=300)
def get_today_games():
    today = date.today().strftime("%Y-%m-%d")
    url   = (
        f"https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&date={today}&hydrate=team,probablePitcher,linescore"
    )
    try:
        data = requests.get(url, timeout=10).json()
    except Exception:
        return []

    if not data.get("dates"):
        return []

    games = []
    for g in data["dates"][0]["games"]:
        away = g["teams"]["away"]
        home = g["teams"]["home"]

        def record(side):
            lr = side.get("leagueRecord", {})
            w, l = lr.get("wins", ""), lr.get("losses", "")
            return f"{w}-{l}" if w != "" else ""

        def pitcher(side):
            return side.get("probablePitcher", {}).get("fullName", "TBD")

        away_id = away["team"]["id"]
        home_id = home["team"]["id"]

        games.append({
            "game_pk":      g["gamePk"],
            "away_abbr":    away["team"]["abbreviation"],
            "home_abbr":    home["team"]["abbreviation"],
            "away_name":    away["team"]["name"],
            "home_name":    home["team"]["name"],
            "away_record":  record(away),
            "home_record":  record(home),
            "away_pitcher": pitcher(away),
            "home_pitcher": pitcher(home),
            "away_logo":    f"https://www.mlbstatic.com/team-logos/{away_id}.svg",
            "home_logo":    f"https://www.mlbstatic.com/team-logos/{home_id}.svg",
            "status":       g["status"]["detailedState"],
            "game_time":    to_pst(g.get("gameDate", "")),
            "label":        f"{away['team']['name']} @ {home['team']['name']}",
        })
    return games


def style_bullpen(df: pd.DataFrame, abbr: str, date_cols: list):
    fg_abbr    = MLB_TO_FG.get(abbr, abbr)
    team_color = TEAM_COLORS.get(fg_abbr, "#1e2130")

    df = df.fillna("").replace("None", "")
    if "IP (L6)" in df.columns:
        def fmt_ip(v):
            try:
                return f"{float(v):.1f}"
            except (ValueError, TypeError):
                return v
        df["IP (L6)"] = df["IP (L6)"].apply(fmt_ip)

    # Single row-wise apply so nothing overrides anything else
    def style_row(row):
        styles = []
        for col in row.index:
            val = str(row[col]).strip()
            if col == "Player":
                styles.append(f"background-color: {team_color}; color: white; font-weight: 600")
            elif col in date_cols:
                if val == "AAA":
                    styles.append("background-color: #d3d3d3; color: red")
                elif val == "IL":
                    styles.append("background-color: #FFD700; color: red")
                else:
                    styles.append("background-color: #add8e6; color: black")
            else:
                styles.append("")
        return styles

    styler = (
        df.style
        .apply(style_row, axis=1)
        .set_properties(**{"text-align": "left"})
        .hide(axis="index")
    )

    # Header highlight for date columns — apply_index generates inline styles on <th> elements
    try:
        styler = styler.apply_index(
            lambda s: [
                "background-color: #d3d3d3; color: black; font-weight: bold" if v in date_cols else ""
                for v in s
            ],
            axis="columns"
        )
    except Exception:
        pass

    return styler


# ---- Session state ----
if "selected_game" not in st.session_state:
    st.session_state.selected_game = None


# ---- Game detail view ----
if st.session_state.selected_game is not None:
    game = st.session_state.selected_game

    if st.button("← Back to Today's Games"):
        st.session_state.selected_game = None
        st.rerun()

    c1, c2, mid, c3, c4 = st.columns([1, 5, 1, 5, 1])
    with c1:
        st.image(game["away_logo"], width=80)
    with c2:
        st.markdown(f"<div class='team-name'>{game['away_name']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='record'>{game['away_record']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='pitcher'>SP: {game['away_pitcher']}</div>", unsafe_allow_html=True)
    with mid:
        st.markdown("<div style='text-align:center; font-size:28px; padding-top:18px; color:#aaa'>@</div>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"<div class='team-name'>{game['home_name']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='record'>{game['home_record']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='pitcher'>SP: {game['home_pitcher']}</div>", unsafe_allow_html=True)
    with c4:
        st.image(game["home_logo"], width=80)

    st.markdown(
        f"<div style='margin-top:8px'>"
        f"<span class='gametime'>{game['game_time']}</span>"
        f"<span class='status'>  &nbsp;{game['status']}</span>"
        f"</div>",
        unsafe_allow_html=True
    )
    st.divider()

    away_col, home_col = st.columns(2)

    with away_col:
        st.subheader(f"{game['away_name']} Bullpen")
        with st.spinner("Loading..."):
            away_df, away_date_cols = get_cached(game["away_abbr"])
        if away_df.empty:
            st.warning(f"No closer depth data found for **{game['away_abbr']}**.")
        else:
            st.write(style_bullpen(away_df, game["away_abbr"], away_date_cols).to_html(), unsafe_allow_html=True)

    with home_col:
        st.subheader(f"{game['home_name']} Bullpen")
        with st.spinner("Loading..."):
            home_df, home_date_cols = get_cached(game["home_abbr"])
        if home_df.empty:
            st.warning(f"No closer depth data found for **{game['home_abbr']}**.")
        else:
            st.write(style_bullpen(home_df, game["home_abbr"], home_date_cols).to_html(), unsafe_allow_html=True)


# ---- Main game list ----
else:
    today_str = date.today().strftime("%B %d, %Y")
    st.title("MLB Bullpen Closer Depth Charts")
    st.subheader(f"Today's Games — {today_str}")
    st.markdown("---")

    games = get_today_games()

    if not games:
        st.info("No MLB games scheduled today.")
    else:
        for game in games:
            col_away_logo, col_away, col_vs, col_home, col_home_logo, col_btn = st.columns([1, 4, 1, 4, 1, 2])

            with col_away_logo:
                st.image(game["away_logo"], width=56)
            with col_away:
                st.markdown(f"<div class='team-name'>{game['away_name']}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='record'>{game['away_record']}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='pitcher'>SP: {game['away_pitcher']}</div>", unsafe_allow_html=True)
            with col_vs:
                st.markdown("<div style='text-align:center; padding-top:12px; font-size:20px; color:#aaa'>@</div>", unsafe_allow_html=True)
            with col_home:
                st.markdown(f"<div class='team-name'>{game['home_name']}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='record'>{game['home_record']}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='pitcher'>SP: {game['home_pitcher']}</div>", unsafe_allow_html=True)
            with col_home_logo:
                st.image(game["home_logo"], width=56)
            with col_btn:
                st.markdown(
                    f"<div class='gametime'>{game['game_time']}</div>"
                    f"<div class='status'>{game['status']}</div>",
                    unsafe_allow_html=True
                )
                if st.button("View Bullpens", key=f"game_{game['game_pk']}"):
                    st.session_state.selected_game = game
                    st.rerun()

            st.markdown("---")
