# Personal Finance Analyst

An intelligent multi-bank transaction analysis system that standardizes CSV exports from different banks, uses AI to categorize and subcategorize transactions, and provides natural language querying capabilities.

## Getting Started

New users can test the system using the included mock data:

```bash
# 1. Setup environment
python3 -m venv myvenv
source myvenv/bin/activate
pip install -r requirements.txt

# 2. Configure API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 3. Try with mock data
python standardize_csv.py mock_data/1_raw_bank_exports/*.csv
python classify_by_merchant.py

# 4. Query with natural language (interactive web interface)
adk web
# Or run in CLI mode
adk run agent
```

The `mock_data/` folder contains synthetic transaction data to help you understand the workflow before using your own financial data.

## Features

- **Multi-Bank Support**: Automatically detects and processes CSVs from Chase (credit & checking), Citi, SFCU, and Bank of America
- **Standardized Schema**: Converts all bank formats into a unified schema
- **Merchant-Based AI Classification**: Uses Claude AI to categorize transactions by grouping unique merchants (100+ transactions per API call)
- **Hierarchical Categories**: 21 main categories with detailed subcategories (e.g., Transportation → Gas/Fuel, Rideshare, Parking, etc.)
- **Natural Language Queries (NL2SQL)**: Ask questions about your spending in plain English
- **Smart Refund Handling**: Returns are categorized with the original purchase category to prevent overstating expenses
- **Individual + Merged Outputs**: Saves both individual standardized CSVs and a merged file for analysis

## Workflow

### 1. Standardize Raw CSVs

Convert raw bank CSV files into a standardized format:

```bash
source myvenv/bin/activate
python standardize_csv.py data/1_raw_bank_exports/*.csv
```

**Output:**
- Individual standardized CSVs in `data/2_standardized/`
- Merged CSV at `data/2_standardized/transactions_merged.csv`

**Standardized Schema:**
```
date         - Transaction date (YYYY-MM-DD)
description  - Transaction description
amount       - Amount (negative for debits, positive for credits)
type         - Transaction type (Sale, Return, Credit, Debit, etc.)
category     - Original bank category
source       - Bank identifier (e.g., "Chase_6559")
month        - YYYY-MM format
year         - YYYY format
```

### 2. Classify Transactions with AI (Merchant-Based)

Use Claude AI to categorize transactions by grouping unique merchants:

```bash
python classify_by_merchant.py
```

**How it works:**
1. Groups all transactions by unique merchant/description
2. Sends batches of 50 unique merchants to Claude AI
3. AI categorizes each merchant with category + subcategory
4. Applies the categorization to all matching transactions

**Example:** All 43 "UBER *TRIP" transactions get categorized as Transportation → Rideshare in a single API call.

**Output:**
- `data/3_classified/classified_by_merchant_YYYYMMDD_HHMMSS.csv` - All transactions with AI categories and subcategories
- `data/3_classified/merchant_categories_YYYYMMDD_HHMMSS.csv` - Merchant-to-category mapping for reference

**Columns added:**
- `ai_category` - Main category (Income, Transportation, Dining, etc.)
- `ai_subcategory` - Detailed subcategory (Gas/Fuel, Rideshare, Coffee Shops, etc.)
- `confidence` - AI confidence level (high/medium/low)
- `reasoning` - Brief explanation of categorization

### 3. Query Your Data with Natural Language (NL2SQL)

Ask questions about your spending in plain English using the ADK agent:

```bash
# Launch interactive web interface
adk web

# Or use CLI mode
adk run agent
```

**Example queries:**
- "How much did I spend on dining in 2024?"
- "What are my top 5 expense categories?"
- "Show me all Uber transactions over $50"
- "Compare my gas spending between 2024 and 2025"
- "What's my monthly average for groceries?"

**How it works:**
1. Takes your natural language question
2. Uses Claude AI to convert it to a SQL query
3. **Validates the SQL is read-only** (blocks INSERT, UPDATE, DELETE, DROP, etc.)
4. Executes the safe query against your transaction data
5. Returns results in a readable format

**Security:** All generated SQL is validated to ensure read-only access. Any attempt to modify, delete, or drop data is automatically blocked.

### 4. Apply Manual Overrides (Optional)

Override specific transaction categories using pattern matching:

```bash
python recategorize.py
```

Reads from `data/config/category_overrides.csv` to apply manual corrections.

## Supported Banks

| Bank | Format | Adapter |
|------|--------|---------|
| Chase Credit Cards | Single amount column | `ChaseCreditAdapter` |
| Chase Checking | Details + Type columns | `ChaseCheckingAdapter` |
| Citi | Debit/Credit columns, metadata headers | `CitiAdapter` |
| SFCU | Debit/Credit columns | `SFCUAdapter` |
| Bank of America | Summary rows, single amount | `BofAAdapter` |

