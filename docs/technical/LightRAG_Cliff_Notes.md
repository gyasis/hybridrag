# LightRAG Cliff Notes - Structured Output for Tabular Data

## 🎯 **Quick Answer: YES, you can get structured output!**

LightRAG has multiple ways to control output format and get structured data about tables, columns, datatypes, and keys.

---

## 🔧 **1. Response Type Control**

### In your QueryParam:
```python
query_param = QueryParam(
    mode="hybrid",
    response_type="JSON",  # ← KEY: Change this for structured output
    # Other options:
    # response_type="Bullet Points"
    # response_type="Single Paragraph" 
    # response_type="Multiple Paragraphs"
)
```

### Available Response Types:
- `"JSON"` - Structured JSON output
- `"Bullet Points"` - Bulleted list format
- `"Single Paragraph"` - One paragraph
- `"Multiple Paragraphs"` - Multiple paragraphs (default)

---

## 🎯 **2. User Prompt for Structured Output**

### Add structured prompt to your query:
```python
query_text = """
[Return as JSON with this exact structure:
{
  "tables": [
    {
      "name": "table_name",
      "columns": [
        {
          "name": "column_name", 
          "datatype": "data_type",
          "is_primary_key": true/false,
          "is_foreign_key": true/false,
          "references": "referenced_table.column"
        }
      ],
      "relationships": ["table1", "table2"]
    }
  ]
}]
What tables are related to patient appointments?
"""
```

---

## 🔍 **3. Context-Only Mode for Raw Data**

### Get raw retrieval without LLM processing:
```python
query_param = QueryParam(
    mode="hybrid",
    only_need_context=True,  # ← Gets raw chunks/entities
    top_k=100  # More results
)
```

---

## 📊 **4. Modified Query Function for Tabular Data**

### Add this to your LightRAGQueryInterface class:
```python
async def query_structured(
    self, 
    query_text: str, 
    output_format: str = "JSON",
    mode: str = "hybrid"
):
    """Query with structured output for tabular data."""
    
    # Add structure prompt
    structured_query = f"""
[Return as {output_format} with this exact structure:
{{
  "tables": [
    {{
      "name": "table_name",
      "columns": [
        {{
          "name": "column_name",
          "datatype": "data_type", 
          "is_primary_key": true/false,
          "is_foreign_key": true/false,
          "references": "referenced_table.column",
          "nullable": true/false,
          "default_value": "default"
        }}
      ],
      "row_count": "estimated_count",
      "relationships": ["related_tables"]
    }}
  ]
}}]
{query_text}
"""
    
    query_param = QueryParam(
        mode=mode,
        response_type=output_format,
        top_k=80,  # More results for comprehensive data
        max_entity_tokens=8000,
        max_relation_tokens=10000
    )
    
    return await self.rag.aquery(structured_query, param=query_param)
```

---

## 🎛️ **5. Query Modes for Different Data Types**

| Mode | Best For | Use Case |
|------|----------|----------|
| `local` | Specific table relationships and foreign keys | "Show foreign keys for patient table" |
| `global` | High-level schema overview | "List all tables in the database" |
| `hybrid` | Comprehensive table + relationship info | "Complete schema for appointment system" |
| `naive` | Simple retrieval, basic column info | "What columns are in patient table?" |

---

## 🔄 **6. Two-Step Approach (Recommended)**

```python
# Step 1: Get context only (raw data)
context_result = await self.query(
    "patient appointment tables columns datatypes keys",
    only_need_context=True,
    mode="hybrid"
)

# Step 2: Process with structured prompt
structured_result = await self.query(
    f"[Return as JSON] Based on this context: {context_result}",
    response_type="JSON"
)
```

---

## 📝 **7. Specific Prompts for Your Needs**

### For table structure:
```
"List all tables with their columns, datatypes, primary keys, and foreign key relationships in JSON format"
```

### For specific table:
```
"Return the complete schema for patient_appointments table including all columns, datatypes, constraints, and relationships as JSON"
```

### For relationships:
```
"Show all foreign key relationships between tables in JSON format with source table, target table, and column mappings"
```

---

## ⚡ **8. Quick Implementation in Your Demo**

### Modify your existing `query` method in `lightrag_query_demo.py`:

```python
# Add this parameter to your existing query method (line ~93):
async def query(
    self, 
    query_text: str, 
    mode: str = "hybrid",
    only_need_context: bool = False,
    top_k: int = 60,
    max_entity_tokens: int = 6000,
    max_relation_tokens: int = 8000,
    response_type: str = "Multiple Paragraphs"  # ← ADD THIS
):
```

### Then update QueryParam creation (line ~120):
```python
query_param = QueryParam(
    mode=mode,
    only_need_context=only_need_context,
    top_k=top_k,
    max_entity_tokens=max_entity_tokens,
    max_relation_tokens=max_relation_tokens,
    response_type=response_type  # ← USE THE PARAMETER
)
```

---

## 🎯 **9. Where to Change Prompts in Your Demo**

### In `lightrag_query_demo.py`:

1. **Line ~126**: Change default `response_type`
2. **Line ~238**: Add structured prompt to user input
3. **Line ~120-127**: Modify QueryParam creation
4. **Add new method**: `query_structured()` for tabular data

### Example modification:
```python
# In the interactive loop (around line 238):
result = await self.query(
    f"[Return as JSON with table schema structure] {user_input}",  # ← Add prompt
    mode=current_mode,
    only_need_context=context_only,
    top_k=top_k,
    response_type="JSON"  # ← Force JSON output
)
```

---

## 🚀 **10. Complete Example for Tabular Data**

```python
# Example usage in your demo:
query_text = """
[Return as JSON with this structure:
{
  "tables": [
    {
      "name": "table_name",
      "columns": [
        {
          "name": "column_name",
          "datatype": "data_type",
          "is_primary_key": boolean,
          "is_foreign_key": boolean,
          "references": "table.column"
        }
      ]
    }
  ]
}]
What tables contain patient information and what are their schemas?
"""

result = await self.query_structured(query_text, "JSON", "hybrid")
```

---

## 📋 **11. Key Parameters to Tune**

| Parameter | Default | For Tabular Data | Purpose |
|-----------|---------|------------------|---------|
| `top_k` | 60 | 80-100 | More comprehensive results |
| `max_entity_tokens` | 6000 | 8000 | More entity context |
| `max_relation_tokens` | 8000 | 10000 | More relationship context |
| `response_type` | "Multiple Paragraphs" | "JSON" | Structured output |
| `mode` | "hybrid" | "hybrid" | Best for comprehensive data |

---

## 🎯 **Bottom Line**

- **YES**: LightRAG can return structured JSON/format
- **HOW**: Use `response_type="JSON"` + structured prompts
- **BEST**: Combine `only_need_context=True` + structured processing
- **MODE**: Use `hybrid` for comprehensive tabular data
- **PROMPT**: Be very specific about the JSON structure you want

**The key is in the prompt engineering** - tell LightRAG exactly what JSON structure you want, and it will format the retrieved knowledge graph data accordingly!

---

## 🔧 **Quick Start Commands**

```bash
# Run your demo with structured output
cd hybridrag
python lightrag_query_demo.py

# Then use these query patterns:
# /mode hybrid
# [Return as JSON] What tables are in the database?
# [Return as JSON] Show me the schema for patient tables
# /context  # Get raw data only
```

---

*Last updated: 2024 - LightRAG Structured Output Guide*
