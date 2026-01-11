import pandas as pd
import os
import duckdb
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def extract_schema_from_dataframe(df, table_name="my_df"):
    """
    Extract SQL schema from a pandas DataFrame.

    Args:
        df: pandas.DataFrame - The dataframe to extract schema from
        table_name: str - Name for the table in the schema (default: "my_df")

    Returns:
        str - SQL CREATE TABLE statement
    """
    schema_parts = [f"CREATE TABLE {table_name} ("]

    for col in df.columns:
        dtype = df[col].dtype

        # Map pandas dtypes to SQL types
        if dtype == 'object':
            sql_type = "VARCHAR"
        elif dtype in ['int64', 'int32']:
            sql_type = "INTEGER"
        elif dtype in ['float64', 'float32']:
            sql_type = "FLOAT"
        elif dtype == 'bool':
            sql_type = "BOOLEAN"
        elif 'datetime' in str(dtype):
            sql_type = "TIMESTAMP"
        else:
            sql_type = "VARCHAR"  # fallback

        schema_parts.append(f"    {col} {sql_type},")

    # Remove last comma and close
    schema_parts[-1] = schema_parts[-1].rstrip(',')
    schema_parts.append(")")

    return "\n".join(schema_parts)

# Get database path from environment variable
# Default to project data folder if not set
db_path = os.environ.get('FINANCE_DB_PATH')

if db_path:
    # User specified a custom path (e.g., in encrypted folder)
    csv_path = db_path
else:
    # Fallback to default project location - find latest classified file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    classified_dir = os.path.join(project_root, 'data', '3_classified')

    # Find the most recent classified_by_merchant file
    import glob
    classified_files = glob.glob(os.path.join(classified_dir, 'classified_by_merchant_*.csv'))

    if not classified_files:
        raise FileNotFoundError(
            f"No classified transaction files found in {classified_dir}\n"
            f"Please run classify_by_merchant.py first to generate classified transactions,\n"
            f"or set FINANCE_DB_PATH environment variable to point to your classified transactions CSV"
        )

    # Use the most recent file (sorted by filename, which includes timestamp)
    csv_path = sorted(classified_files)[-1]

# Validate file exists
if not os.path.exists(csv_path):
    raise FileNotFoundError(
        f"Transaction data file not found at: {csv_path}\n"
        f"Please set FINANCE_DB_PATH environment variable to point to your classified transactions CSV,\n"
        f"or run classify_by_merchant.py to generate classified transactions"
    )

# Load data
my_df = pd.read_csv(csv_path)

con = duckdb.connect(database=':memory:')

con.register('my_df', my_df)

# SQL Safety: Forbidden keywords to prevent data modification
FORBIDDEN_SQL_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
    "CREATE", "TRUNCATE", "COPY", "ATTACH", "DETACH",
    "PRAGMA", "VACUUM", "GRANT", "REVOKE"
)

def is_safe_sql(sql: str) -> bool:
    """
    Validate that SQL query is read-only and safe to execute.

    Args:
        sql: SQL query string to validate

    Returns:
        bool: True if query is safe (SELECT only), False otherwise
    """
    sql_upper = sql.upper().strip()

    # Must start with SELECT or WITH (for CTEs)
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        return False

    # Must not contain any forbidden keywords
    if any(keyword in sql_upper for keyword in FORBIDDEN_SQL_KEYWORDS):
        return False

    return True

def execute_sql_tool(sql_query: str) -> str:
    """
    Executes a read-only SQL query against the DuckDB instance and returns the results
    as a Markdown-formatted table string (or a simple text string if it's one number).

    SECURITY: Only SELECT queries are allowed. Any attempt to modify data will be rejected.
    """
    try:
        # 1. Validate SQL safety
        sql_clean = sql_query.strip()

        if not is_safe_sql(sql_clean):
            return (
                "❌ UNSAFE SQL DETECTED: Only SELECT queries are allowed. "
                "The query cannot contain INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, or other data-modifying operations. "
                "This is a read-only database for financial analysis."
            )

        # 2. Execute the safe query
        df = con.sql(sql_clean).df()

        # 3. Check if empty
        if df.empty:
            return "Query executed successfully but returned no data."

        # 4. Format as string so the LLM can read it
        # Converting to Markdown allows the LLM to understand columns vs rows
        return df.to_markdown(index=False)

    except Exception as e:
        # Return the error so the Agent knows it failed and can try to fix the SQL
        return f"SQL Error: {str(e)}"

# Usage:
#schema = extract_schema_from_dataframe(my_df)
#print(schema)