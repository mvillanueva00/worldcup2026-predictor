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


def load_sheet_tab(tab_name: str) -> pd.DataFrame:
    """
    Loads a single tab as a DataFrame. Falls back to data/<tab_name>.csv
    if Google Sheets isn't configured, or if anything goes wrong while
    talking to the Sheets API (so the app never hard-crashes for your
    coworkers if a credential expires mid-tournament).
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
