import pandas as pd
import os

def clean_fuel_data(input_file: str, output_file: str):
    print(f"Reading {input_file}...")
    df = pd.read_csv(input_file)
    original_count = len(df)

    us_states = [
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
        'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
        'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
        'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
        'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
        'DC'
    ]

    # Fix 1: Filter to US states
    df = df[df['State'].isin(us_states)]

    # Fix 2: Strip whitespaces from City and Address
    if 'City' in df.columns:
        df['City'] = df['City'].str.strip()
    if 'Address' in df.columns:
        df['Address'] = df['Address'].str.strip()

    # Fix 3 & 4: Sort by Retail Price ascending, drop duplicates by OPIS ID
    if 'Retail Price' in df.columns and 'OPIS Truckstop ID' in df.columns:
        df = df.sort_values('Retail Price', ascending=True)
        df = df.drop_duplicates(subset=['OPIS Truckstop ID'], keep='first')

    # Fix 5: Round Retail Price to 5 decimal places
    if 'Retail Price' in df.columns:
        df['Retail Price'] = df['Retail Price'].round(5)

    # Drop the Rack ID column as it is unused
    if 'Rack ID' in df.columns:
        df = df.drop(columns=['Rack ID'])

    # Export to clean CSV
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    df.to_csv(output_file, index=False)
    
    cleaned_count = len(df)
    print(f"Original row count: {original_count}")
    print(f"Cleaned row count:  {cleaned_count}")
    print(f"Clean data exported to: {output_file}")

if __name__ == "__main__":
    clean_fuel_data("data/fuel-prices-for-be-assessment.csv", "data/fuel_prices_clean.csv")