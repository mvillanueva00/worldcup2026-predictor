"""
sheets_io.py
Reads teams / results / bracket data from a shared Google Sheet
(so multiple coworkers can update it), with automatic fallback to the
local CSV files in data/ if no Google Sheet is configured yet.

To enable Google Sheets:
1. Create a Google Sheet with three tabs: "teams", "results", "bracket"
   (see data/*.csv in this project for the exact column headers to use).
2. Create a Google Cloud service account with the Sheets API enabled,
   download its JSON key, and share the Sheet with the service account's
   email address (Editor access).
3. In Streamlit, add the service account JSON and the Sheet ID/URL to
   .streamlit/secrets.toml (see secrets.toml.example in this project).
4. That's it - the app will automatically use the Sheet instead of the
   local CSVs once secrets are present.
"""

import pandas as pd
import streamlit as st

DATA_DIR = "data"


def _load_csv_fallback(name: str) -> pd.DataFrame:
    return pd.read_csv(f"{DATA_DIR}/{name}.csv")


def _get_gsheet_client():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


def using_google_sheets() -> bool:
    try:
        return "gcp_service_account" in st.secrets and "sheet_url" in st.secrets
    except Exception:
        return False


@st.cache_data(ttl=30, show_spinner=False)
def load_sheet_tab(tab_name: str) -> pd.DataFrame:
    """
    Loads a single tab as a DataFrame. Falls back to data/<tab_name>.csv
    if Google Sheets isn't configured, or if anything goes wrong while
    talking to the Sheets API (so the app never hard-crashes for your
    coworkers if a credential expires mid-tournament).

    Cached for 30 seconds: every Streamlit interaction (a slider move, a
    button click) re-runs the whole script, and without caching that
    means a fresh API call to Google for every tab on every single click.
    With several people using the app at once, that blows through
    Google Sheets' free-tier rate limit (60 read requests/minute) almost
    immediately. Caching means the app only actually re-fetches from
    Google once every 30 seconds, regardless of how many people are
    clicking around - new results/picks will show up within ~30 seconds
    instead of instantly, which is a small tradeoff for the app not
    breaking under normal use.
    """
    if not using_google_sheets():
        return _load_csv_fallback(tab_name)

    try:
        gc = _get_gsheet_client()
        sh = gc.open_by_url(st.secrets["sheet_url"])
        worksheet = sh.worksheet(tab_name)
        records = worksheet.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return _load_csv_fallback(tab_name)

        # Manual editing in Google Sheets commonly introduces two issues:
        # trailing blank rows (from formatting extending past the real data)
        # and stray leading/trailing spaces in typed team names. Both are
        # silent failure risks - a name with an extra space won't match
        # anything in teams.csv and will just quietly vanish from the
        # ratings calc - so we clean both up here.
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].astype(str).str.strip()
        df = df[~df.apply(lambda row: all(str(v).strip() == "" for v in row), axis=1)]
        df = df.reset_index(drop=True)

        return df
    except Exception as e:
        import gspread

        if isinstance(e, gspread.exceptions.WorksheetNotFound):
            # Normal pre-launch state (e.g. nobody has submitted a bracket
            # pick yet) - no need to alarm anyone with a warning banner.
            return _load_csv_fallback(tab_name)

        st.warning(
            f"Couldn't reach the Google Sheet for '{tab_name}' tab "
            f"({e}). Falling back to local CSV data."
        )
        return _load_csv_fallback(tab_name)


def append_result_row(team_a, team_b, score_a, score_b, stage, date=None):
    """
    Appends a new match result to the 'results' tab of the Google Sheet.
    Only works when Google Sheets is configured; otherwise raises so the
    UI can show a clear message instead of silently doing nothing.
    """
    if not using_google_sheets():
        raise RuntimeError(
            "Google Sheets isn't configured yet, so results can't be "
            "saved from the app. Edit data/results.csv directly for now, "
            "or set up secrets.toml (see README)."
        )
    gc = _get_gsheet_client()
    sh = gc.open_by_url(st.secrets["sheet_url"])
    worksheet = sh.worksheet("results")
    date_str = date.isoformat() if hasattr(date, "isoformat") else (date or "")
    worksheet.append_row([team_a, team_b, score_a, score_b, stage, date_str])
    load_sheet_tab.clear()


