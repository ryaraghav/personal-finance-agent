import os, glob
import duckdb
import pandas as pd
from dotenv import load_dotenv
from google.adk.agents import Agent, LlmAgent
from google.adk import Runner
from . import prompts
from . import tools

# Get database path from environment variable or find latest classified file
load_dotenv()
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
    classified_files = glob.glob(os.path.join(classified_dir, 'classified_by_merchant_*.csv'))

    if not classified_files:
        raise FileNotFoundError(
            f"No classified transaction files found in {classified_dir}\n"
            f"Please run classify_by_merchant.py first to generate classified transactions,\n"
            f"or set FINANCE_DB_PATH environment variable to point to your classified transactions CSV"
        )

    # Use the most recent file (sorted by filename, which includes timestamp)
    csv_path = sorted(classified_files)[-1]

print(f"Loading transaction data from: {csv_path}")
my_df = pd.read_csv(csv_path)

# Load Google AI API key (required for Google ADK)
api_key = os.environ.get("GOOGLE_API_KEY")

#Extract schema from DataFrame
schema = tools.extract_schema_from_dataframe(my_df)

# v1 Agent - basic prompt (kept for backward compatibility)
nl2sql_agent_v1 = LlmAgent(
    name="sql_agent_v1",
    model="gemini-2.0-flash",
    description=(
        "Answers financial questions by querying transaction data (basic prompt)"
    ),
    instruction=prompts.nl2sql_system_instruction_v1.format(schema=schema, MAX_ROWS=10),
    tools=[tools.execute_sql_tool],
    output_key="generated_sql_query"
)

# v2 Agent - uses semantic layer and SQL examples from YAML configs
nl2sql_agent = LlmAgent(
    name="sql_agent",
    model="gemini-2.0-flash",
    description=(
        "Answers financial questions by querying transaction data with semantic layer"
    ),
    instruction=prompts.get_nl2sql_instruction_v2(max_rows=10),
    tools=[tools.execute_sql_tool],
    output_key="generated_sql_query"
)