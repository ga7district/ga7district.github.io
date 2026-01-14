"""
2026 U.S. House Election Forecast - All 435 Districts
======================================================

This script:
1. Loads PVI and WAR data from local files
2. Runs the forecasting model on all districts
3. Simulates each race 1,000 times using Monte Carlo
4. Outputs results to CSV files

MODEL COEFFICIENTS (Empirically derived from 2020-2024 House elections)
Based on OLS regression with 1,157 contested races:

  Dem_Margin = -0.24 + 1.03*PVI - 0.51*WAR + 0.19*Generic_Ballot

Model Performance:
  - R² = 0.892 (89.2% of variance explained)
  - RMSE = 5.35 points (used for simulation uncertainty)
  - All coefficients significant at p < 0.001

Usage:
    python forecast_all_2026_races.py

Or with command line arguments:
    python forecast_all_2026_races.py <pvi_file> <war_file> <generic_ballot> [n_simulations]
"""

import pandas as pd
import numpy as np
import random
import sys
import os

# =============================================================================
# MODEL COEFFICIENTS (Empirically derived from 2020-2024 data)
# =============================================================================

MODEL_COEFFICIENTS = {
    'intercept': -0.2425,
    'pvi': 1.0320,
    'war': -0.5130,
    'generic_ballot': 0.1876
}

# Model standard error (RMSE) - used for simulation
MODEL_RMSE = 5.3522

# Model diagnostics
MODEL_STATS = {
    'r_squared': 0.892,
    'rmse': 5.35,
    'n_observations': 1157,
    'years': '2020-2024'
}

# =============================================================================
# RETIREMENT DATA (from Ballotpedia, Dec 23, 2025)
# =============================================================================

