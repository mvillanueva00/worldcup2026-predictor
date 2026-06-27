"""
scoring.py
Scores everyone's bracket picks against REAL results as the tournament
progresses, for the Scoreboard tab.

How it works:
1. We figure out who actually won each bracket match (M1...M31) by
   cross-referencing the bracket structure against the knockout-stage
   rows in the results sheet (matching on which two teams played).
2. Each correct pick earns points, weighted by round - later rounds are
   worth more, since a correct Final pick is harder/more impressive than
   a correct Round of 32 pick.
3. A person's champion pick is marked "Eliminated" the moment that team
   loses any real match, "Still Alive" otherwise.
"""

import pandas as pd
from simulation import sorted_bracket, resolve_slot, KNOCKOUT_ROUNDS_ORDER

ROUND_POINTS = {
    "Round of 32": 1,
    "Round of 16": 2,
    "Quarterfinal": 4,
    "Semifinal": 8,
    "Final": 16,
}


def compute_actual_winners(bracket_df: pd.DataFrame, results_df: pd.DataFrame) -> dict:
    """
    Returns {match_id: actual_winning_team} for every bracket match that
    has genuinely been played in real life so far. Works by matching
    each bracket match's two teams (resolved round-by-round using only
    REAL winners, never picks or simulations) against the knockout-stage
    rows in the results sheet.
    """
    knockout = results_df[results_df["stage"].astype(str).str.lower() == "knockout"]

    # Map each real played matchup -> winner, e.g. {South Africa, Canada} -> South Africa
    lookup = {}
    for _, row in knockout.iterrows():
        a, b = row.get("team_a"), row.get("team_b")
        sa, sb = row.get("score_a"), row.get("score_b")
        if pd.isna(sa) or pd.isna(sb) or sa == sb or not a or not b:
            continue
        winner = a if sa > sb else b
        lookup[frozenset({a, b})] = winner

    actual_winners = {}
    for _, row in sorted_bracket(bracket_df).iterrows():
        team_a = resolve_slot(row["team_a"], actual_winners)
        team_b = resolve_slot(row["team_b"], actual_winners)
        if team_a is None or team_b is None:
            continue
        winner = lookup.get(frozenset({team_a, team_b}))
        if winner:
            actual_winners[row["match_id"]] = winner

    return actual_winners


def is_team_eliminated(team: str, bracket_df: pd.DataFrame, actual_winners: dict) -> bool:
    """True if `team` has actually lost a real match anywhere in the bracket so far."""
    if not team:
        return False
    for _, row in sorted_bracket(bracket_df).iterrows():
        team_a = resolve_slot(row["team_a"], actual_winners)
        team_b = resolve_slot(row["team_b"], actual_winners)
        winner = actual_winners.get(row["match_id"])
        if winner is None:
            continue
        if team in (team_a, team_b) and winner != team:
            return True
    return False


def score_participants(bracket_df: pd.DataFrame, results_df: pd.DataFrame, picks_df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns a leaderboard DataFrame: name, points, correct_picks,
    decided_picks, champion_pick, champion_status - sorted by points
    descending (most points first).
    """
    if picks_df.empty or "name" not in picks_df.columns:
        return pd.DataFrame(columns=[
            "name", "points", "correct_picks", "decided_picks", "champion_pick", "champion_status"
        ])

    actual_winners = compute_actual_winners(bracket_df, results_df)
    ordered = sorted_bracket(bracket_df)
    round_by_match = dict(zip(ordered["match_id"], ordered["round"]))

    rows = []
    for name, group in picks_df.groupby("name"):
        points = 0
        correct = 0
        decided = 0
        for _, prow in group.iterrows():
            match_id = prow["match_id"]
            pick = prow["pick"]
            real_winner = actual_winners.get(match_id)
            if real_winner is None:
                continue
            decided += 1
            if pick == real_winner:
                correct += 1
                points += ROUND_POINTS.get(round_by_match.get(match_id), 1)

        champ_row = group[group["match_id"] == "M31"]
        champion_pick = champ_row.iloc[0]["pick"] if not champ_row.empty else None
        if champion_pick and is_team_eliminated(champion_pick, bracket_df, actual_winners):
            champion_status = "\u274C Eliminated"
        elif champion_pick:
            champion_status = "\u2705 Still Alive"
        else:
            champion_status = "-"

        rows.append({
            "name": name,
            "points": points,
            "correct_picks": correct,
            "decided_picks": decided,
            "champion_pick": champion_pick,
            "champion_status": champion_status,
        })

    leaderboard = pd.DataFrame(rows).sort_values(
        ["points", "correct_picks"], ascending=[False, False]
    ).reset_index(drop=True)
    return leaderboard
