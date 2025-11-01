# dining/agent_graph.py
import re
from typing import List, Optional, TypedDict, Literal
from decimal import Decimal
from django.db.models import Q
from django.contrib.auth.models import AnonymousUser

from .models import MenuItem, Cart, CartItem, Tag
from .views import get_guest_token

# --- LangChain/LangGraph ---
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI   # pip install langchain-openai
from langgraph.graph import StateGraph, END

# Set your model env var: OPENAI_API_KEY
LLM_MODEL = "gpt-4o-mini"  # or "gpt-4o" / any chat model you have

# State the graph carries
class AgentState(TypedDict):
    messages: List[dict]           # [{"role":"user"/"assistant"/"tool","content":str}]
    actions_done: List[str]
    cart_summary: Optional[dict]

# ---- Tools (these run inside Django) ----
@tool
def search_menu(query: str = "", diet: List[str] = [], features: List[str] = [],
                price_cap: Optional[float] = None) -> List[dict]:
    """
    Search available menu items by keywords/tags/price.
    Returns a list of {id, name, price}.
    """
    qs = MenuItem.objects.filter(is_available=True)
    text = query.strip().lower()
    if text:
        qs = qs.filter(Q(name__icontains=text) | Q(description__icontains=text) |
                       Q(tags__name__icontains=text)).distinct()
    for d in diet:
        qs = qs.filter(tags__name__iexact=d)
    for f in features:
        qs = qs.filter(tags__name__iexact=f)
    if price_cap is not None:
        qs = qs.filter(price__lte=Decimal(str(price_cap)))
    qs = qs.order_by("-popularity")[:8]
    return [{"id": x.id, "name": x.name, "price": float(x.price)} for x in qs]

@tool
def add_to_cart(item_id: int, qty: int = 1, user_is_auth: bool = False,
                guest_token: str = "") -> str:
    """
    Add a menu item to the active cart (user or guest).
    """
    try:
        item = MenuItem.objects.get(id=item_id, is_available=True)
    except MenuItem.DoesNotExist:
        return "Item not found."
    # Build or get cart
    if user_is_auth:
        # Will be replaced by the view passing the real user; we just use guest route if False
        pass
    # We'll bind the user/guest in the wrapper (see run_order_agent below)
    return f"ADDED:{item_id}:{qty}"

@tool
def show_cart() -> dict:
    """Placeholder; the view injects a real summary after execution."""
    return {"info": "cart will be summarized by server"}

TOOLS = [search_menu, add_to_cart, show_cart]

# --- Build the graph ---
def build_graph():
    llm = ChatOpenAI(model=LLM_MODEL, temperature=0).bind_tools(TOOLS)
    graph = StateGraph(AgentState)

    def call_agent(state: AgentState):
        msgs = state["messages"]
        resp = llm.invoke(msgs)
        # LangChain returns a message with .tool_calls if any
        return {"messages": msgs + [resp]}

    def route(state: AgentState):
        last = state["messages"][-1]
        # If the LLM asked to call tools, go run them; else end.
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    def run_tools(state: AgentState):
        last = state["messages"][-1]
        actions_done = state.get("actions_done", [])
        new_msgs = []
        for tc in last.tool_calls:
            name = tc["name"]
            args = tc["args"]
            # Tools run later in wrapper to attach user/guest context;
            # here we just echo a placeholder tool result message.
            new_msgs.append({"role": "tool", "name": name, "content": str(args)})
        return {"messages": state["messages"] + new_msgs, "actions_done": actions_done}

    graph.add_node("agent", call_agent)
    graph.add_node("tools", run_tools)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", route, {"tools":"tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()