## Adding a New Bank

1. Create a new adapter class in [bank_adapters.py](bank_adapters.py):

```python
class NewBankAdapter(BankAdapter):
    def can_handle(self, df: pd.DataFrame, file_path: str) -> bool:
        # Check if CSV matches this bank's format
        expected_columns = {'Date', 'Description', 'Amount'}
        return expected_columns.issubset(set(df.columns))

    def parse(self, file_path: str) -> pd.DataFrame:
        # Parse bank-specific CSV
        df = pd.read_csv(file_path)

        standardized = pd.DataFrame({
            'date': pd.to_datetime(df['Date']),
            'description': df['Description'],
            'amount': df['Amount'],
            'type': 'Sale',  # or infer from data
            'category': df.get('Category', 'Uncategorized')
        })

        standardized = self._add_source(standardized)
        standardized = self._add_derived_fields(standardized)

        return standardized
```

2. Add the adapter to the detection list in `BankDetector.detect_and_parse()`:

```python
adapters = [
    CitiAdapter(source_id),
    BofAAdapter(source_id),
    NewBankAdapter(source_id),  # Add here
    # ...
]
```

## Files

### Core Scripts
- [bank_adapters.py](bank_adapters.py) - Bank-specific CSV adapters
- [standardize_csv.py](standardize_csv.py) - Main standardization script
- [classify_by_merchant.py](classify_by_merchant.py) - Merchant-based AI classification with subcategories
- [nl2sql.py](nl2sql.py) - Natural language to SQL query engine
- [recategorize.py](recategorize.py) - Manual category overrides (optional)

### Configuration
- [categories.json](categories.json) - Category and subcategory definitions for AI classification
- `data/config/category_overrides.csv` - Manual category overrides (optional)

### Data Folder Structure
See [data/README.md](data/README.md) for complete documentation. Quick overview:
- `data/1_raw_bank_exports/` - Raw CSV files from banks (input)
- `data/2_standardized/` - Standardized unified schema files
- `data/3_classified/` - AI-categorized transactions (current/active)
- `data/4_archives/` - Previous versions and legacy files
- `data/config/` - Configuration files

## Categories & Subcategories

The system supports 21 main categories with detailed subcategories:

### Main Categories
- **Income** - Salary, bonuses, reimbursements
- **Transfers** - Venmo, Zelle, bank-to-bank transfers
- **Bill Payments** - Credit card autopay, loan payments
- **Transportation** → Gas/Fuel, Rideshare, Parking, Car Insurance, Car Maintenance, Public Transit
- **Utilities** → Electricity/Gas (PG&E), Water/Sewer, Internet/Cable, Phone/Mobile, Garbage/Waste
- **Dining** → Restaurants, Fast Food/Casual, Coffee Shops/Cafes, Bakery/Desserts, Food Delivery, Bars/Nightlife
- **Groceries** → Supermarket, Specialty/Ethnic Groceries, Warehouse Club (Costco), Organic/Natural Foods
- **Shopping** → Electronics, Clothing/Apparel, Home/Furniture, Pharmacy/Personal Care, Online Shopping, Sporting Goods, Liquor/Wine
- **Healthcare** → Pharmacy, Doctor/Medical, Dental, Vision/Optometry, Hospital, Medical Supplies
- **Entertainment** → Movies/Theater, Museums/Attractions, Streaming Services, Sports/Activities, Parks/Recreation
- **Education** → Tuition/School Fees, School Supplies, Extracurricular Activities
- **Fitness** → Gym Membership, Sports Classes, Dance/Movement, Swimming, Recreation Programs
- **Software Subscriptions** → Productivity Software, Cloud Storage, Streaming (Video/Music), Professional Tools
- **Travel** → Airfare, Hotels/Lodging, Car Rental, Travel Activities
- Professional Services, Gifts, Donations, Investments, Refunds, Fees, Other

## Key Improvements

### Merchant-Based AI Classification (Latest)
Instead of classifying each transaction individually, groups transactions by merchant:
- **Processes 2,308 transactions across 1,016 unique merchants in just 21 API calls**
- **~110 transactions categorized per API call** (vs. 50 with batch classification)
- All 43 Uber transactions categorized as "Transportation → Rideshare" in one go
- Consistent categorization across identical merchants

### Hierarchical Subcategories
Provides granular spending insights:
- Transportation: See breakdown of Gas ($3,532) vs Rideshare ($2,726) vs Parking ($249)
- Dining: Restaurants ($5,424) vs Coffee Shops ($1,428) vs Food Delivery ($834)
- Shopping: Online Shopping ($11,777) is 66% of all shopping spend

