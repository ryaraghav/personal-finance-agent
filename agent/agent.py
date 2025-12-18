import os, glob
import duckdb
import pandas as pd
from dotenv import load_dotenv
from google.adk.agents import Agent, SequentialAgent, LlmAgent
from google.adk import Runner
from .subagents.nl2sql.agent import nl2sql_agent
from .subagents.insights.agent import response_agent
from . import prompts
from . import tools

# Load Google AI API key (required for Google ADK)
load_dotenv()
api_key = os.environ.get("GOOGLE_API_KEY") 

financial_advisor_agent = SequentialAgent(
    name="FinancialAdvisorAgent",
    sub_agents=[nl2sql_agent],
    description="Executes a sequence of natural language to SQL query.",
)

# For ADK tools compatibility, the root agent must be named `root_agent`
root_agent = financial_advisor_agent

if __name__ == "__main__":
    runner = Runner(root_agent)
    result = runner.run("What was my total spending in January 2025?")
    print(result)