# Restaurant AI Agent

This project contains a LangGraph restaurant ordering workflow.

## Run

```powershell
cd rest_agent
pip install -e .
python main.py
```

The CLI accepts single- and multi-item orders such as `2 pizzas` or
`2 burgers, 3 coffees, and 4 pizzas` (numeric and basic word quantities are
supported). It validates availability for every line item, asks for a decision
on partial/unavailable items, then retries cooking and serving according to the
state counters. An accepted partial order contains every available quantity;
zero-availability items are omitted from the accepted order.

When `GROQ_API_KEY` is set in a `.env` file or the environment, the CLI uses
Groq's JSON extraction API with `openai/gpt-oss-120b`. Without a key, it uses
the offline `extract_order` parser. Tests can pass either extractor directly to
`build_graph(extractor=...)`; `build_graph(random_value=...)` similarly allows
deterministic tests of failure paths. A failed operation uses a 35% failure
probability and the remaining retry counter is stored in state.