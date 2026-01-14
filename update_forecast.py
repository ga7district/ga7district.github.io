"""
Automated Forecast Updater
===========================

This script:
1. Scrapes the latest Generic Ballot average from RealClearPolling
2. Runs the forecast model with the updated Generic Ballot
3. Outputs updated CSV file for the web display

Usage:
    python update_forecast.py
"""

import requests
from bs4 import BeautifulSoup
import re
import subprocess
import sys
import os
from datetime import datetime

# RCP Generic Ballot URL
RCP_URL = "https://www.realclearpolling.com/polls/state-of-the-union/generic-congressional-vote"

def scrape_generic_ballot():
    """
    Scrape the latest Generic Ballot average from RealClearPolling.

    Returns:
        float: Generic ballot margin (positive = Dem advantage, negative = GOP advantage)
    """
    print(f"Fetching Generic Ballot from RCP...")
    print(f"URL: {RCP_URL}")

    try:
        # Set headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        response = requests.get(RCP_URL, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Method 1: Look for "RCP Average" in table
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 5:
                    poll_name = cells[0].get_text(strip=True)
                    if 'RCP Average' in poll_name or 'Average' in poll_name:
                        # Try to find D and R percentages
                        for i, cell in enumerate(cells):
                            text = cell.get_text(strip=True)
                            # Look for pattern like "45.2" or "D+3.5"
                            match = re.search(r'(D|R)\+?([0-9.]+)', text)
                            if match:
                                party = match.group(1)
                                value = float(match.group(2))
                                margin = value if party == 'D' else -value
                                print(f"  Found RCP Average: {party}+{value}")
                                return margin

                            # Look for two consecutive percentage values
                            if i < len(cells) - 1:
                                try:
                                    dem_val = float(text)
                                    rep_val = float(cells[i+1].get_text(strip=True))
                                    if 35 < dem_val < 65 and 35 < rep_val < 65:
                                        margin = dem_val - rep_val
                                        print(f"  Found RCP Average: D {dem_val:.1f}% - R {rep_val:.1f}% = ", end="")
                                        if margin > 0:
                                            print(f"D+{margin:.1f}")
                                        else:
                                            print(f"R+{abs(margin):.1f}")
                                        return margin
                                except ValueError:
                                    continue

        # Method 2: Look for any prominent margin display
        # Search for patterns like "Democrats +3.5" or "Republicans +2.1"
        text_content = soup.get_text()
        patterns = [
            r'Democrats?\s*\+?\s*([0-9.]+)',
            r'Republicans?\s*\+?\s*([0-9.]+)',
            r'Dem\s*\+\s*([0-9.]+)',
            r'GOP\s*\+\s*([0-9.]+)',
            r'D\s*\+\s*([0-9.]+)',
            r'R\s*\+\s*([0-9.]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                is_dem = 'D' in pattern or 'Dem' in pattern
                margin = value if is_dem else -value
                party = 'D' if is_dem else 'R'
                print(f"  Found in text: {party}+{value}")
                return margin

        print("  Warning: Could not parse Generic Ballot. Using default value of 0.0")
        return 0.0

    except requests.exceptions.RequestException as e:
        print(f"  Error fetching data: {e}")
        print("  Using default Generic Ballot value: 0.0")
        return 0.0
    except Exception as e:
        print(f"  Unexpected error: {e}")
        print("  Using default Generic Ballot value: 0.0")
        return 0.0


def run_forecast(generic_ballot):
    """
    Run the forecast script with the given generic ballot value.

    Args:
        generic_ballot (float): Generic ballot margin
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    pvi_file = os.path.join(script_dir, "District2025PVIs.xlsx")
    war_file = os.path.join(script_dir, "WinAboveReplacementData.csv")
    forecast_script = os.path.join(script_dir, "forecast_all_2026_races.py")

    print(f"\nRunning forecast with Generic Ballot: ", end="")
    if generic_ballot > 0:
        print(f"D+{generic_ballot:.1f}")
    elif generic_ballot < 0:
        print(f"R+{abs(generic_ballot):.1f}")
    else:
        print("EVEN")

    # Run the forecast script
    cmd = [
        sys.executable,
        forecast_script,
        pvi_file,
        war_file,
        str(generic_ballot),
        "1000"  # number of simulations
    ]

    print(f"\nExecuting: {' '.join(cmd)}")
    print("="*70)

    result = subprocess.run(cmd, capture_output=False, text=True)

    if result.returncode == 0:
        print("\n" + "="*70)
        print("Forecast updated successfully!")
    else:
        print("\n" + "="*70)
        print("Error running forecast script!")
        sys.exit(1)


def main():
    """Main execution function."""
    print("="*70)
    print("       2026 HOUSE FORECAST - AUTOMATED UPDATE")
    print("="*70)
    print(f"\nRun time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Step 1: Scrape Generic Ballot
    generic_ballot = scrape_generic_ballot()

    # Step 2: Run forecast
    run_forecast(generic_ballot)

    print("\n" + "="*70)
    print("Update complete!")
    print("="*70)


if __name__ == "__main__":
    main()
