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

def classify_merchants_batch(merchants_batch):
    """Send batch of unique merchants to Claude for classification"""

    # Format merchants for the prompt
    merchants_list = []
    for idx, merchant_info in enumerate(merchants_batch):
        merchants_list.append({
            "id": idx,
            "merchant": merchant_info['description'],
            "transaction_count": merchant_info['count'],
            "avg_amount": round(merchant_info['avg_amount'], 2),
            "total_amount": round(merchant_info['total_amount'], 2),
            "transaction_type": merchant_info['transaction_type']
        })

    # Build subcategory information for prompt
    subcategory_info = ""
    if 'subcategories' in category_config:
        subcategory_info = "\n\nAvailable Subcategories:\n"
        for cat, subcats in category_config['subcategories'].items():
            subcategory_info += f"{cat}: {', '.join(subcats)}\n"

        if 'subcategory_examples' in category_config:
            subcategory_info += "\nSubcategory Examples:\n"
            subcategory_info += json.dumps(category_config['subcategory_examples'], indent=2)

    prompt = f"""Review these unique merchants/descriptions and categorize them appropriately.

Available Categories: {', '.join(category_config['categories'])}

Category Examples:
{json.dumps(category_config['examples'], indent=2)}
{subcategory_info}

Unique merchants to classify (with transaction count, amounts, and transaction type):
{json.dumps(merchants_list, indent=2)}

IMPORTANT CATEGORIZATION RULES:
1. Transaction Type matters:
   - "Credit" type = likely Income, Transfers, or Refunds
   - "Debit" type = likely expenses (Shopping, Groceries, etc.)
   - "ACH_CREDIT" = usually Income or Transfers
   - "ACH_DEBIT" = usually Bill Payments or Transfers

2. Pattern matching:
   - "PAYROLL" or "salary" = Income (not Other!)
   - "Venmo", "Zelle", "transfer", "external" = Transfers
   - "AUTOPAY", "credit card payment" = Bill Payments
   - Merchant names (e.g., "Uber" = Transportation, "Safeway" = Groceries)

3. Refunds/Returns - IMPORTANT:
   - Returns from merchants should be categorized as the ORIGINAL CATEGORY, not "Refunds"
   - Example: Amazon return = Shopping (not Refunds), Safeway return = Groceries (not Refunds)
   - This prevents overstating expenses in the original category
   - Only use "Refunds" for generic credits that aren't tied to a specific merchant/category

4. Context clues:
   - Positive amounts with Credit type = likely Income
   - Large recurring payments to schools = Education
   - Gas stations, parking = Transportation
   - PG&E, AT&T = Utilities

Respond with a JSON array where each object has:
{{
    "id": merchant_id,
    "category": "category name",
    "subcategory": "subcategory name (if applicable, otherwise null)",
    "confidence": "high/medium/low",
    "reasoning": "brief explanation"
}}

IMPORTANT: If the category has subcategories defined, you MUST provide a subcategory.
For example: Transportation must have subcategory (Gas/Fuel, Rideshare, Parking, etc.)
If no subcategory applies or category has no subcategories, use null.

Return ONLY the JSON array, no other text."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    # Parse response
    response_text = message.content[0].text
    # Extract JSON from response (handling markdown code blocks)
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError as e:
        # Save problematic response for debugging
        print(f"JSON parsing error: {e}")
        print(f"Response (first 500 chars): {response_text[:500]}")
        raise

def process_transactions_by_merchant(csv_path, batch_size=50):
    """Process transactions by grouping unique merchants"""

    # Read CSV
    df = pd.read_csv(csv_path)

    print(f"Total transactions: {len(df)}")

    # Group by description to get unique merchants
    merchant_stats = df.groupby('description').agg({
        'amount': ['count', 'mean', 'sum'],
        'category': 'first',  # Keep original bank category
        'type': 'first'  # Keep transaction type (Credit/Debit/etc)
    }).reset_index()

    merchant_stats.columns = ['description', 'count', 'avg_amount', 'total_amount', 'bank_category', 'transaction_type']

    # Sort by transaction count (most frequent first)
    merchant_stats = merchant_stats.sort_values('count', ascending=False)

    print(f"Unique merchants/descriptions: {len(merchant_stats)}")
    print(f"\nTop 10 most frequent merchants:")
    print(merchant_stats.head(10)[['description', 'count', 'avg_amount']])

    # Process merchants in batches
    merchant_categories = {}
    total_merchants = len(merchant_stats)
    num_batches = (total_merchants + batch_size - 1) // batch_size

    print(f"\nProcessing {total_merchants} unique merchants in {num_batches} batches of {batch_size}...")

    for batch_num in range(num_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, total_merchants)

        print(f"\nBatch {batch_num + 1}/{num_batches}: Processing merchants {start_idx + 1}-{end_idx}...")

        # Get batch of merchants
        batch_merchants = merchant_stats.iloc[start_idx:end_idx].to_dict('records')

        try:
            # Classify entire batch
            classifications = classify_merchants_batch(batch_merchants)

            # Store results
            for merchant_info, classification in zip(batch_merchants, classifications):
                merchant_categories[merchant_info['description']] = {
                    'ai_category': classification['category'],
                    'ai_subcategory': classification.get('subcategory'),
                    'confidence': classification['confidence'],
                    'reasoning': classification.get('reasoning', ''),
                    'transaction_count': merchant_info['count']
                }

            print(f"✓ Batch {batch_num + 1} completed ({len(classifications)} merchants)")

        except Exception as e:
            print(f"✗ Error processing batch {batch_num + 1}: {e}")

            # Add all merchants in failed batch as errors
            for merchant_info in batch_merchants:
                merchant_categories[merchant_info['description']] = {
                    'ai_category': 'ERROR',
                    'ai_subcategory': None,
                    'confidence': 'low',
                    'reasoning': str(e),
                    'transaction_count': merchant_info['count']
                }

    # Apply merchant categories to all transactions
    print("\nApplying categories to all transactions...")

    results = []
    for _, row in df.iterrows():
        merchant = row['description']
        merchant_cat = merchant_categories.get(merchant, {
            'ai_category': 'ERROR',
            'ai_subcategory': None,
            'confidence': 'low',
            'reasoning': 'Merchant not found',
            'transaction_count': 0
        })

        results.append({
            'date': row['date'],
            'description': row['description'],
            'amount': row['amount'],
            'type': row['type'],
            'bank_category': row['category'],
            'ai_category': merchant_cat['ai_category'],
            'ai_subcategory': merchant_cat['ai_subcategory'],
            'confidence': merchant_cat['confidence'],
            'reasoning': merchant_cat['reasoning'],
            'source': row['source'],
            'month': row['month'],
            'year': row['year']
        })

    # Save results
    output_df = pd.DataFrame(results)
    os.makedirs('data/3_classified', exist_ok=True)
    output_filename = f"data/3_classified/classified_by_merchant_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output_df.to_csv(output_filename, index=False)

    # Also save merchant mapping for reference
    merchant_mapping_df = pd.DataFrame([
        {
            'merchant': merchant,
            'category': info['ai_category'],
            'subcategory': info['ai_subcategory'],
            'confidence': info['confidence'],
            'reasoning': info['reasoning'],
            'transaction_count': info['transaction_count']
        }
        for merchant, info in merchant_categories.items()
    ]).sort_values('transaction_count', ascending=False)

    mapping_filename = f"data/3_classified/merchant_categories_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    merchant_mapping_df.to_csv(mapping_filename, index=False)

    print("\n" + "=" * 80)
    print("CLASSIFICATION COMPLETE")
    print("=" * 80)
    print(f"\nResults saved to: {output_filename}")
    print(f"Merchant mapping saved to: {mapping_filename}")
    print(f"\nTotal transactions: {len(results)}")
    print(f"Unique merchants classified: {len(merchant_categories)}")
    print(f"API calls made: {num_batches} (batch size: {batch_size})")
    print(f"Average merchants per batch: {len(merchant_categories) / num_batches:.1f}")
    print(f"Transactions per API call: {len(results) / num_batches:.1f}")

    # Show category distribution
    print("\nCategory distribution:")
    category_dist = output_df['ai_category'].value_counts()
    for category, count in category_dist.items():
        print(f"  {category}: {count} transactions")

    # Show errors if any
    errors = output_df[output_df['ai_category'] == 'ERROR']
    if len(errors) > 0:
        print(f"\nErrors: {len(errors)} transactions")

    return output_df, merchant_mapping_df

if __name__ == "__main__":
    # Process the merged transactions file
    csv_file = "data/2_standardized/transactions_merged.csv"

    print(f"\n{'='*80}")
    print(f"Processing: {csv_file}")
    print(f"{'='*80}\n")

    transactions_df, merchants_df = process_transactions_by_merchant(csv_file, batch_size=50)

    print("\n" + "=" * 80)
    print("Top 20 merchants by transaction count:")
    print("=" * 80)
    print(merchants_df.head(20)[['merchant', 'category', 'subcategory', 'confidence', 'transaction_count']])
