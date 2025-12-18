import pandas as pd


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

# Usage:
#schema = extract_schema_from_dataframe(my_df)
#print(schema)