RETIREMENTS_2026 = {
    'NY-21': ('Elise Stefanik', 'R', 'Retiring'),
    'WA-04': ('Dan Newhouse', 'R', 'Retiring'),
    'TX-33': ('Marc Veasey', 'D', 'Retiring'),
    'TX-37': ('Lloyd Doggett', 'D', 'Retiring'),
    'TX-22': ('Troy Nehls', 'R', 'Retiring'),
    'NY-07': ('Nydia Velazquez', 'D', 'Retiring'),
    'TX-19': ('Jodey Arrington', 'R', 'Retiring'),
    'NJ-12': ('Bonnie Watson Coleman', 'D', 'Retiring'),
    'CA-11': ('Nancy Pelosi', 'D', 'Retiring'),
    'IL-04': ('Jesus Garcia', 'D', 'Retiring'),
    'ME-02': ('Jared Golden', 'D', 'Retiring'),
    'TX-10': ('Michael McCaul', 'R', 'Retiring'),
    'TX-08': ('Morgan Luttrell', 'R', 'Retiring'),
    'NY-12': ('Jerrold Nadler', 'D', 'Retiring'),
    'IL-07': ('Danny K. Davis', 'D', 'Retiring'),
    'NE-02': ('Don Bacon', 'R', 'Retiring'),
    'PA-03': ('Dwight Evans', 'D', 'Retiring'),
    'IL-09': ('Jan Schakowsky', 'D', 'Retiring'),
    'WY-AL': ('Harriet Hageman', 'R', 'Running for Senate'),
    'TX-30': ('Jasmine Crockett', 'D', 'Running for Senate'),
    'MA-06': ('Seth Moulton', 'D', 'Running for Senate'),
    'TX-38': ('Wesley Hunt', 'R', 'Running for Senate'),
    'IA-02': ('Ashley Hinson', 'R', 'Running for Senate'),
    'AL-01': ('Barry Moore', 'R', 'Running for Senate'),
    'GA-10': ('Mike Collins', 'R', 'Running for Senate'),
    'GA-01': ('Buddy Carter', 'R', 'Running for Senate'),
    'IL-08': ('Raja Krishnamoorthi', 'D', 'Running for Senate'),
    'IL-02': ('Robin Kelly', 'D', 'Running for Senate'),
    'MN-02': ('Angie Craig', 'D', 'Running for Senate'),
    'KY-06': ('Andy Barr', 'R', 'Running for Senate'),
    'MI-11': ('Haley Stevens', 'D', 'Running for Senate'),
    'NH-01': ('Chris Pappas', 'D', 'Running for Senate'),
    'CA-14': ('Eric Swalwell', 'D', 'Running for Governor'),
    'AZ-01': ('David Schweikert', 'R', 'Running for Governor'),
    'WI-07': ('Tom Tiffany', 'R', 'Running for Governor'),
    'SC-01': ('Nancy Mace', 'R', 'Running for Governor'),
    'SC-05': ('Ralph Norman', 'R', 'Running for Governor'),
    'SD-AL': ('Dusty Johnson', 'R', 'Running for Governor'),
    'IA-04': ('Randy Feenstra', 'R', 'Running for Governor'),
    'MI-10': ('John James', 'R', 'Running for Governor'),
    'TN-06': ('John Rose', 'R', 'Running for Governor'),
    'FL-19': ('Byron Donalds', 'R', 'Running for Governor'),
    'AZ-05': ('Andy Biggs', 'R', 'Running for Governor'),
    'TX-21': ('Chip Roy', 'R', 'Running for AG'),
    'NJ-11': ('Mikie Sherrill', 'D', 'Resigned - Now Governor'),
    'TN-07': ('Mark Green', 'R', 'Resigned'),
    'VA-11': ('Gerald Connolly', 'D', 'Deceased'),
    'AZ-07': ('Raul Grijalva', 'D', 'Deceased'),
    'TX-18': ('Sylvester Turner', 'D', 'Deceased'),
    'FL-06': ('Michael Waltz', 'R', 'Resigned - NSA'),
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_pvi(pvi_str):
    """Convert PVI string (e.g., 'D+5', 'R+10', 'EVEN') to numeric."""
    if pd.isna(pvi_str) or pvi_str == 'EVEN':
        return 0.0
    pvi_str = str(pvi_str).strip()
    if pvi_str.startswith('D+'):
        return float(pvi_str[2:])
    elif pvi_str.startswith('R+'):
        return -float(pvi_str[2:])
    return 0.0


def get_race_rating(margin, d_win_pct=None):
    """Convert margin to race rating, optionally using win probability."""
    if d_win_pct is not None:
        # Use simulation-based rating
        if d_win_pct >= 99:
            return "Safe D"
        elif d_win_pct >= 90:
            return "Likely D"
        elif d_win_pct >= 75:
            return "Lean D"
        elif d_win_pct > 50:
            return "Tilt D"
        elif d_win_pct == 50:
            return "Toss-up"
        elif d_win_pct >= 25:
            return "Tilt R"
        elif d_win_pct >= 10:
            return "Lean R"
        elif d_win_pct >= 1:
            return "Likely R"
        else:
            return "Safe R"
    else:
        # Use margin-based rating
        margin_abs = abs(margin)
        winner = "D" if margin > 0 else "R"
        if margin_abs > 15:
            return f"Safe {winner}"
        elif margin_abs > 10:
            return f"Likely {winner}"
        elif margin_abs > 5:
            return f"Lean {winner}"
        else:
            return f"Toss-up {winner}"


def forecast_district(pvi, war, generic_ballot):
    """Calculate predicted Democratic margin for a district."""
    pred_margin = (MODEL_COEFFICIENTS['intercept'] + 
                   MODEL_COEFFICIENTS['pvi'] * pvi + 
                   MODEL_COEFFICIENTS['war'] * war + 
                   MODEL_COEFFICIENTS['generic_ballot'] * generic_ballot)
    return pred_margin


def simulate_race(predicted_margin, n_simulations=1000, rmse=MODEL_RMSE):
    """
    Simulate a race n_simulations times using the model's RMSE.
    
    Returns:
    - d_wins: Number of Democratic wins
    - r_wins: Number of Republican wins
    - d_win_pct: Democratic win probability (%)
    - avg_margin: Average margin across simulations
    - margin_std: Standard deviation of margins
    """
    d_wins = 0
    r_wins = 0
    margins = []
    
    for _ in range(n_simulations):
        # Add random error from normal distribution with std = RMSE
        error = random.gauss(0, rmse)
        simulated_margin = predicted_margin + error
        margins.append(simulated_margin)
        
        if simulated_margin > 0:
            d_wins += 1
        else:
            r_wins += 1
    
    d_win_pct = (d_wins / n_simulations) * 100
    avg_margin = np.mean(margins)
    margin_std = np.std(margins)
    
    return {
        'd_wins': d_wins,
        'r_wins': r_wins,
        'd_win_pct': round(d_win_pct, 1),
        'r_win_pct': round(100 - d_win_pct, 1),
        'avg_margin': round(avg_margin, 2),
        'margin_std': round(margin_std, 2)
    }


def simulate_all_races(forecast_df, n_simulations=1000):
    """
    Run Monte Carlo simulation for the entire House.
    
    Returns distribution of total D and R seats across simulations.
    """
    print(f"\nRunning {n_simulations} simulations of entire House...")
    
    d_seat_counts = []
    r_seat_counts = []
    
    predicted_margins = forecast_df['predicted_margin'].values
    
    for sim in range(n_simulations):
        d_seats = 0
        r_seats = 0
        
        for margin in predicted_margins:
            error = random.gauss(0, MODEL_RMSE)
            simulated_margin = margin + error
            
            if simulated_margin > 0:
                d_seats += 1
            else:
                r_seats += 1
        
        d_seat_counts.append(d_seats)
        r_seat_counts.append(r_seats)
        
        if (sim + 1) % 200 == 0:
            print(f"  Completed {sim + 1}/{n_simulations} simulations...")
    
    return {
        'd_seats': d_seat_counts,
        'r_seats': r_seat_counts,
        'd_mean': np.mean(d_seat_counts),
        'r_mean': np.mean(r_seat_counts),
        'd_std': np.std(d_seat_counts),
        'd_median': np.median(d_seat_counts),
        'd_min': min(d_seat_counts),
        'd_max': max(d_seat_counts),
        'd_majority_pct': sum(1 for x in d_seat_counts if x >= 218) / n_simulations * 100
    }


def find_file(filename, search_dirs=None):
    """Try to find a file in common locations."""
    if search_dirs is None:
        search_dirs = ['.', os.path.expanduser('~'), 
                       os.path.expanduser('~/Downloads'),
                       os.path.expanduser('~/Documents')]
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        search_dirs.insert(1, script_dir)
    except:
        pass
    
    for dir_path in search_dirs:
        full_path = os.path.join(dir_path, filename)
        if os.path.exists(full_path):
            return full_path
    return None


def get_file_path(prompt, default_filename):
    """Get file path from user, with auto-detection."""
    auto_path = find_file(default_filename)
    if auto_path:
        print(f"  Found: {auto_path}")
        use_auto = input(f"  Use this file? (Y/N) [Y]: ").strip().upper()
        if use_auto != 'N':
            return auto_path
    
    while True:
        path = input(f"{prompt}: ").strip().strip('"').strip("'")
        if os.path.exists(path):
            return path
        print(f"  Error: File not found. Please try again.")


# =============================================================================
# MAIN FUNCTIONS
# =============================================================================

def load_data(pvi_path, war_path):
    """Load PVI and WAR data from files."""
    print(f"\nLoading PVI data from: {pvi_path}")
    pvi_df = pd.read_excel(pvi_path)
    pvi_df['pvi_numeric'] = pvi_df['2025 PVI'].apply(parse_pvi)
    pvi_df['district_id'] = pvi_df['Dist']
    print(f"  Loaded {len(pvi_df)} districts")
    
    print(f"\nLoading WAR data from: {war_path}")
    war_df = pd.read_csv(war_path, encoding='utf-8-sig')
    war_2024 = war_df[war_df['Year'] == 2024].copy()
    war_dict = dict(zip(war_2024['Geography'], war_2024['Sortable']))
    print(f"  Loaded {len(war_dict)} WAR values from 2024")
    
    return pvi_df, war_dict


def run_forecast(pvi_df, war_dict, generic_ballot, n_simulations=1000):
    """Run forecast on all districts with Monte Carlo simulation."""
    
    print(f"\nForecasting {len(pvi_df)} districts...")
    print(f"Running {n_simulations} simulations per race...")
    
    forecasts = []
    
    for idx, row in pvi_df.iterrows():
        district = row['Dist']
        incumbent = row['2025 Incumbent']
        party = row['Party']
        pvi_str = row['2025 PVI']
        pvi = parse_pvi(pvi_str)
        
        war = war_dict.get(district, 0.0)
        is_open_seat = district in RETIREMENTS_2026
        retirement_reason = RETIREMENTS_2026.get(district, (None, None, None))[2] if is_open_seat else None
        
        if is_open_seat:
            war = 0.0
        
        # Point estimate
        pred_margin = forecast_district(pvi, war, generic_ballot)
        pred_winner = 'D' if pred_margin > 0 else 'R'
        
        # Monte Carlo simulation
        sim_results = simulate_race(pred_margin, n_simulations, MODEL_RMSE)
        
        # Rating based on win probability
        rating = get_race_rating(pred_margin, sim_results['d_win_pct'])
        
        is_flip = (pred_winner != party)
        
        forecasts.append({
            'district_id': district,
            'incumbent_2025': incumbent,
            'incumbent_party': party,
            'pvi_string': pvi_str,
            'pvi_numeric': pvi,
            'is_open_seat': is_open_seat,
            'retirement_reason': retirement_reason,
            'war': war,
            'generic_ballot': generic_ballot,
            'predicted_margin': round(pred_margin, 2),
            'predicted_winner': pred_winner,
            'd_win_pct': sim_results['d_win_pct'],
            'r_win_pct': sim_results['r_win_pct'],
            'race_rating': rating,
            'potential_flip': is_flip,
            'sim_avg_margin': sim_results['avg_margin'],
            'sim_margin_std': sim_results['margin_std']
        })
        
        if (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1}/{len(pvi_df)} districts...")
    
    forecast_df = pd.DataFrame(forecasts)
    forecast_df = forecast_df.sort_values('predicted_margin', key=abs)
    
    return forecast_df


def print_summary(forecast_df, generic_ballot, house_sim_results=None):
    """Print forecast summary."""
    
    dem_seats = (forecast_df['predicted_winner'] == 'D').sum()
    rep_seats = (forecast_df['predicted_winner'] == 'R').sum()
    
    # Count by rating
    tossups = forecast_df['race_rating'].str.contains('Toss-up|Tilt').sum()
    flips_to_d = ((forecast_df['potential_flip']) & (forecast_df['predicted_winner'] == 'D')).sum()
    flips_to_r = ((forecast_df['potential_flip']) & (forecast_df['predicted_winner'] == 'R')).sum()
    
    print("\n" + "="*70)
    print("2026 HOUSE FORECAST SUMMARY")
    print("="*70)
    
    print(f"\nNational Environment: Generic Ballot {'D+' if generic_ballot > 0 else 'R+'}{abs(generic_ballot)}")
    print(f"\nModel: Dem_Margin = -0.24 + 1.03*PVI - 0.51*WAR + 0.19*GB")
    print(f"       (R² = 0.892, RMSE = {MODEL_RMSE:.2f} pts)")
    
    print(f"\n{'='*70}")
    print("POINT ESTIMATE (Based on predicted margins)")
    print(f"{'='*70}")
    print(f"  Democrats:   {dem_seats}")
    print(f"  Republicans: {rep_seats}")
    print(f"  Net change:  {'D' if flips_to_d >= flips_to_r else 'R'}+{abs(flips_to_d - flips_to_r)}")
    
    if house_sim_results:
        print(f"\n{'='*70}")
        print("MONTE CARLO SIMULATION RESULTS")
        print(f"{'='*70}")
        print(f"  Simulations:           {len(house_sim_results['d_seats'])}")
        print(f"  Dem seats (mean):      {house_sim_results['d_mean']:.1f}")
        print(f"  Dem seats (median):    {house_sim_results['d_median']:.0f}")
        print(f"  Dem seats (std dev):   {house_sim_results['d_std']:.1f}")
        print(f"  Dem seats (range):     {house_sim_results['d_min']} - {house_sim_results['d_max']}")
        print(f"\n  DEM MAJORITY PROB:     {house_sim_results['d_majority_pct']:.1f}%")
        print(f"  GOP MAJORITY PROB:     {100 - house_sim_results['d_majority_pct']:.1f}%")
        
        # Percentiles
        d_seats = house_sim_results['d_seats']
        print(f"\n  Seat Distribution Percentiles:")
        for pct in [5, 10, 25, 50, 75, 90, 95]:
            seats = np.percentile(d_seats, pct)
            print(f"    {pct}th percentile: D {seats:.0f} - R {435-seats:.0f}")
    
    print(f"\n{'='*70}")
    print("RACE RATINGS (Based on Win Probability)")
    print(f"{'='*70}")
    rating_order = ['Safe D', 'Likely D', 'Lean D', 'Tilt D', 'Toss-up', 
                    'Tilt R', 'Lean R', 'Likely R', 'Safe R']
    for rating in rating_order:
        count = (forecast_df['race_rating'] == rating).sum()
        if count > 0:
            print(f"  {rating}: {count}")
    
    print(f"\n{'='*70}")
    print("TOP 25 MOST COMPETITIVE RACES (by win probability)")
    print(f"{'='*70}")
    
    # Sort by how close to 50% the D win probability is
    forecast_df['competitiveness'] = abs(forecast_df['d_win_pct'] - 50)
    competitive = forecast_df.nsmallest(25, 'competitiveness')[
        ['district_id', 'incumbent_2025', 'pvi_string', 'predicted_margin', 
         'd_win_pct', 'r_win_pct', 'race_rating']
    ]
    print(competitive.to_string(index=False))
    
    print(f"\n{'='*70}")
    print("POTENTIAL FLIPS:")
    print(f"{'='*70}")
    
    flips = forecast_df[forecast_df['potential_flip']]
    
    print(f"\nD Pickups ({flips_to_d} seats):")
    d_pickups = flips[flips['predicted_winner'] == 'D'].sort_values('d_win_pct', ascending=False)
    if len(d_pickups) > 0:
        print(d_pickups[['district_id', 'incumbent_party', 'pvi_string', 
                         'predicted_margin', 'd_win_pct', 'race_rating']].to_string(index=False))
    else:
        print("  None")
    
    print(f"\nR Pickups ({flips_to_r} seats):")
    r_pickups = flips[flips['predicted_winner'] == 'R'].sort_values('r_win_pct', ascending=False)
    if len(r_pickups) > 0:
        print(r_pickups[['district_id', 'incumbent_party', 'pvi_string', 
                         'predicted_margin', 'r_win_pct', 'race_rating']].to_string(index=False))
    else:
        print("  None")


def main():
    """Main function."""
    
    print("="*70)
    print("       2026 U.S. HOUSE ELECTION FORECAST")
    print("       (With Monte Carlo Simulation)")
    print("="*70)
    
    # Default number of simulations
    n_simulations = 1000
    
    # Check for command line arguments
    if len(sys.argv) >= 4:
        pvi_path = sys.argv[1]
        war_path = sys.argv[2]
        generic_ballot = float(sys.argv[3])
        if len(sys.argv) >= 5:
            n_simulations = int(sys.argv[4])
    else:
        print("\n--- DATA FILES ---")
        pvi_path = get_file_path("Path to PVI file (District2025PVIs.xlsx)", "District2025PVIs.xlsx")
        war_path = get_file_path("Path to WAR file (WinAboveReplacementData.csv)", "WinAboveReplacementData.csv")
        
        print("\n--- PARAMETERS ---")
        try:
            gb_input = input("Generic Ballot (e.g., 4.5 for D+4.5, -2 for R+2) [0]: ").strip()
            generic_ballot = float(gb_input) if gb_input else 0.0
        except ValueError:
            generic_ballot = 0.0
        
        try:
            sim_input = input("Number of simulations per race [1000]: ").strip()
            n_simulations = int(sim_input) if sim_input else 1000
        except ValueError:
            n_simulations = 1000
    
    # Load data
    pvi_df, war_dict = load_data(pvi_path, war_path)
    
    # Run forecast with per-race simulations
    forecast_df = run_forecast(pvi_df, war_dict, generic_ballot, n_simulations)
    
    # Run whole-House simulation
    house_sim = simulate_all_races(forecast_df, n_simulations)
    
    # Save results - use current directory, not input file directory
    output_dir = '.'
    forecast_path = os.path.join(output_dir, 'house_2026_forecast.csv')
    forecast_df.to_csv(forecast_path, index=False)
    print(f"\n✓ Forecast saved to: {forecast_path}")
    
    # Print summary
    print_summary(forecast_df, generic_ballot, house_sim)
    
    print("\n" + "="*70)
    print("Forecast complete!")
    print("="*70)
    
    if sys.platform == 'win32':
        input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
