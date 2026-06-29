from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from config import (
    ANTHROPIC_API_KEY,
    SYSTEM_PROMPT_1,
    SYSTEM_PROMPT_2,
)

checkpointer = InMemorySaver()

agent = create_agent(
    model="claude-haiku-4-5-20251001",
    checkpointer=checkpointer,
    system_prompt=SYSTEM_PROMPT_1,
)


# One thread per match. Reset this when a new match starts.
MATCH_THREAD_ID = "match-current"

def get_config():
    return {"configurable": {"thread_id": MATCH_THREAD_ID}}

def reset_match():
    """Call this on MatchInitialized to start a fresh memory thread."""
    global MATCH_THREAD_ID
    import uuid
    MATCH_THREAD_ID = f"match-{uuid.uuid4()}"


# result = agent.invoke(
#     {"messages": [{"role": "user", "content": "What's the weather in San Francisco?"}]}
# )
# print(result["messages"][-1].content_blocks)