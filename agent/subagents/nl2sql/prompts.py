import os
import yaml

# =============================================================================
# YAML CONFIG LOADERS
# =============================================================================

def _get_config_path(filename: str) -> str:
    """Get the path to a config file in agent/config/"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    agent_dir = os.path.dirname(os.path.dirname(current_dir))
    return os.path.join(agent_dir, 'config', filename)


def load_semantic_layer() -> dict:
    """Load the semantic layer configuration."""
    config_path = _get_config_path('semantic_layer.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def load_sql_examples() -> dict:
    """Load the SQL examples configuration."""
    config_path = _get_config_path('sql_examples.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def format_semantic_layer(semantic_layer: dict) -> str:
    """Format semantic layer into a readable string for the prompt."""
    lines = []

    # Table name
    lines.append(f"Table: {semantic_layer.get('table_name', 'my_df')}")
    lines.append("")

    # Fields
    lines.append("## Fields")
    for field_name, field_info in semantic_layer.get('fields', {}).items():
        lines.append(f"\n### {field_name}")
        lines.append(f"- Type: {field_info.get('type', 'unknown')}")
        if 'format' in field_info:
            lines.append(f"- Format: {field_info['format']}")
        lines.append(f"- Description: {field_info.get('description', '')}")

        # Valid values
        if 'valid_values' in field_info:
            if isinstance(field_info['valid_values'], list):
                if isinstance(field_info['valid_values'][0], dict):
                    # Format: [{value: X, meaning: Y}, ...]
                    vals = [f"{v['value']} ({v['meaning']})" for v in field_info['valid_values']]
                    lines.append(f"- Valid values: {', '.join(vals)}")
                else:
                    lines.append(f"- Valid values: {', '.join(field_info['valid_values'])}")

        # Valid values by category (for subcategories)
        if 'valid_values_by_category' in field_info:
            lines.append("- Valid values by category:")
            for cat, subcats in field_info['valid_values_by_category'].items():
                lines.append(f"  - {cat}: {', '.join(subcats)}")

        # Business rules
        if 'business_rules' in field_info:
            lines.append("- Business rules:")
            for rule in field_info['business_rules']:
                lines.append(f"  - {rule}")

        # Tips
        if 'tips' in field_info:
            lines.append("- Tips:")
            for tip in field_info['tips']:
                lines.append(f"  - {tip}")

    # Business rules section
    if 'business_rules' in semantic_layer:
        lines.append("\n## Important Business Rules")
        for rule_info in semantic_layer['business_rules']:
            lines.append(f"- {rule_info['rule']}: {rule_info['implication']}")

    # Query patterns
    if 'query_patterns' in semantic_layer:
        lines.append("\n## Common Query Patterns")
        for pattern_name, pattern_sql in semantic_layer['query_patterns'].items():
            lines.append(f"- {pattern_name}: `{pattern_sql}`")

    return "\n".join(lines)


def format_sql_examples(sql_examples: dict, limit: int = 10) -> str:
    """Format SQL examples into a readable string for the prompt."""
    lines = ["## SQL Examples", ""]

    examples = sql_examples.get('examples', [])[:limit]

    for i, example in enumerate(examples, 1):
        lines.append(f"### Example {i}: {example['question']}")
        lines.append("```sql")
        lines.append(example['sql'].strip())
        lines.append("```")
        lines.append(f"Explanation: {example['explanation']}")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

nl2sql_system_instruction_v0 = """
    You are a SQL expert. 
    You are given a natural language question and a database schema. 
    You need to generate a SQL query to answer the question.
    
    Guidelines:
    - Use the full table name in the SQL query.
    - Only use the columns that are in the schema.
    - The maximum number of rows to return should be less than {MAX_ROWS}.
    - Always compute ratios using aggregated totals (e.g., SUM() with GROUP BY on the relevant dimension such as author, platform, or category) instead of row-level values.

    The natural language question will be provided by the user.
    The database schema is: {schema}
    
    Think step by step and generate the SQL query.

    Return ONLY valid SQL. No prose, no comments.
"""

nl2sql_system_instruction_v1 = """
You are a financial analyst assistant with SQL expertise and access to transaction data.

When the user asks a question:
1. Understand the question and identify what data is needed
2. Generate a SQL query following the guidelines below
3. Use the execute_sql_tool to run the query
4. Interpret the results and respond in natural, conversational language

Database schema: {schema}

SQL Query Guidelines:
- Use the full table name 'my_df' in queries
- Only use columns that are in the schema
- Limit results to {MAX_ROWS} rows unless user asks for more
- Always compute ratios using aggregated totals (e.g., SUM() with GROUP BY on the relevant dimension such as category, month, or year) instead of row-level values
- Think step by step before generating the query

Response Guidelines:
- Format currency values with $ symbol and commas (e.g., $1,234.56)
- Be concise and helpful
- If results are empty, explain that no data was found
- Highlight key insights from the data

Example:
User: "What was my total spend in 2025?"
You: *Generate SQL: SELECT SUM(amount) FROM my_df WHERE year = 2025*
You: *Use execute_sql_tool*
You: "Your total spend in 2025 was $45,678.90"
"""


def get_nl2sql_instruction_v2(max_rows: int = 10) -> str:
    """
    Generate the v2 system instruction with semantic layer and SQL examples.

    This version:
    - Uses the semantic layer for field descriptions and business rules
    - Includes curated SQL examples for few-shot learning
    - Auto-executes SQL using execute_sql_tool
    """
    # Load configurations
    semantic_layer = load_semantic_layer()
    sql_examples = load_sql_examples()

    # Format into readable strings
    semantic_str = format_semantic_layer(semantic_layer)
    examples_str = format_sql_examples(sql_examples, limit=5)

    instruction = f"""You are a financial analyst assistant with SQL expertise and access to transaction data.

IMPORTANT: You MUST use the execute_sql_tool function to run queries. Do NOT just return SQL text - always call the tool.

When the user asks a question:
1. Understand the question and identify what data is needed
2. Generate a SQL query following the schema and guidelines below
3. ALWAYS call execute_sql_tool(sql_query="YOUR SQL HERE") to run the query
4. Interpret the results and respond in natural, conversational language

# Database Schema & Field Descriptions

{semantic_str}

# SQL Query Guidelines

- Use the table name 'my_df' in all queries
- Only use fields documented in the schema above
- Limit results to {max_rows} rows unless user asks for more
- Generate ONLY read-only SELECT queries (no INSERT, UPDATE, DELETE, etc.)

# Response Guidelines

- Format currency values with $ symbol and commas (e.g., $1,234.56)
- Be concise and helpful
- If results are empty, explain that no data was found
- Highlight key insights from the data

{examples_str}

CRITICAL: Never output raw SQL to the user. Always call execute_sql_tool to run the query and return the analyzed results."""

    return instruction