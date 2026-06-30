from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt, ModelRequest
from langgraph.checkpoint.memory import InMemorySaver

from config import (
    ANTHROPIC_API_KEY,
    SYSTEM_PROMPT_1,
    SYSTEM_PROMPT_2,
)

checkpointer = InMemorySaver()

 
@dataclass
class AnnouncerContext:
    # Per-invocation context: which announcer is speaking.
    announcer: int = 1
 
 
@dynamic_prompt
def select_announcer_prompt(request: ModelRequest) -> str:
    if request.runtime.context.announcer == 2:
        return SYSTEM_PROMPT_2
    return SYSTEM_PROMPT_1
 
 
agent = create_agent(
    model="claude-haiku-4-5-20251001",
    checkpointer=checkpointer,
    middleware=[select_announcer_prompt],
    context_schema=AnnouncerContext,
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