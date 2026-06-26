"""
app.py
Mark's World Cup Predicting Machine

Combines:
  - Elo ratings seeded from pre-tournament team strength
  - Adjustments from actual World Cup 2026 results so far
  - Monte Carlo simulation of the remaining knockout bracket

Data sources (in priority order):
  1. Shared Google Sheet (if configured in secrets.toml) - lets you and
     your coworkers update scores from anywhere.
  2. Local CSV files in data/ - used automatically if no Sheet is set up.

Match results are entered manually (by you or your coworkers, either
directly in the Google Sheet or via the in-app form below) since the
free tier of live sports score APIs doesn't cover the current World Cup
season.
"""

import base64
import os
import streamlit as st
import pandas as pd

from elo_engine import build_current_ratings
from simulation import monte_carlo_bracket, KNOCKOUT_ROUNDS_ORDER
from sheets_io import load_sheet_tab, append_result_row, using_google_sheets

st.set_page_config(
    page_title="Mark's World Cup Predicting Machine",
    page_icon="\U0001F3C6",
    layout="wide",
)


def _load_logo_b64():
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "care-fusion-logo.svg")
    try:
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except FileNotFoundError:
        return None


_logo_b64 = _load_logo_b64()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
header_col1, header_col2 = st.columns([4, 1])
with header_col1:
    st.title("\U0001F3C6 Mark's World Cup Predicting Machine")
    st.caption(
        "*If you're not passionate about soccer, let statistics decide for you.*"
    )
with header_col2:
    if _logo_b64:
        st.markdown(
            f"""
            <div style="display:flex; justify-content:flex-end; align-items:center; height:100%; padding-top:18px;">
                <img src="data:image/svg+xml;base64,{_logo_b64}" style="max-width:180px; width:100%;">
            </div>
            """,
            unsafe_allow_html=True,
        )

st.write(
    "This tool uses real World Cup 2026 results to estimate each team's "
    "strength, then runs thousands of simulated tournaments to see who "
    "comes out on top most often. No soccer knowledge required."
)
st.info(
    "\U0001F3C5 **Filling out your bracket for the 6/29 Bracket Challenge?** "
    "Scroll down to the simulation section below to see which teams are "
    "favored to go all the way - a handy cheat sheet either way!"
)