### Smart Refund Handling
Returns and refunds are categorized with the original merchant category:
- Amazon returns → Shopping (not Refunds)
- This prevents overstating expenses by keeping net spending accurate

### Natural Language Queries (NL2SQL)
Ask questions in plain English:
- "How much did I spend on coffee shops in 2025?"
- "What's my average monthly Uber spending?"
- AI converts natural language to SQL and executes against your data

### Multi-Bank Standardization
Supports 5 different bank formats with automatic detection:
- Auto-detects bank type from CSV headers
- Handles edge cases (trailing commas, metadata rows, debit/credit columns)
- Outputs both individual and merged standardized CSVs

## Example Use Cases

### Detailed Spending Analysis
With subcategories, you can answer questions like:
- "Am I spending more on gas or rideshare?"
- "What percentage of my dining budget goes to food delivery vs restaurants?"
- "How much do I spend on coffee per month?"

### Budget Optimization
Identify optimization opportunities:
- High rideshare costs → Consider alternatives
- Excessive food delivery → Cook more or meal prep
- Online shopping dominance → Evaluate subscription services

### Tax Preparation
Easily filter by category for tax purposes:
- Professional Services for business expenses
- Healthcare for medical deductions
- Education for tuition credits
- Donations for charitable deductions

### Natural Language Insights
Ask complex questions without writing SQL:
- "Show me my top 10 merchants by total spend"
- "Compare my grocery spending between 2024 and 2025"
- "How much did I spend on transportation each month in 2025?"

## Statistics

**Current Dataset (2023 onwards):**
- Total transactions: 2,308
- Unique merchants: 1,016
- Date range: 2023-01-04 to 2025-12-17
- AI Classification: 21 API calls (50 merchants per call)
- Categories: 21 main categories with subcategories for 11 of them

## Quick Reference

### Setup
```bash
# Create virtual environment
python3 -m venv myvenv
source myvenv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
export ANTHROPIC_API_KEY='your-api-key'

# Optional: Set custom database path (for encrypted folder)
export FINANCE_DB_PATH='/path/to/encrypted/folder/classified_transactions.csv'

# Or create .env file with:
# ANTHROPIC_API_KEY=your-api-key
# FINANCE_DB_PATH=/path/to/encrypted/folder/classified_transactions.csv
```

### Complete Workflow
```bash
# 1. Place raw bank CSVs in data/1_raw_bank_exports/

# 2. Standardize raw bank CSVs
python standardize_csv.py data/1_raw_bank_exports/*.csv

# 3. Classify with AI (merchant-based)
python classify_by_merchant.py

# 4. Query your data with natural language
adk web
# Or: adk run agent
# Then ask: "How much did I spend on dining in 2025?"
```

### Output Schema
The final classified CSV contains:
```
date              - Transaction date (YYYY-MM-DD)
description       - Merchant/transaction description
amount            - Amount (negative = expense, positive = income)
type              - Transaction type (Sale, Credit, Debit, etc.)
bank_category     - Original bank category
ai_category       - AI-assigned main category
ai_subcategory    - AI-assigned subcategory (if applicable)
confidence        - AI confidence level (high/medium/low)
reasoning         - Brief explanation of categorization
source            - Bank identifier
month             - YYYY-MM format
year              - YYYY format
```

## Security & Privacy

### Storing Sensitive Data
Your financial data should be kept secure. We recommend:

1. **Use an encrypted folder** for your classified transaction files
2. **Set the `FINANCE_DB_PATH` environment variable** to point to this encrypted location
3. **Add `.env` to `.gitignore`** to prevent accidentally committing API keys or file paths

Example setup with encrypted folder:
```bash
# In your .env file (never commit this!)
ANTHROPIC_API_KEY=your-api-key-here
FINANCE_DB_PATH=/Users/yourusername/EncryptedFolder/classified_transactions.csv
```

### What Gets Sent to the API
- **Classification**: Merchant names, transaction amounts, and types are sent to Claude AI for categorization
- **NL2SQL**: Your natural language query and the database schema (column names) are sent to generate SQL
- **Not sent**: Your actual transaction data stays local during NL2SQL queries

### SQL Security (NL2SQL)
The NL2SQL feature enforces read-only database access:
- ✅ **Allowed**: SELECT queries, WITH clauses (CTEs)
- ❌ **Blocked**: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, COPY, ATTACH, PRAGMA
- All AI-generated SQL is validated before execution
- Attempts to modify data are automatically rejected with a clear error message

### Gitignore
Make sure these are in your `.gitignore`:
```
.env
data/*.csv
*.http
myvenv/
```

## Contributing

To add support for a new bank or improve categorization:
1. For new banks: Add adapter to [bank_adapters.py](bank_adapters.py)
2. For new categories: Update [categories.json](categories.json)
3. Submit a pull request with examples

## License

MIT
