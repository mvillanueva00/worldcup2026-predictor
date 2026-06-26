# World Cup 2026 Winner Predictor

Predicts the World Cup 2026 champion using Elo ratings (seeded from
pre-tournament team strength, updated by actual results so far) and a
Monte Carlo simulation of the remaining knockout bracket.

This mirrors the methodology used by most reputable World Cup forecasters
(e.g. FiveThirtyEight-style models): Elo ratings have repeatedly been shown
to out-predict trained classifiers when the in-tournament sample size is
tiny (36 group games is not enough data to train a reliable ML model on).

## How it works

1. **Team ratings** start from `data/teams.csv` (pre-tournament Elo
   estimates) and get updated using every match in `data/results.csv`
   (or the shared Google Sheet), with bigger wins moving ratings more.
2. **Bracket simulation**: `data/bracket.csv` (or the Sheet's "bracket"
   tab) defines the knockout matchups. Matches that haven't been played
   yet are simulated thousands of times using each team's current Elo
   rating to produce a championship probability for every team still in
   the tournament.

## Project structure

```
worldcup2026_predictor/
├── app.py                  # Streamlit app (run this)
├── elo_engine.py            # Elo rating math
├── simulation.py            # Monte Carlo bracket simulator
├── sheets_io.py             # Google Sheet / CSV data loading
├── requirements.txt
├── secrets.toml.example     # Template for Google Sheet credentials
└── data/
    ├── teams.csv            # Starting Elo ratings (48 teams)
    ├── results.csv          # Matches played so far
    └── bracket.csv          # Knockout matchups (PLACEHOLDER - see below)
```

> **Important:** `data/bracket.csv` currently has placeholder example
> matchups (it includes "Poland", which isn't even in this World Cup).
> Replace it with the real Round of 32 matchups once they're confirmed
> after the group stage finishes (use "Winner M#" for teams that depend
> on an earlier match - see the existing rows for the pattern).

## Running it locally

```bash
cd worldcup2026_predictor
pip install -r requirements.txt
streamlit run app.py
```

It'll work immediately using the local CSV files - no setup required.

## Sharing it with your coworkers (recommended path)

### Step 1: Set up the shared Google Sheet

1. Create a new Google Sheet.
2. Create three tabs named exactly `teams`, `results`, `bracket`.
3. Copy the headers + data from `data/teams.csv`, `data/results.csv`,
   and `data/bracket.csv` into the matching tabs (first row = headers).
4. Click **Share** and give edit access to your coworkers' Google
   accounts.

### Step 2: Create a Google Cloud service account (so the app can read/write the Sheet)

1. Go to https://console.cloud.google.com/ → create a project (or use an
   existing one).
2. Enable the **Google Sheets API** and **Google Drive API**.
3. Go to "IAM & Admin" → "Service Accounts" → "Create Service Account".
4. Once created, open it → "Keys" tab → "Add Key" → "Create new key" →
   JSON. This downloads a JSON file - keep it private.
5. Copy the `client_email` value from that JSON file, and share your
   Google Sheet with that email address (Editor access) - same as
   sharing with a coworker.

### Step 3: Fill in secrets.toml

Copy `secrets.toml.example` → `.streamlit/secrets.toml` and fill in:
- `sheet_url` with your Sheet's URL
- the `[gcp_service_account]` values from the downloaded JSON file
  (it has all the matching field names)

Add `.streamlit/secrets.toml` to your `.gitignore` - never commit real
credentials to GitHub.

### Step 4: Push to GitHub and deploy on Streamlit Community Cloud

Same process as your ADS-509 project:

1. Create a new GitHub repo, push this whole folder to it (everything
   except `.streamlit/secrets.toml`, which should stay local/private).
2. Go to https://share.streamlit.io → "New app" → connect your GitHub
   repo → set the main file to `app.py`.
3. In the app's **Settings → Secrets**, paste the contents of your local
   `.streamlit/secrets.toml` file.
4. Deploy. You'll get a public link like
   `worldcup2026-predictor.streamlit.app` that you and your coworkers can
   open in any browser - no installs needed.

Once deployed, anyone with the link can view live predictions, and
anyone with edit access to the Google Sheet (or who uses the in-app
"Add a new match result" form) can update scores - everyone sees the
update on their next page refresh.

## Updating results without the Google Sheet

If you skip the Google Sheet setup entirely, just edit `data/results.csv`
directly (same column format) and re-run/redeploy. This only works well
for a single person updating things, since local CSV edits don't sync
across deployed instances - the Google Sheet route is what makes this
work properly for multiple coworkers.