# ---------------------------------------------------------------------------
# Sidebar: beginner-friendly explanations + settings
# ---------------------------------------------------------------------------
with st.sidebar:
    if _logo_b64:
        st.markdown(
            f"""
            <div style="text-align:center; padding-bottom:8px;">
                <img src="data:image/svg+xml;base64,{_logo_b64}" style="max-width:160px; width:80%;">
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.divider()

    st.header("\u2139\ufe0f How This Works")
    st.markdown(
        """
**What's an Elo rating?**

Every team gets a number (called an Elo rating) that represents how
strong they are. Beating a tough opponent raises your number a lot;
beating a weak opponent barely moves it. Losing does the opposite.
It's the same rating system used in chess, just applied to soccer.

**How does this predict a winner?**

Once every team has a rating, the app simulates the rest of the
tournament thousands of times. In each simulated run, the better-rated
team is more likely to win each match, but upsets can still happen
(just like in real life). After running it 10,000+ times, we count how
often each team ends up as champion - that's their championship odds.
        """
    )

    st.divider()
    st.header("\u2699\ufe0f Settings")

    n_sims = st.slider(
        "How many tournaments to simulate",
        1000, 50000, 10000, step=1000,
        help=(
            "The app 'replays' the rest of the World Cup this many times, "
            "with a bit of randomness each time (so upsets can happen). "
            "More replays = more reliable odds, but takes a little longer "
            "to calculate. 10,000 is a good default."
        ),
    )
    k_factor = st.slider(
        "How much each result affects the ratings",
        10, 60, 30,
        help=(
            "After a team wins or loses, this controls how much their "
            "strength rating changes. A higher number means recent results "
            "matter more (a single big win or loss swings things harder). "
            "A lower number means ratings stay steadier over time. 30 is a "
            "balanced default."
        ),
    )

    st.divider()

    if using_google_sheets():
        st.success("Connected to the shared team Google Sheet")
    else:
        st.info("No Google Sheet connected yet - using local sample data")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
teams_df = load_sheet_tab("teams")
results_df = load_sheet_tab("results")
bracket_df = load_sheet_tab("bracket")

teams_df["base_elo"] = pd.to_numeric(teams_df["base_elo"], errors="coerce")
results_df["score_a"] = pd.to_numeric(results_df["score_a"], errors="coerce")
results_df["score_b"] = pd.to_numeric(results_df["score_b"], errors="coerce")

ratings = build_current_ratings(teams_df, results_df, k=k_factor)

# Catch silent data-entry typos: if a team name in results doesn't exactly
# match a team in the teams list, elo_engine quietly skips that match
# (and that match's data effectively vanishes). Surface it loudly instead.
known_teams = set(teams_df["team"])
unrecognized = sorted(
    set(results_df["team_a"]).union(results_df["team_b"]) - known_teams - {"", "nan"}
)
if unrecognized:
    st.error(
        "\u26A0\ufe0f **Heads up Mark/Kiran/Phillip:** these team names in "
        "the results tab don't match the teams list exactly (likely a typo "
        "or extra space) and are being skipped from the ratings: "
        + ", ".join(f"`{t}`" for t in unrecognized)
    )

# ---------------------------------------------------------------------------
# Current ratings + results tables
# ---------------------------------------------------------------------------
st.divider()
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("\U0001F4CA Current Team Strength Rankings")
    st.caption("Higher number = stronger team, based on results so far.")
    ratings_df = (
        pd.DataFrame(list(ratings.items()), columns=["Team", "Strength Rating"])
        .sort_values("Strength Rating", ascending=False)
        .reset_index(drop=True)
    )
    ratings_df.index = ratings_df.index + 1
    ratings_df.index.name = "Rank"
    ratings_df["Strength Rating"] = ratings_df["Strength Rating"].round(1)
    st.dataframe(ratings_df, use_container_width=True, height=420)

with col2:
    st.subheader("\u26BD Match Results So Far")
    sort_col1, sort_col2 = st.columns([2, 1])
    with sort_col1:
        sort_by = st.selectbox(
            "Sort by", ["Date", "Team A", "Team B", "Stage"], index=0, key="sort_by"
        )
    with sort_col2:
        sort_dir = st.selectbox("Order", ["Newest first", "Oldest first"], index=0, key="sort_dir")

    display_results = results_df.copy()
    sort_map = {"Date": "date", "Team A": "team_a", "Team B": "team_b", "Stage": "stage"}
    sort_col = sort_map[sort_by]

    if sort_col == "date" and "date" in display_results.columns:
        display_results["_sort_key"] = pd.to_datetime(display_results["date"], errors="coerce")
    else:
        display_results["_sort_key"] = display_results[sort_col]

    display_results = display_results.sort_values(
        "_sort_key", ascending=(sort_dir == "Oldest first")
    ).drop(columns="_sort_key")

    display_results["stage"] = display_results["stage"].str.title()
    display_results = display_results.rename(columns={
        "team_a": "Team A",
        "team_b": "Team B",
        "score_a": "Score A",
        "score_b": "Score B",
        "stage": "Stage",
        "date": "Date",
    })
    display_results = display_results.reset_index(drop=True)
    display_results.index = display_results.index + 1

    st.dataframe(display_results, use_container_width=True, height=420)
    st.caption(f"{len(results_df)} matches recorded so far.")

# ---------------------------------------------------------------------------
# Add a new result
# ---------------------------------------------------------------------------
st.divider()
st.subheader("\u270F\ufe0f Add a New Match Result")
st.warning(
    "\U0001F512 **Reserved for Mark, Kiran, and Phillip.** Match results are "
    "kept up to date by the three of us - no need for anyone else to enter "
    "anything here."
)

with st.expander("Open form (Mark / Kiran / Phillip only)"):
    st.caption(
        "Submitting this form saves the result directly to the shared "
        "Google Sheet, so the ratings and predictions update for everyone "
        "automatically."
    )

    with st.form("add_result_form", clear_on_submit=True):
        c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 1, 1, 1, 1.3])
        team_options = sorted(teams_df["team"].tolist())
        with c1:
            team_a = st.selectbox("Team A", team_options)
        with c2:
            team_b = st.selectbox("Team B", team_options, index=1)
        with c3:
            score_a = st.number_input("Score A", min_value=0, max_value=20, step=1)
        with c4:
            score_b = st.number_input("Score B", min_value=0, max_value=20, step=1)
        with c5:
            stage = st.selectbox("Stage", ["Group", "Knockout"])
        with c6:
            match_date = st.date_input("Date")
        submitted = st.form_submit_button("Save Result")

        if submitted:
            if team_a == team_b:
                st.error("Team A and Team B must be different.")
            else:
                try:
                    append_result_row(
                        team_a, team_b, int(score_a), int(score_b), stage.lower(), match_date
                    )
                    st.success("Saved! Refresh the page to see updated predictions.")
                except RuntimeError as e:
                    st.error(str(e))

    st.divider()
    st.markdown("**\U0001F4CB After every knockout match, do BOTH of these:**")
    st.markdown(
        """
1. **Log the score** using the form above, same as any group stage match.
2. **Update the `bracket` tab** in the Google Sheet: find the slot that
   match feeds into (it'll say something like `Winner M3`) and replace it
   with the actual winning team's name.

**Why both steps matter:** Step 1 keeps the strength ratings accurate.
Step 2 tells the simulation "this game is already decided, stop guessing
it" - without it, the app will keep simulating a match that already
happened, which throws off everyone's odds for later rounds.

**Also check for `TBD` slots:** once the 8 third-place teams are
finalized (and again before each new round), swap any `TBD` in the
bracket tab for the real team name as soon as it's known.
        """
    )
    st.markdown(
        """
**Example:** South Africa beats Canada 2-1 in the Round of 32 (match M1).
- Log it: `South Africa, Canada, 2, 1, Knockout`
- M1's winner feeds into match **M17** in the Round of 16. In the
  bracket tab, find the **M17** row - column `team_a` currently says
  `Winner M1`. Type over it with `South Africa`. That's the only cell
  that needs to change.
        """
    )

# ---------------------------------------------------------------------------
# Bracket simulation
# ---------------------------------------------------------------------------
st.divider()
st.subheader("\U0001F3C6 Who Will Win the World Cup?")
st.caption(
    "This runs the simulation described in the sidebar and shows how often "
    "each team comes out on top."
)
st.caption(
    "\u2139\ufe0f A few Round of 32 matchups still show 'TBD' since the "
    "8 best third-place teams haven't been finalized yet. Teams stuck "
    "behind a TBD slot will show 0% for now - that'll update automatically "
    "once their opponent is confirmed."
)

required_cols = {"round", "match_id", "team_a", "team_b"}
if not required_cols.issubset(bracket_df.columns):
    st.info(
        "The knockout bracket matchups aren't set yet - they'll be added "
        "once the Round of 32 is confirmed. Check back soon!"
    )
else:
    with st.expander("View the current knockout bracket matchups"):
        st.caption(
            "Anything labeled 'Winner M#' means that slot depends on the "
            "outcome of an earlier match, and will fill in automatically "
            "as real results come in."
        )
        bracket_display = bracket_df.rename(columns={
            "round": "Round", "match_id": "Match", "team_a": "Team A", "team_b": "Team B"
        })
        st.dataframe(bracket_display, use_container_width=True)

    if st.button("\U0001F3B2 Run the Simulation", type="primary"):
        with st.spinner(f"Simulating the rest of the World Cup {n_sims:,} times..."):
            sim_results = monte_carlo_bracket(bracket_df, ratings, n_sims=n_sims)

        st.subheader("Championship Odds")
        st.caption(
            "Out of every simulated tournament we ran, this is the "
            "percentage of the time each team ended up winning it all."
        )
        display_df = sim_results.copy()
        for c in display_df.columns:
            if c != "team":
                display_df[c] = display_df[c].round(1)

        rename_map = {"team": "Team", "champion_pct": "Champion %"}
        for rnd in KNOCKOUT_ROUNDS_ORDER:
            rename_map[f"reached_{rnd.replace(' ', '_')}_pct"] = f"Reached {rnd} %"
        display_df = display_df.rename(columns=rename_map)
        display_df = display_df.reset_index(drop=True)
        display_df.index = display_df.index + 1

        st.dataframe(display_df, use_container_width=True, height=400)

        st.caption("Top 10 teams by championship odds:")
        st.bar_chart(sim_results.set_index("team")["champion_pct"].head(10))

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "**How the math works:** Each team starts with a strength rating based "
    "on their pre-tournament form, then that rating gets adjusted after "
    "every real World Cup 2026 match (bigger wins move it more). The rest "
    "of the bracket gets simulated thousands of times using those ratings, "
    "and we tally how often each team wins overall. This is the same "
    "general approach used by professional sports forecasters."
)
