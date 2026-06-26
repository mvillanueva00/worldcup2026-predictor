"""
simulation.py
Monte Carlo simulator for the World Cup 2026 knockout bracket.

The bracket is read from a simple list of matchups per round. A matchup
where both teams are known (e.g. "Mexico" vs "Poland") gets simulated
directly. A matchup that depends on a previous round (e.g. "Winner of
Match 3") is resolved automatically as the simulation progresses through
rounds in order.
"""

import random
from collections import defaultdict
import pandas as pd
from elo_engine import expected_score


KNOCKOUT_ROUNDS_ORDER = [
    "Round of 32",
    "Round of 16",
    "Quarterfinal",
    "Semifinal",
    "Final",
]


def resolve_slot(team_field, resolved: dict):
    """
    Resolves a single bracket cell to an actual team name.
    - "Winner M#" -> looks up M#'s resolved winner (None if not decided yet)
    - "TBD" -> None (not yet known)
    - anything else -> returned as-is (a real team name)
    """
    if isinstance(team_field, str) and team_field.startswith("Winner "):
        ref_id = team_field.replace("Winner ", "").strip()
        return resolved.get(ref_id)
    if isinstance(team_field, str) and team_field.strip().upper() == "TBD":
        return None
    return team_field


def sorted_bracket(bracket_df: pd.DataFrame) -> pd.DataFrame:
    """Returns the bracket sorted into proper round order (R32 -> Final)."""
    df = bracket_df.copy()
    df["_order"] = df["round"].apply(
        lambda r: KNOCKOUT_ROUNDS_ORDER.index(r) if r in KNOCKOUT_ROUNDS_ORDER else 99
    )
    return df.sort_values(["_order", "match_id"]).drop(columns="_order")


def simulate_single_match(team_a, team_b, ratings, home_advantage=0):
    """
    Simulate one knockout match (no draws allowed - extra time/penalties
    eventually produce a winner). Returns the winning team name.
    """
    ra = ratings.get(team_a, 1500) + home_advantage
    rb = ratings.get(team_b, 1500)
    p_a = expected_score(ra, rb)
    return team_a if random.random() < p_a else team_b


def run_bracket_once(bracket_df: pd.DataFrame, ratings: dict) -> dict:
    """
    bracket_df columns: round, match_id, team_a, team_b
    team_a/team_b may be an actual team name, or a placeholder like
    "Winner M1" referencing another match_id's winner.
    Returns dict: match_id -> winning team name, plus 'CHAMPION' key.
    """
    winners = {}
    df = sorted_bracket(bracket_df)

    for _, row in df.iterrows():
        team_a = resolve_slot(row["team_a"], winners)
        team_b = resolve_slot(row["team_b"], winners)
        if team_a is None or team_b is None:
            # Dependency not yet resolved (shouldn't happen if sorted right)
            continue
        winner = simulate_single_match(team_a, team_b, ratings)
        winners[row["match_id"]] = winner

    if len(df) > 0:
        final_match_id = df.iloc[-1]["match_id"]
        winners["CHAMPION"] = winners.get(final_match_id)

    return winners


def monte_carlo_bracket(bracket_df: pd.DataFrame, ratings: dict, n_sims: int = 10000) -> pd.DataFrame:
    """
    Runs the bracket simulation n_sims times and tallies how often each
    team reaches / wins each round.
    Returns a DataFrame: team, champion_pct, final_pct, semifinal_pct, ... etc.
    """
    round_counts = defaultdict(lambda: defaultdict(int))  # team -> round -> count
    champion_counts = defaultdict(int)

    for _ in range(n_sims):
        winners = run_bracket_once(bracket_df, ratings)
        for match_id, winner in winners.items():
            if winner is None or match_id == "CHAMPION":
                continue
        if winners.get("CHAMPION"):
            champion_counts[winners["CHAMPION"]] += 1

        # Track how far each team got: any team appearing as a winner of a
        # round R reached at least round R+1
        df = bracket_df.copy()
        for _, row in df.iterrows():
            match_id = row["match_id"]
            w = winners.get(match_id)
            if w:
                round_counts[w][row["round"]] += 1

    teams = sorted(set(bracket_df["team_a"]).union(bracket_df["team_b"]) - {None})
    teams = [
        t for t in teams
        if not (isinstance(t, str) and (t.startswith("Winner ") or t.strip().upper() == "TBD"))
    ]

    rows = []
    for t in teams:
        row = {"team": t}
        row["champion_pct"] = 100 * champion_counts.get(t, 0) / n_sims
        for rnd in KNOCKOUT_ROUNDS_ORDER:
            row[f"reached_{rnd.replace(' ', '_')}_pct"] = 100 * round_counts[t].get(rnd, 0) / n_sims
        rows.append(row)

    result = pd.DataFrame(rows).sort_values("champion_pct", ascending=False).reset_index(drop=True)
    return result
