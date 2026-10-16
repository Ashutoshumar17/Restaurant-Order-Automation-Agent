"""Restaurant ordering workflow implemented with LangGraph.

The graph is deliberately usable without an API key.  ``extract_order`` is a
small deterministic fallback; applications can replace it with an LLM-backed
extractor without changing the workflow or its state contract.
"""

from __future__ import annotations

import random
import re
import os
import json
from typing import Annotated, Callable, TypedDict

from dotenv import load_dotenv
from groq import Groq
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


load_dotenv()

MENU: dict[str, int] = {
    "pizza": 5,
    "burger": 4,
    "pasta": 3,
    "salad": 6,
    "coffee": 10,
    "tea": 8,
    "sushi": 0,
}


class OrderItem(TypedDict):
    dish_name: str
    required_quantity: int
    available_quantity: int


Order = list[OrderItem]


class RestaurantState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    order: Order
    status: str
    order_retry_attempts: int
    cook_retry_attempts: int
    serve_retry_attempts: int
    final_result: str
    awaiting_user: bool
    user_input: str


def _message(state: RestaurantState, text: str) -> dict:
    return {"messages": [{"role": "assistant", "content": text}]}


def extract_order(text: str) -> Order | None:
    """Extract comma- or conjunction-separated quantities and dishes."""
    lowered = text.lower().strip()
    quantities = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    item_pattern = r"(?:(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+)?([a-z]+)"
    items: Order = []
    for part in re.split(r"\s*(?:,|\band\b)\s*", lowered):
        match = re.search(item_pattern, part)
        if not match:
            continue
        token, word = match.groups()
        dish = next((item for item in MENU if word.rstrip("s") == item), None)
        if dish is None:
            continue
        quantity = quantities[token] if token in quantities else int(token) if token else 1
        if quantity > 0:
            items.append({"dish_name": dish, "required_quantity": quantity, "available_quantity": 0})
    return items or None


def llm_extract_order(text: str) -> Order | None:
    """Extract an order with Groq's JSON response mode."""
    my_api_key = os.getenv("GROQ_API_KEY")
    if not my_api_key:
        raise ValueError("GROQ_API_KEY environment variable not set. Please set it in your .env file.")

    client = Groq(api_key=my_api_key)
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    f"Extract food orders only. The available menu is: {', '.join(MENU)}. "
                    'Return JSON with exactly {"items": [{"dish_name": string, '
                    '"required_quantity": integer, "available_quantity": 0}]}. '
                    "Return an empty items list for unrelated requests or unknown menu items."
                ),
            },
            {"role": "user", "content": text},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Groq returned an empty order extraction response.")
    try:
        result = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("Groq returned invalid JSON for order extraction.") from error

    raw_items = result.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Groq order extraction response did not contain an items list.")
    items: Order = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        dish_name = item.get("dish_name")
        required_quantity = item.get("required_quantity")
        if isinstance(dish_name, str) and dish_name.lower() in MENU and isinstance(required_quantity, int) and required_quantity > 0:
            items.append({"dish_name": dish_name.lower(), "required_quantity": required_quantity, "available_quantity": 0})
    return items or None


def receive_order(state: RestaurantState, *, extractor: Callable[[str], Order | None] = extract_order) -> dict:
    text = state.get("user_input", "")
    order: Order | None = None
    if state.get("status") in {"partial", "unavailable"}:
        answer = text.lower().strip()
        if state.get("status") == "partial":
            if answer in {"yes", "y", "confirm", "go ahead", "no", "n", "reject", "cancel"}:
                return {"status": "partial", "awaiting_user": False}
            order = extractor(text)
            if order is None:
                return {
                    **_message(state, "Please answer yes to accept the partial order, no to reject it, or enter a new order."),
                    "status": "partial",
                    "awaiting_user": True,
                }
        elif state.get("status") == "unavailable":
            order = extractor(text)
            if order is None:
                return {
                    **_message(state, "Please enter a new food or beverage order."),
                    "status": "unavailable",
                    "awaiting_user": True,
                }
    if order is None:
        order = extractor(text)
    if order is None:
        remaining = state.get("order_retry_attempts", 3) - 1
        if remaining <= 0:
            return {
                **_message(state, "I am sorry, but the maximum number of order attempts has been reached."),
                "status": "failed",
                "order_retry_attempts": 0,
                "final_result": "Order failed after too many order attempts.",
            }
        return {
            **_message(state, "I am a restaurant ordering assistant. Please order food or a beverage, such as '2 pizzas'."),
            "status": "invalid",
            "order_retry_attempts": remaining,
            "awaiting_user": True,
        }
    remaining = state.get("order_retry_attempts", 3) - 1
    return {
        **_message(state, "I understood your order as " + ", ".join(
            f"{item['required_quantity']} {item['dish_name']}" for item in order
        ) + "."),
        "order": order,
        "status": "received",
        "order_retry_attempts": max(remaining, 0),
        "awaiting_user": False,
    }


