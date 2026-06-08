import os
from pathlib import Path

from dotenv import load_dotenv

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent

load_dotenv(PROJECT_ROOT / ".env")

from langchain_openai import ChatOpenAI
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit

DB_FILE = PROJECT_ROOT / "data" / "database" / "operational_twin.db"


def get_openai_api_key() -> str:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise ValueError(
            "OPENAI_API_KEY is not set. Add it to .env in the project root "
            "(get a key at https://platform.openai.com/api-keys)."
        )
    # Strip surrounding quotes if they exist in the env variable
    key = key.strip("'\"")
    if not key.startswith("sk-"):
        raise ValueError(
            "OPENAI_API_KEY in .env is not a valid OpenAI API key. "
            "Create one at https://platform.openai.com/api-keys — keys start with 'sk-'."
        )
    return key


# --- 2. Setup the OpenAI LLM ---
# We use gpt-4o-mini for speed, which is perfect for real-time dashboard chats
llm = ChatOpenAI(
    model="gpt-4o-mini",
    openai_api_key=get_openai_api_key(),
    temperature=0,  # Temperature 0 ensures deterministic, factual answers (no hallucinations)
)

# --- 3. Connect LangChain to DuckDB ---
# LangChain uses SQLAlchemy formatting for the database connection string
db_uri = f"duckdb:///{DB_FILE}"
db = SQLDatabase.from_uri(
    db_uri,
    engine_args={"connect_args": {"read_only": True}}
)

# --- 4. Define the AI Persona & Constraints ---
system_prefix = """
You are the AI Operational Twin for Ekak Innovations, an industrial recycling facility.
Your job is to analyze machinery telemetry and calculate financial waste in Indian Rupees (INR).

CRITICAL RULES:
1. You have access to a DuckDB database. You MUST query the 'gold_operational_metrics' table to answer questions.
2. NEVER guess or estimate financial numbers. Only report the exact math calculated in the database.
3. The power baseline is 300kW. Anything above that is a 'CRITICAL_POWER_WASTE' anomaly.
4. Always format financial outputs clearly with the ₹ symbol.
"""

# --- 5. Build the Agent ---
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

agent_executor = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    verbose=True, # Set to True so you can watch OpenAI write the SQL in your terminal
    prefix=system_prefix,
    agent_type="openai-tools" # Standardized format for tool calling
)

def ask_operational_twin(question: str) -> str:
    """Wrapper function to send a query to the agent."""
    try:
        response = agent_executor.invoke({"input": question})
        return response["output"]
    except Exception as e:
        err = str(e)
        if "API_KEY_INVALID" in err or "API key not valid" in err or "Incorrect API key" in err or "invalid_api_key" in err:
            return (
                "Error: OpenAI rejected the API key in .env. "
                "Create a new key at https://platform.openai.com/api-keys and update OPENAI_API_KEY."
            )
        return f"An error occurred: {err}"

# --- 6. Terminal Testing ---
if __name__ == "__main__":
    print("AI Engine is online.")
    print("Type 'exit' to quit.\n")
    
    while True:
        user_input = input("Ask a question: ")
        if user_input.lower() in ['exit', 'quit']:
            break
            
        print("\nThinking...")
        answer = ask_operational_twin(user_input)
        print(f"\nResponse:\n{answer}\n")
        print("-" * 50)