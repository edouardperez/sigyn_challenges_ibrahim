# Progress Tracker Usage Guide

The progress tracker component has been successfully integrated into the chat interface and **automatically displays after each analysis**.

## ✅ Automatic Progress Tracking

**The progress tracker now shows automatically for every chat query!** The synthesizer node automatically generates a progress block showing:
- All steps from the agent's execution plan
- Status of each step (completed/failed/pending)
- Final outcome summary (success/failure/partial)

You'll see it appear at the top of each response, showing what the agent did to answer your question.

## How It Works

## Frontend Integration

The progress tracker is now available in `components/toolkit.tsx` as the `show_progress` tool.

### Data Structure

The component expects the following JSON structure:

```typescript
{
  id: string;                    // Unique identifier for the progress tracker
  steps: [
    {
      id: string;                // Unique step ID
      label: string;             // Step display name
      description?: string;      // Optional step description
      status: "pending" | "in-progress" | "completed" | "failed";
    }
  ];
  elapsedTime?: number;          // Optional elapsed time in milliseconds
  choice?: {                     // Optional receipt state (when complete)
    outcome: "success" | "failure" | "cancelled";
    summary: string;
    identifiers?: Record<string, string>;
    at: string;                  // ISO timestamp
  }
}
```

## Backend Usage (Python)

### Option 1: Direct Tool Call (Simple)

If you want to add a simple progress tracker to any existing tool, you can return the progress data directly:

```python
def some_analysis_tool(args: dict, engine, semantic) -> dict:
    """Example tool that shows progress during execution."""
    
    # Return progress tracker data
    return {
        "tool": "show_progress",
        "result": {
            "id": "analysis-progress-1",
            "steps": [
                {
                    "id": "load-data",
                    "label": "Chargement des données FEC",
                    "status": "completed"
                },
                {
                    "id": "validate",
                    "label": "Validation des écritures",
                    "status": "in-progress"
                },
                {
                    "id": "analyze",
                    "label": "Analyse financière",
                    "status": "pending"
                }
            ]
        }
    }
```

### Option 2: Streaming Updates (Advanced)

For real-time progress updates during long-running operations, you can send multiple updates:

```python
# In your LangGraph node or tool executor:

# Step 1: Start progress
yield {
    "tool": "show_progress",
    "result": {
        "id": "waterfall-calc",
        "steps": [
            {"id": "step1", "label": "Calcul résultat net", "status": "in-progress"},
            {"id": "step2", "label": "Charges externes", "status": "pending"},
            {"id": "step3", "label": "Charges personnel", "status": "pending"},
        ]
    }
}

# Step 2: Update progress
yield {
    "tool": "show_progress",
    "result": {
        "id": "waterfall-calc",
        "steps": [
            {"id": "step1", "label": "Calcul résultat net", "status": "completed"},
            {"id": "step2", "label": "Charges externes", "status": "in-progress"},
            {"id": "step3", "label": "Charges personnel", "status": "pending"},
        ],
        "elapsedTime": 1500
    }
}

# Step 3: Complete with receipt
yield {
    "tool": "show_progress",
    "result": {
        "id": "waterfall-calc",
        "steps": [
            {"id": "step1", "label": "Calcul résultat net", "status": "completed"},
            {"id": "step2", "label": "Charges externes", "status": "completed"},
            {"id": "step3", "label": "Charges personnel", "status": "completed"},
        ],
        "elapsedTime": 3200,
        "choice": {
            "outcome": "success",
            "summary": "Cascade calculée avec succès (3 étapes)",
            "at": "2026-04-05T10:30:00Z"
        }
    }
}
```

## Integration Examples

### Example 1: FEC Upload Progress

Add to the `/upload-fec` endpoint in `pcg_agent/api/routes.py`:

```python
# After file is received
progress_steps = [
    {"id": "upload", "label": "Téléchargement du fichier", "status": "completed"},
    {"id": "parse", "label": "Analyse du fichier", "status": "in-progress"},
    {"id": "validate", "label": "Validation des écritures", "status": "pending"},
    {"id": "load", "label": "Chargement en mémoire", "status": "pending"},
]

# Update as you progress through ingestion steps...
```

### Example 2: Multi-Step Analysis

For complex operations like waterfall calculation or sector comparison:

```python
def compute_waterfall_with_progress(args, engine, semantic):
    steps = [
        {"id": "net", "label": "Résultat net", "status": "in-progress"},
        {"id": "charges", "label": "Charges", "status": "pending"},
        {"id": "products", "label": "Produits", "status": "pending"},
    ]
    
    # Start
    yield {"tool": "show_progress", "result": {"id": "waterfall", "steps": steps}}
    
    # ... do calculations, update steps ...
    
    # Finally return the actual waterfall
    yield {"tool": "show_waterfall_card", "result": waterfall_data}
```

## Tips

1. **Keep it Simple**: For most cases, just show static progress after an operation completes
2. **Unique IDs**: Always use unique IDs for each progress tracker instance
3. **Meaningful Labels**: Use French labels that match your business domain
4. **Status Flow**: Always go `pending → in-progress → completed/failed`
5. **Receipts**: Use the `choice` field to show final outcome and summary

## Testing

To test the component, you can manually call it from the chat:

```bash
# Start the frontend
cd frontend
npm run dev

# The backend should return progress data in the expected format
# The component will automatically render in the chat interface
```

## Next Steps

To fully integrate streaming progress:

1. Modify your LangGraph nodes to yield progress updates
2. Update the FastAPI `/chat` endpoint to stream tool calls
3. Ensure the frontend transport handles streaming tool updates
