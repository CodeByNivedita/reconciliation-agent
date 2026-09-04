
import os
import json

from backend.agent.prompts import SYSTEM_PROMPT
from backend.tools.reconciliation_tools import reconcile_order_tool
from backend.tools.order_tools import load_orders
from backend.tools.settlement_tools import load_settlements

PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()

TOOL_DESCRIPTION = (
    "Runs the deterministic reconciliation rules engine for a single order_id "
    "and returns its category, matched transaction id(s), settled amount, "
    "confidence, reason, and default action. Always call this before stating "
    "a reconciliation verdict — never classify a case from memory or from the "
    "raw CSV rows alone."
)


def run_agent_on_case(order_id: str) -> dict:
    orders = load_orders()
    settlements = load_settlements()
    if PROVIDER == "openai":
        return _run_openai(order_id, orders, settlements)
    if PROVIDER == "anthropic":
        return _run_anthropic(order_id, orders, settlements)
    return _run_gemini(order_id, orders, settlements)



def _run_gemini(order_id: str, orders, settlements) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    tool_declaration = {
        "name": "reconcile_order",
        "description": TOOL_DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order_id to reconcile, e.g. 'ORD-000123'."},
            },
            "required": ["order_id"],
        },
    }

    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=SYSTEM_PROMPT,
        tools=[{"function_declarations": [tool_declaration]}],
    )
    chat = model.start_chat()
    response = chat.send_message(f"Reconcile order {order_id}.")

    while True:
        function_call = None
        for part in response.candidates[0].content.parts:
            if getattr(part, "function_call", None):
                function_call = part.function_call
                break
        if not function_call:
            break
        args = dict(function_call.args)
        result = reconcile_order_tool(args["order_id"], orders, settlements)
        response = chat.send_message(
            genai.protos.Content(parts=[genai.protos.Part(
                function_response=genai.protos.FunctionResponse(
                    name="reconcile_order", response={"result": result},
                )
            )])
        )

    return {"order_id": order_id, "agent_response": response.text, "provider": "gemini"}


# --------------------------------------------------------------------------
# OpenAI
# --------------------------------------------------------------------------
def _run_openai(order_id: str, orders, settlements) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model_name = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    tool_schema = {
        "type": "function",
        "function": {
            "name": "reconcile_order",
            "description": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order_id to reconcile, e.g. 'ORD-000123'."},
                },
                "required": ["order_id"],
            },
        },
    }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Reconcile order {order_id}."},
    ]
    response = client.chat.completions.create(model=model_name, messages=messages, tools=[tool_schema])
    msg = response.choices[0].message

    while msg.tool_calls:
        messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = reconcile_order_tool(args["order_id"], orders, settlements)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
        response = client.chat.completions.create(model=model_name, messages=messages, tools=[tool_schema])
        msg = response.choices[0].message

    return {"order_id": order_id, "agent_response": msg.content, "provider": "openai"}


# --------------------------------------------------------------------------
# Anthropic (kept for parity if you get access to a key later)
# --------------------------------------------------------------------------
def _run_anthropic(order_id: str, orders, settlements) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model_name = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    tool_schema = {
        "name": "reconcile_order",
        "description": TOOL_DESCRIPTION,
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order_id to reconcile, e.g. 'ORD-000123'."},
            },
            "required": ["order_id"],
        },
    }

    messages = [{"role": "user", "content": f"Reconcile order {order_id}."}]
    response = client.messages.create(
        model=model_name, max_tokens=1024, system=SYSTEM_PROMPT, tools=[tool_schema], messages=messages,
    )

    while response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use" and block.name == "reconcile_order":
                result = reconcile_order_tool(block.input["order_id"], orders, settlements)
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
        response = client.messages.create(
            model=model_name, max_tokens=1024, system=SYSTEM_PROMPT, tools=[tool_schema], messages=messages,
        )

    final_text = "".join(b.text for b in response.content if b.type == "text")
    return {"order_id": order_id, "agent_response": final_text, "provider": "anthropic"}