def order_confirm(state: RestaurantState) -> dict:
    order = state["order"]
    updated_order: Order = [
        {**item, "available_quantity": MENU.get(item["dish_name"], 0)}
        for item in order
    ]
    fully_available = all(item["available_quantity"] >= item["required_quantity"] for item in updated_order)
    has_available = any(item["available_quantity"] > 0 for item in updated_order)
    status = "confirmed" if fully_available else "partial" if has_available else "unavailable"
    if status == "unavailable" and state.get("order_retry_attempts", 0) <= 0:
        return {
            **_message(state, "I am sorry, but the maximum number of order attempts has been reached."),
            "order": updated_order,
            "status": "failed",
            "order_retry_attempts": 0,
            "final_result": "Order failed after too many order attempts.",
        }
    if status == "confirmed":
        text = "Your order is confirmed: " + ", ".join(
            f"{item['required_quantity']} {item['dish_name']}" for item in updated_order
        ) + "."
    elif status == "partial":
        details = ", ".join(
            f"{item['available_quantity']} {item['dish_name']} available"
            for item in updated_order if item["available_quantity"] < item["required_quantity"]
        )
        text = f"Some items are only partially available ({details}). Reply 'yes' to accept available quantities, or place a new order."
    else:
        text = "None of the requested items are available. Please place a new order."
    return {
        **_message(state, text),
        "order": updated_order,
        "status": status,
        "awaiting_user": status in {"partial", "unavailable"},
    }


def partial_order_decision(state: RestaurantState) -> dict:
    answer = state.get("user_input", "").lower().strip()
    if state.get("status") == "partial" and answer in {"yes", "y", "confirm", "go ahead"}:
        order = state["order"]
        accepted_order: Order = [
            {
                **item,
                "required_quantity": min(item["required_quantity"], item["available_quantity"]),
            }
            for item in order if item["available_quantity"] > 0
        ]
        return {
            **_message(state, "Continuing with " + ", ".join(
                f"{item['required_quantity']} {item['dish_name']}" for item in accepted_order
            ) + "."),
            "order": accepted_order,
            "status": "confirmed",
            "awaiting_user": False,
        }
    remaining = state.get("order_retry_attempts", 3)
    if remaining <= 0:
        return {
            **_message(state, "I am sorry, but the maximum number of order attempts has been reached."),
            "status": "failed",
            "final_result": "Order failed after too many order attempts.",
            "order_retry_attempts": 0,
        }
    return {
        **_message(state, "Please enter a new food or beverage order."),
        "status": "new_order",
        "order_retry_attempts": remaining,
        "awaiting_user": True,
    }


def cook(state: RestaurantState, *, random_value: Callable[[], float] = random.random) -> dict:
    remaining = state.get("cook_retry_attempts", 2)
    if state.get("status") == "serving_failed":
        if remaining <= 0:
            return {
                **_message(state, "I am sorry, but cooking retries have been exhausted."),
                "status": "failed",
                "cook_retry_attempts": 0,
                "final_result": "Order failed because cooking retries were exhausted.",
            }
        remaining -= 1
    if random_value() < 0.35:
        remaining -= 1
        if remaining > 0:
            return {**_message(state, f"Cooking failed. I will retry ({remaining} attempt(s) left)."), "status": "cooking_failed", "cook_retry_attempts": remaining}
        return {**_message(state, "I am sorry, but we could not prepare your order."), "status": "failed", "cook_retry_attempts": 0, "final_result": "Order failed during cooking."}
    return {**_message(state, "Your order is ready to be served."), "status": "ready", "cook_retry_attempts": remaining}


