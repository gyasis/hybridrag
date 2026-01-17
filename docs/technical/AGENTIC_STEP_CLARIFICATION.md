# AgenticStepProcessor: Critical Understanding

## ⚠️ `max_internal_steps` is NOT a Tool Call Limit!

### The Confusion

Many developers assume `max_internal_steps=8` means "maximum 8 tool calls total."

**This is WRONG!**

### What It Actually Means

`max_internal_steps` counts **reasoning iterations**, not individual tool calls.

## The Loop Structure

```python
# From agentic_step_processor.py lines 200-352
for step_num in range(self.max_internal_steps):  # Outer loop
    logger.info(f"Iteration {step_num + 1}/{self.max_internal_steps}")

    while True:  # Inner loop - unlimited iterations!
        # Call LLM to decide next action
        response_message = await llm_runner(messages, tools)

        if tool_calls:  # LLM requested tools
            # Execute ALL requested tools
            for tool_call in tool_calls:
                tool_result = await tool_executor(tool_call)
                last_tool_msgs.append(tool_result)

            # Build history based on mode
            if history_mode == "progressive":
                self.conversation_history.extend(last_tool_msgs)
                llm_history = [system, user] + self.conversation_history

            continue  # ← Stay in inner loop, DON'T increment step_num

        else:  # LLM provided final answer
            final_answer = response_message.content
            break  # ← Exit inner loop, NOW step_num increments
```

## Key Points

### 1. Inner Loop is Unlimited
The `while True:` inner loop (line 202) has **no iteration limit**. It continues until:
- ✅ LLM provides a final answer (no tool calls)
- ❌ Error occurs
- ❌ Clarification limit reached (3 attempts)

### 2. `step_num` Only Increments on Final Answer
Line 352: `continue` keeps you in the inner loop **without** incrementing `step_num`.
Line 367: `break` exits inner loop, allowing `step_num` to increment.

### 3. Multiple Tool Calls Per Iteration
Each iteration can have:
- Multiple LLM calls (one per tool execution round)
- Multiple tool calls per LLM call
- Accumulating context (in progressive/kitchen_sink modes)

## Real-World Example

### Configuration
```python
# query_with_promptchain.py line 215
agentic_step = AgenticStepProcessor(
    objective="Answer questions using LightRAG retrieval",
    max_internal_steps=8,
    history_mode="progressive"
)
```

### Possible Execution
```
Iteration 1 (step_num=0):
  LLM call 1: Calls query_global("architecture overview")
  Tool executes: Returns 500 tokens of context
  → continue (stay in inner loop)

  LLM call 2: Sees overview, calls query_local("specific implementation")
  Tool executes: Returns 300 tokens of context
  → continue (stay in inner loop)

  LLM call 3: Sees both contexts, calls query_hybrid("related patterns")
  Tool executes: Returns 400 tokens of context
  → continue (stay in inner loop)

  LLM call 4: Has full context, provides final answer
  → break (exit inner loop, step_num increments to 1)

Iteration 2 (step_num=1):
  ... (if needed for refinement)

Total consumed: 1-2 iterations out of 8
Total tool calls: 3+ (could be many more!)
Total LLM calls: 4+ (one per tool round + final answer)
```

## Progressive Mode Impact

With `history_mode="progressive"` (lines 309-319):
```python
# After EACH tool execution:
self.conversation_history.append(last_tool_call_assistant_msg)
self.conversation_history.extend(last_tool_msgs)

# On NEXT LLM call:
llm_history = [system, user] + self.conversation_history
# ↑ Contains ALL previous assistant messages + tool results
```

This means:
- ✅ Context accumulates across **all** tool calls
- ✅ LLM sees complete reasoning history
- ✅ Enables true multi-hop reasoning
- ⚠️ Context grows rapidly (use `max_context_tokens` monitoring)

## Token Growth Example

```
Tool call 1: +500 tokens (query_global result)
Tool call 2: +300 tokens (query_local result) = 800 total
Tool call 3: +400 tokens (query_hybrid result) = 1200 total
Tool call 4: +250 tokens (get_context_only result) = 1450 total
Tool call 5: +350 tokens (another query_local) = 1800 total

All in ONE iteration! (step_num still = 0)
```

## Common Misconceptions

### ❌ WRONG
```python
max_internal_steps=8  # "Maximum 8 tool calls allowed"
```

### ✅ CORRECT
```python
max_internal_steps=8  # "Maximum 8 reasoning iterations"
                      # Each iteration can have unlimited tool calls
                      # until the LLM decides to provide a final answer
```

## Implications for HybridRAG

In `query_with_promptchain.py`:
- Configuration allows **8 reasoning iterations**
- Each iteration can call `query_local`, `query_global`, `query_hybrid`, `get_context_only` multiple times
- Progressive mode accumulates **all** tool results
- Total tool calls could easily reach **20-50+** for complex queries
- Context can grow to **4000-6000 tokens** (hence `max_context_tokens=6000`)

## Best Practices

1. **Set `max_internal_steps` conservatively** (5-10 is usually plenty)
2. **Use `history_mode="progressive"`** for multi-hop reasoning
3. **Set `max_context_tokens`** to monitor context growth
4. **Design clear objectives** so LLM knows when to stop calling tools
5. **Monitor logs** to understand actual tool call patterns

## Debugging Tips

Check logs for:
```
INFO:agentic_step_processor:Agentic step internal iteration 1/8
INFO:agentic_step_processor:LLM requested 2 tool(s).
INFO:agentic_step_processor:Executing tool: query_global
INFO:agentic_step_processor:Executing tool: query_local
# ↑ Still in iteration 1!

INFO:agentic_step_processor:Agentic step internal iteration 2/8
# ↑ Now iteration 2 (LLM provided final answer in iteration 1)
```

Count the tool executions **between** iteration markers to see how many tools are called per iteration.

## Summary

- `max_internal_steps` = reasoning iterations (outer loop counter)
- Tool calls per iteration = unlimited (inner loop continues until final answer)
- With `history_mode="progressive"`, **all** tool results accumulate
- Actual tool calls >> `max_internal_steps` value
- This enables powerful multi-hop reasoning with full context retention
