"""
elo_engine.py
Core Elo rating math for the World Cup 2026 predictor.

Based on the standard World Football Elo Ratings methodology
(see https://www.eloratings.net / Wikipedia: World Football Elo Ratings),
adapted slightly for simplicity.
"""

import math
import pandas as pd


def expected_score(rating_a: float, rating_b: float) -> float:
    """
    Probability that team A beats team B (draw counts as 0.5 for each side),
    using the standard Elo logistic formula with divisor 400.
    Assumes a neutral venue (World Cup knockout games are on neutral or
    semi-neutral grounds, host nations get a small bump applied separately).
    """
    diff = rating_b - rating_a
    return 1.0 / (1.0 + math.pow(10, diff / 400.0))


def goal_diff_multiplier(goal_diff: int) -> float:
    """
    Standard Elo football adjustment: bigger wins move ratings more,
    but with diminishing returns.
    """
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    elif gd == 2:
        return 1.5
    else:
        return (11 + gd) / 8.0


HOST_NATIONS = {"USA", "Mexico", "Canada"}
HOST_ADVANTAGE = 100  # standard Elo football home-advantage bump


def update_ratings(rating_a, rating_b, score_a, score_b, k=30, team_a=None, team_b=None):
    """
    Update two teams' ratings after a single match.
    score_a/score_b are goals scored. Returns (new_rating_a, new_rating_b).

    World Cup 2026 is co-hosted by the USA, Mexico, and Canada - the
    standard Elo football methodology gives a host nation a +100 boost
    to its EXPECTED score calculation only (not a permanent rating
    change), reflecting home-crowd advantage. This doesn't apply to a
    real "home" match for the other two co-hosts playing each other,
    since the tournament is genuinely neutral-ish for everyone except
    the specific host nation's own matches.
    """
    if score_a > score_b:
        result_a = 1.0
    elif score_a < score_b:
        result_a = 0.0
    else:
        result_a = 0.5

    adj_rating_a, adj_rating_b = rating_a, rating_b
    if team_a in HOST_NATIONS:
        adj_rating_a = rating_a + HOST_ADVANTAGE
    if team_b in HOST_NATIONS:
        adj_rating_b = rating_b + HOST_ADVANTAGE

    exp_a = expected_score(adj_rating_a, adj_rating_b)
    mult = goal_diff_multiplier(score_a - score_b)

    change = k * mult * (result_a - exp_a)
    return rating_a + change, rating_b - change


def build_current_ratings(teams_df: pd.DataFrame, results_df: pd.DataFrame, k=30) -> dict:
    """
    Start from each team's base_elo and roll forward through every
    completed match in results_df to get each team's current rating.
    If a 'date' column is present, matches are processed in chronological
    order regardless of the order rows appear in the sheet/CSV.
    """
    ratings = dict(zip(teams_df["team"], teams_df["base_elo"].astype(float)))

    df = results_df.copy()
    if "date" in df.columns:
        df["_sort_date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values("_sort_date", kind="stable")

    for _, row in df.iterrows():
        a, b = row["team_a"], row["team_b"]
        if a not in ratings or b not in ratings:
            # Unknown team name - skip rather than crash, but this usually
            # means a spelling mismatch between the sheet and teams.csv
            continue
        sa, sb = float(row["score_a"]), float(row["score_b"])
        ra, rb = ratings[a], ratings[b]
        new_ra, new_rb = update_ratings(ra, rb, sa, sb, k=k, team_a=a, team_b=b)
        ratings[a] = new_ra
        ratings[b] = new_rb

    return ratings


def win_draw_prob(rating_a, rating_b, draw_weight=0.26):
    """
    Splits a 2-outcome Elo expectation into win/draw/loss probabilities
    for a GROUP STAGE style match (where draws are possible).
    draw_weight controls how much probability mass goes to a draw,
    concentrated around evenly-matched games.
    """
    exp_a = expected_score(rating_a, rating_b)
    # Closeness factor: highest when exp_a is near 0.5, near zero when lopsided
    closeness = 1 - abs(exp_a - 0.5) * 2
    p_draw = draw_weight * closeness
    p_a = (exp_a - 0.5 * p_draw / (1 - p_draw + 1e-9)) if p_draw < 1 else 0
    # Simpler, numerically safe approach: split remaining prob by exp_a ratio
    remaining = 1 - p_draw
    p_a = remaining * exp_a
    p_b = remaining * (1 - exp_a)
    return p_a, p_draw, p_b