def serve(state: RestaurantState, *, random_value: Callable[[], float] = random.random) -> dict:
    remaining = state.get("serve_retry_attempts", 2)
    if random_value() < 0.35:
        remaining -= 1
        if remaining > 0:
            return {**_message(state, f"Serving failed. I will retry ({remaining} attempt(s) left)."), "status": "serving_failed", "serve_retry_attempts": remaining}
        return {**_message(state, "I am sorry, but we could not serve your order."), "status": "failed", "serve_retry_attempts": 0, "final_result": "Order failed during serving."}
    return {**_message(state, "Your order is complete. Enjoy your meal!"), "status": "complete", "final_result": "Order completed."}


def build_graph(
    *,
    random_value: Callable[[], float] = random.random,
    extractor: Callable[[str], Order | None] = extract_order,
):
    """Build a compiled graph; ``random_value`` makes failure paths testable."""
    graph = StateGraph(RestaurantState)
    graph.add_node("receive_order", lambda state: receive_order(state, extractor=extractor))
    graph.add_node("order_confirm", order_confirm)
    graph.add_node("partial_order_decision", partial_order_decision)
    graph.add_node("cook", lambda state: cook(state, random_value=random_value))
    graph.add_node("serve", lambda state: serve(state, random_value=random_value))
    graph.add_edge(START, "receive_order")
    graph.add_conditional_edges(
        "receive_order",
        lambda s: "order_confirm" if s.get("status") == "received" else
        "partial_order_decision"
        if s.get("status") == "partial"
        and s.get("user_input", "").lower().strip()
        in {"yes", "y", "confirm", "go ahead", "no", "n", "reject", "cancel"}
        else END,
    )
    graph.add_conditional_edges(
        "order_confirm",
        lambda s: "cook" if s.get("status") == "confirmed" else END,
    )
    graph.add_conditional_edges(
        "partial_order_decision",
        lambda s: "cook" if s.get("status") == "confirmed" else END,
    )
    graph.add_conditional_edges(
        "cook",
        lambda s: "serve" if s.get("status") == "ready" else "cook" if s.get("status") == "cooking_failed" else END,
    )
    graph.add_conditional_edges(
        "serve",
        lambda s: "cook" if s.get("status") == "serving_failed"
        and s.get("serve_retry_attempts", 0) > 0
        and s.get("cook_retry_attempts", 0) > 0 else END,
    )
    return graph.compile()


def initial_state(user_input: str) -> RestaurantState:
    return {
        "messages": [],
        "user_input": user_input,
        "order_retry_attempts": 3,
        "cook_retry_attempts": 2,
        "serve_retry_attempts": 2,
        "final_result": "",
        "awaiting_user": False,
    }


def run_cli() -> None:
    print("Restaurant ordering assistant. Type 'quit' to exit.")
    extractor = llm_extract_order if os.getenv("GROQ_API_KEY") else extract_order
    graph = build_graph(extractor=extractor)
    text = input("You: ").strip()
    if text.lower() in {"quit", "exit"}:
        return
    state = initial_state(text)
    printed_messages = 0

    while True:
        result = graph.invoke(state)
        messages = result.get("messages", [])
        for message in messages[printed_messages:]:
            if getattr(message, "type", None) == "ai":
                print(f"Assistant: {message.content}")
        printed_messages = len(messages)
        state = result

        if state.get("status") in {"complete", "failed"}:
            break
        if not state.get("awaiting_user"):
            break

        text = input("You: ").strip()
        if text.lower() in {"quit", "exit"}:
            return
        state = {**state, "user_input": text}


if __name__ == "__main__":
    run_cli()
