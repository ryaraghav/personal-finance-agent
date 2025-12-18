import os, glob
import duckdb
import pandas as pd
from dotenv import load_dotenv
from google.adk.agents import Agent, LlmAgent
from google.adk import Runner
from . import prompts
from . import tools

# Get directory where this file lives
current_dir = os.path.dirname(os.path.abspath(__file__))
# Go up 3 levels to project root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
csv_path = os.path.join(project_root, 'data', 'transactions_2024_2025.csv')

my_df = pd.read_csv(csv_path)

# Load Google AI API key (required for Google ADK)
load_dotenv()
api_key = os.environ.get("GOOGLE_API_KEY") 

#Download data from CSV file and store in DataFrame
#my_df = pd.read_csv('data/transactions_2024_2025.csv')
my_df = pd.read_csv(csv_path)

#Extract schema from DataFrame
schema = tools.extract_schema_from_dataframe(my_df)

# Agent generated SQL query
nl2sql_agent = LlmAgent(
    name="sql_agent",
    model="gemini-2.0-flash",
    description=(
        "Answers financial questions by querying transaction data"
    ),
    instruction= prompts.nl2sql_system_instruction_v1.format(schema=schema, MAX_ROWS=10),
    tools=[tools.execute_sql_tool],
    output_key = "generated_sql_query"
)