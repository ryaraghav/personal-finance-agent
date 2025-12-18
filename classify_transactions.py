import pandas as pd
import anthropic
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Load API key
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    raise ValueError(
        "ANTHROPIC_API_KEY environment variable is not set. "
        "Please set it using: export ANTHROPIC_API_KEY='your-api-key' "
        "or create a .env file with: ANTHROPIC_API_KEY=your-api-key"
    )
client = anthropic.Anthropic(api_key=api_key)

# Load category definitions
with open('categories.json', 'r') as f:
    category_config = json.load(f)

def classify_transaction(description, bank_category, amount):
    """Send single transaction to Claude for classification"""
    
    prompt = f"""Review this credit card transaction and determine if the category is correct.

Transaction: {description}
Current Category: {bank_category}
Amount: ${amount}

Available Categories: {', '.join(category_config['categories'])}

Category Examples:
{json.dumps(category_config['examples'], indent=2)}

Respond in JSON format:
{{
    "correct_category": "category name",
    "changed": true/false,
    "reasoning": "brief explanation if changed"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Parse response
    response_text = message.content[0].text
    # Extract JSON from response (handling markdown code blocks)
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]
    
    return json.loads(response_text.strip())

def process_transactions(csv_path):
    """Process all transactions from CSV"""
    
    # Read CSV
    df = pd.read_csv(csv_path)
    
    # Map Chase CSV columns to expected format
    # Chase CSV has: Transaction Date, Post Date, Description, Category, Type, Amount, Memo
    df_mapped = pd.DataFrame({
        'date': df['Transaction Date'],
        'description': df['Description'],
        'bank_category': df['Category'],
        'amount': df['Amount']
    })
    
    results = []
    
    for idx, row in df_mapped.iterrows():
        print(f"Processing {idx + 1}/{len(df_mapped)}: {row['description']}")
        
        try:
            classification = classify_transaction(
                row['description'],
                row['bank_category'],
                row['amount']
            )
            
            results.append({
                'date': row['date'],
                'description': row['description'],
                'amount': row['amount'],
                'bank_category': row['bank_category'],
                'ai_category': classification['correct_category'],
                'changed': classification['changed'],
                'reasoning': classification.get('reasoning', '')
            })
        except Exception as e:
            print(f"Error processing row {idx}: {e}")
            results.append({
                'date': row['date'],
                'description': row['description'],
                'amount': row['amount'],
                'bank_category': row['bank_category'],
                'ai_category': 'ERROR',
                'changed': False,
                'reasoning': str(e)
            })
    
    # Save results to data/ directory
    output_df = pd.DataFrame(results)
    os.makedirs('data', exist_ok=True)  # Ensure data directory exists
    output_filename = f"data/reclassified_transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output_df.to_csv(output_filename, index=False)
    
    print(f"\nResults saved to: {output_filename}")
    print(f"Total transactions: {len(results)}")
    print(f"Reclassified: {sum(r['changed'] for r in results)}")
    
    return output_df

if __name__ == "__main__":
    # Process both CSV files
    files_to_process = [
        #"data/chase_2024_FY.CSV",
        #"data/chase_2025_YTD.CSV"
        #"data/Chase6410_2025.CSV",
        #"data/Chase2201.CSV",
        #"data/Chase5021.CSV",
        "data/Chase6559.CSV",
    ]
    
    for csv_file in files_to_process:
        print(f"\n{'='*60}")
        print(f"Processing: {csv_file}")
        print(f"{'='*60}\n")
        df = process_transactions(csv_file)
        
        # Show reclassified items
        reclassified = df[df['changed'] == True]
        if len(reclassified) > 0:
            print(f"\nReclassified transactions from {csv_file}:")
            print(reclassified[['description', 'bank_category', 'ai_category', 'reasoning']])