def _get_or_create_worksheet(sh, tab_name, header_row):
    """
    Opens a worksheet, creating it with the given header row if it
    doesn't exist yet (used for the 'picks' tab, which isn't part of
    the original Sheet template).
    """
    import gspread

    try:
        return sh.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=500, cols=len(header_row) + 2)
        ws.append_row(header_row)
        return ws


def append_pick_rows(name, match_picks: dict):
    """
    Saves one person's complete bracket picks (every match, Round of 32
    through the Final) to the 'picks' tab. The Final's pick IS their
    champion pick - no separate field needed. Creates the 'picks' tab
    automatically the first time anyone submits.
    """
    if not using_google_sheets():
        raise RuntimeError(
            "Google Sheets isn't configured yet, so picks can't be saved. "
            "Try again once the Sheet is connected."
        )
    import datetime

    gc = _get_gsheet_client()
    sh = gc.open_by_url(st.secrets["sheet_url"])
    worksheet = _get_or_create_worksheet(sh, "picks", ["name", "match_id", "pick", "timestamp"])

    timestamp = datetime.datetime.now().isoformat(timespec="seconds")
    rows = [[name, match_id, team, timestamp] for match_id, team in match_picks.items()]
    worksheet.append_rows(rows)
    load_sheet_tab.clear()


def append_participant(name):
    """
    Adds a name to the 'participants' roster tab so they show up as a
    pickable option in the bracket submission form. Creates the
    'participants' tab automatically the first time anyone is added.
    """
    if not using_google_sheets():
        raise RuntimeError(
            "Google Sheets isn't configured yet, so the roster can't be "
            "updated. Try again once the Sheet is connected."
        )
    gc = _get_gsheet_client()
    sh = gc.open_by_url(st.secrets["sheet_url"])
    worksheet = _get_or_create_worksheet(sh, "participants", ["name"])
    worksheet.append_row([name])
    load_sheet_tab.clear()


def remove_participant(name):
    """
    Removes a name from the 'participants' roster tab. If the same name
    appears more than once (shouldn't normally happen), removes all
    matching rows.
    """
    if not using_google_sheets():
        raise RuntimeError(
            "Google Sheets isn't configured yet, so the roster can't be "
            "updated."
        )
    gc = _get_gsheet_client()
    sh = gc.open_by_url(st.secrets["sheet_url"])
    worksheet = _get_or_create_worksheet(sh, "participants", ["name"])

    all_values = worksheet.get_all_values()
    # Delete from the bottom up so row numbers don't shift mid-loop
    for row_idx in range(len(all_values), 1, -1):  # skip header row 1
        if all_values[row_idx - 1] and all_values[row_idx - 1][0].strip() == name.strip():
            worksheet.delete_rows(row_idx)
    load_sheet_tab.clear()


def clear_picks_for_name(name):
    """
    Deletes every saved pick row for a given name from the 'picks' tab,
    effectively un-locking them so they can resubmit a fresh bracket.
    Used for corrections (e.g. a bracket structure fix after they already
    submitted) - not meant for routine use.
    """
    if not using_google_sheets():
        raise RuntimeError(
            "Google Sheets isn't configured yet, so picks can't be cleared."
        )
    gc = _get_gsheet_client()
    sh = gc.open_by_url(st.secrets["sheet_url"])
    worksheet = _get_or_create_worksheet(sh, "picks", ["name", "match_id", "pick", "timestamp"])

    all_values = worksheet.get_all_values()
    removed = 0
    # Delete from the bottom up so row numbers don't shift mid-loop
    for row_idx in range(len(all_values), 1, -1):  # skip header row 1
        if all_values[row_idx - 1] and all_values[row_idx - 1][0].strip() == name.strip():
            worksheet.delete_rows(row_idx)
            removed += 1
    load_sheet_tab.clear()
    return removed
