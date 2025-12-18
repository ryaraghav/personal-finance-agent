import pandas as pd

df = pd.read_csv('data/transactions_2024_2025.csv')
overrides = pd.read_csv('data/category_overrides.csv')

for _, row in overrides.iterrows():
    pattern = row['description_pattern']
    correct_category = row['correct_category']
    
    # Escape special characters and use partial match
    import re
    pattern_escaped = re.escape(pattern)
    
    mask = df['description'].str.contains(pattern_escaped, case=False, na=False, regex=True)
    
    if mask.sum() > 0:
        df.loc[mask, 'ai_category'] = correct_category
        print(f"✓ Updated {mask.sum()} transactions: {pattern} → {correct_category}")
    else:
        print(f"✗ No matches found for: {pattern}")
        # Show similar descriptions
        similar = df[df['description'].str.contains('TWELVEMONTH', case=False, na=False)]
        if len(similar) > 0:
            print(f"  Similar descriptions found:")
            print(f"  {similar['description'].unique()[:3]}")

df.to_csv('data/transactions_2024_2025.csv', index=False)