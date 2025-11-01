# dining/agent_runner.py
import re
from decimal import Decimal
from typing import Dict, Any
from django.contrib.auth.models import User, AnonymousUser
from .agent_graph import build_graph, TOOLS
from .models import Cart, CartItem, MenuItem
from .views import get_guest_token

GRAPH = build_graph()

def _get_or_create_cart_for_request(request):
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart, True, ""
    guest_token = get_guest_token(request)
    cart, _ = Cart.objects.get_or_create(user=None, guest_token=guest_token)
    return cart, False, guest_token

def _apply_tool_effects(tool_name: str, args: Dict[str, Any], request, cart):
    if tool_name == "add_to_cart":
        item_id = int(args.get("item_id"))
        qty = int(args.get("qty", 1))
        try:
            item = MenuItem.objects.get(id=item_id, is_available=True)
        except MenuItem.DoesNotExist:
            return "Item not found."
        ci, created = CartItem.objects.get_or_create(cart=cart, menu_item=item, defaults={"qty": qty})
        if not created:
            ci.qty += qty
            ci.save()
        return f"Added {qty} × {item.name} to your cart."
    return f"Ran tool {tool_name}."

def run_order_agent(request, message: str):
    # Seed conversation
    state = {
        "messages": [{"role":"system","content":
                      "You are a food-ordering assistant. Use tools to search for dishes and add them to the cart. "\
                      "Be concise. If the user mentions a quantity, add that many. Respect budgets and diets."}],
    }
    state["messages"].append({"role":"user", "content": message})

    # First agent pass (may request tools)
    state = GRAPH.invoke(state)

    # If tools were requested, actually execute them with request-aware context:
    cart, is_auth, guest_token = _get_or_create_cart_for_request(request)
    last = state["messages"][-1]
    tool_results_text = []
    if hasattr(last, "tool_calls") and last.tool_calls:
        for tc in last.tool_calls:
            tool_name = tc["name"]
            args = tc["args"] or {}
            # Force context for add_to_cart
            if tool_name == "add_to_cart":
                args["user_is_auth"] = is_auth
                args["guest_token"] = guest_token
            # Apply real effect:
            res_text = _apply_tool_effects(tool_name, args, request, cart)
            tool_results_text.append(res_text)
            # Feed back a tool message so the agent can summarize
            state["messages"].append({"role":"tool","name":tool_name,"content":res_text})

        # Let agent produce the final natural reply
        state = GRAPH.invoke(state)

    # Build cart summary
    items = CartItem.objects.filter(cart=cart).select_related("menu_item")
    summary = [{"name":it.menu_item.name, "qty":it.qty, "price":float(it.menu_item.price)} for it in items]
    total = float(sum(it.qty * it.menu_item.price for it in items))

    # Pick the last assistant message as follow-up
    follow_up = ""
    for m in reversed(state["messages"]):
        if getattr(m, "role", None) == "assistant" or (isinstance(m, dict) and m.get("role")=="assistant"):
            follow_up = m.get("content") if isinstance(m, dict) else m.content
            break

    return {
        "actions_done": tool_results_text,
        "cart": {"items": summary, "total": total},
        "follow_up": follow_up or "Added to your cart. Anything else?",
    }