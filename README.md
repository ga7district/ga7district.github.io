# Forecast Info

An empirical election forecasting model for the 2026 House elections, automatically updated daily with the latest polling data.

## Overview

This forecast uses a regression model based on three key factors:
- **PVI (Partisan Voter Index)**: District-level partisan lean
- **WAR (Wins Above Replacement)**: Candidate quality metric
- **Generic Ballot**: National polling environment

**Model Formula**: `Dem_Margin = -0.24 + 1.03×PVI - 0.51×WAR + 0.19×Generic_Ballot`

**Model Performance**: R² = 0.892, RMSE = 5.35 points (based on 1,157 races from 2020-2024)

## Files

- `index.html` - Interactive web dashboard displaying the forecast
- `forecast_all_2026_races.py` - Core forecasting model with Monte Carlo simulation
- `update_forecast.py` - Automated script that scrapes RCP and updates the forecast
- `house_2026_forecast.csv` - Current forecast data (updated daily)
- `.github/workflows/update-forecast.yml` - GitHub Actions workflow for automation

## Quick Start

### View the Forecast

1. Open `index.html` in any web browser
2. The page displays:
   - Summary statistics (projected seats, majority probability)
   - Race ratings distribution chart
   - Most competitive races
   - Potential seat flips
   - Full methodology

### Run the Forecast Manually

```bash
python forecast_all_2026_races.py
```

You'll be prompted for:
- PVI data file location
- WAR data file location
- Generic Ballot value (e.g., 4.5 for D+4.5)
- Number of simulations (default: 1000)

### Update with Latest Polling

```bash
python update_forecast.py
```

This will:
1. Scrape the latest Generic Ballot from RealClearPolling
2. Run the forecast model with updated data
3. Generate new `house_2026_forecast.csv`

## Automated Daily Updates (GitHub)

To enable automatic daily updates:

### 1. Create a GitHub Repository

```bash
git init
git add .
git commit -m "Initial commit: 2026 House Forecast"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 2. Enable GitHub Actions

The workflow file `.github/workflows/update-forecast.yml` is already configured to:
- Run daily at 6:00 AM EST
- Scrape the latest Generic Ballot from RCP
- Update the forecast
- Commit changes automatically

### 3. Enable GitHub Pages (Optional)

To host the forecast online:
1. Go to repository Settings → Pages
2. Set Source to "Deploy from a branch"
3. Select branch: `main`, folder: `/ (root)`
4. Click Save

Your forecast will be live at: `https://YOUR_USERNAME.github.io/YOUR_REPO/`

## Dependencies

```bash
pip install pandas numpy openpyxl requests beautifulsoup4
```

## Data Sources

- **PVI Data**: `District2025PVIs.xlsx` - Cook Political Report 2025 Partisan Voter Index
- **WAR Data**: `WinAboveReplacementData.csv` - Candidate quality metrics (2016-2024)
- **Generic Ballot**: Scraped daily from [RealClearPolling](https://www.realclearpolling.com/polls/state-of-the-union/generic-congressional-vote)
- **Retirements**: Tracked in `forecast_all_2026_races.py` based on Ballotpedia data

## Methodology

### Model Development

The model was trained on 1,157 contested House races from 2020-2024 using ordinary least squares (OLS) regression. All coefficients are statistically significant (p < 0.001).

### Monte Carlo Simulation

Each race is simulated 1,000 times by adding random error drawn from a normal distribution with standard deviation = model RMSE (5.35 points). This produces:
- Win probabilities for each party
- Confidence intervals
- Overall seat distribution

### Race Ratings

Ratings are based on win probability:
- **Safe**: ≥99% win probability
- **Likely**: 90-99% win probability
- **Lean**: 75-90% win probability
- **Tilt**: 50-75% win probability
- **Toss-up**: Exactly 50%

### Open Seats

Districts with retiring incumbents have WAR set to 0.0 (average candidate quality assumed).

## Customization

### Adjust Generic Ballot Manually

Edit line 8 in `update_forecast.py` or run forecast directly:

```bash
python forecast_all_2026_races.py District2025PVIs.xlsx WinAboveReplacementData.csv 4.5 1000
```

### Change Update Schedule

Edit `.github/workflows/update-forecast.yml`, line 5:

```yaml
- cron: '0 11 * * *'  # 6 AM EST = 11:00 UTC
```

Use [crontab.guru](https://crontab.guru/) to generate different schedules.

### Modify Display

Edit `index.html` to customize:
- Colors and styling (CSS section)
- Charts and visualizations (Chart.js configuration)
- Table columns and layout

## Troubleshooting

### GitHub Actions Not Running

1. Ensure Actions are enabled: Settings → Actions → General → Allow all actions
2. Check workflow runs: Actions tab in repository
3. Verify file is at `.github/workflows/update-forecast.yml`

### Web Scraping Issues

If RCP changes their page structure:
1. Check `update_forecast.py` line 38-90
2. Update the HTML parsing logic in `scrape_generic_ballot()`
3. Test with: `python update_forecast.py`

### Display Not Updating

1. Hard refresh the page (Ctrl+F5 / Cmd+Shift+R)
2. Check that `house_2026_forecast.csv` was updated
3. Verify CSV format matches expected structure

## License

This forecast is for educational and informational purposes. Model and code are provided as-is.

## Contact

For questions about methodology or to report issues, please open a GitHub issue.

---

**Last Model Update**: January 2026
**Data Through**: 2024 General Election
