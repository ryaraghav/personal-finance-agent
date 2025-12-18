import pandas as pd
import os
import duckdb

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
# In tools.py
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
csv_path = os.path.join(project_root, 'data', 'transactions_2024_2025.csv')
my_df = pd.read_csv(csv_path)

con = duckdb.connect(database=':memory:')

con.register('my_df', my_df)

def execute_sql_tool(sql_query: str) -> str:
    """
    Executes a SQL query against the DuckDB instance and returns the results
    as a Markdown-formatted table string (or a simple text string if it's one number).
    """
    try:
        # 1. Run the query
        df = con.sql(sql_query).df()
        
        # 2. Check if empty
        if df.empty:
            return "Query executed successfully but returned no data."
            
        # 3. Format as string so the LLM can read it
        # Converting to Markdown allows the LLM to understand columns vs rows
        return df.to_markdown(index=False)
        
    except Exception as e:
        # Return the error so the Agent knows it failed and can try to fix the SQL
        return f"SQL Error: {str(e)}"

# Usage:
#schema = extract_schema_from_dataframe(my_df)
#print(schema)