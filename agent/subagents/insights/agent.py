from google.adk.agents import LlmAgent
from . import prompts

response_agent = LlmAgent(
    name="response_agent",
    model="gemini-2.0-flash",
    description=(
        "Responds to the user's question in natural language using data context provided to you"
    ),
    instruction= prompts.response_system_instruction_v0,
    output_key = "response"
)