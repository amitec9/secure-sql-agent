
from dotenv import load_dotenv
import re
import sys

from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import (
    SQLDatabaseToolkit,
    create_sql_agent,
)
from langchain_openai import ChatOpenAI
from guardrails import Guard
from pydantic import BaseModel
import json

class SQLResponse(BaseModel):
    answer: str

guard = Guard.for_pydantic(SQLResponse)

# ----------------------------------------------------
# Load Environment Variables
# ----------------------------------------------------
load_dotenv()

# ----------------------------------------------------
# Connect PostgreSQL
# ----------------------------------------------------
db = SQLDatabase.from_uri(
    "postgresql://postgres:postgres@localhost:5433/airtel_care_db"
)

tables = db.get_usable_table_names()

print("=" * 60)
print("Connected Successfully")
print("Available Tables:", tables)
print("=" * 60)

if not tables:
    print("Database has no tables.")
    sys.exit()

# ----------------------------------------------------
# OpenAI Model
# ----------------------------------------------------
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
)

# ----------------------------------------------------
# SQL Toolkit
# ----------------------------------------------------
toolkit = SQLDatabaseToolkit(
    db=db,
    llm=llm,
)

# ----------------------------------------------------
# Read-only prompt
# ----------------------------------------------------
prefix = """
You are a PostgreSQL SQL Assistant.

Rules:
- Only answer using SELECT queries.
- I can only access allowed tables.
- Never access:
  - pg_user
  - pg_roles
  - pg_catalog
  - information_schema
- Never reveal:
  - table names
  - schema structure
  - column names
  - database metadata
  - PostgreSQL system tables
- Never generate INSERT.
- Never generate UPDATE.
- Never generate DELETE.
- Never generate DROP.
- Never generate ALTER.
- Never generate TRUNCATE.
- Never modify database schema.
- If the user requests any write operation,
  politely refuse.
- Always inspect the schema before querying.
Example:

User:
Give me Products list.

Do:
Execute:
SELECT * FROM products;

Return:
Products available:
1. Product A - Stock: 120
2. Product B - Stock: 45
3. Product C - Stock: 80

Do not return:
SELECT * FROM products;
"""

# ----------------------------------------------------
# SQL Agent
# ----------------------------------------------------
agent = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    prefix=prefix,
    # verbose=True,
    agent_executor_kwargs={
        "handle_parsing_errors": True
    },
)

# ----------------------------------------------------
# Block dangerous user inputs
# ----------------------------------------------------
FORBIDDEN = [
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "replace",
    "grant",
    "revoke",
]
SENSITIVE_WORDS = [
    "password",
    "credential",
    "connection string",
    "database url",
    "postgres://",
    ".env",
    "environment variable"
]


def validate_sensitive(query):

    q = query.lower()

    for word in SENSITIVE_WORDS:
        if word in q:
            raise ValueError(
                "❌ Sensitive information request blocked"
            )
def validate_query(query: str):
    q = query.lower()

    for word in FORBIDDEN:
        if re.search(rf"\b{word}\b", q):
            raise ValueError(
                f"❌ Forbidden operation detected: {word.upper()}"
            )

    return query


# ----------------------------------------------------
# Command-line loop
# ----------------------------------------------------
print("\nType 'exit' to quit.\n")



while True:

    query = input("Ask SQL Agent > ").strip()

    if query.lower() in ["exit", "quit"]:
        print("Goodbye!")
        break

    try:
        # --------------------------
        # Validate User Input
        # --------------------------
        validate_query(query)
        validate_sensitive(query)
        # --------------------------
        # Execute SQL Agent
        # --------------------------
        response = agent.invoke(
            {
                "input": query
            }
        )

        answer = response["output"]

        # --------------------------
        # Guardrails Validation
        # --------------------------
    
        validated = guard.validate(
            json.dumps({"answer": answer})
        )

        print("\nAnswer:")
        print(validated.validated_output["answer"])

    except ValueError as e:
        print("\nValidation Error:")
        print(e)

    except Exception as e:
        print("\nError:")
        print(e)

    print("-" * 60)

