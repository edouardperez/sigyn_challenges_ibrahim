# Plan: Generative BI Frontend with assistant-ui + tool-ui

## Context

The PCG FEC Agent backend (FastAPI on port 8000) is fully built. It exposes two endpoints:
- `POST /upload-fec` → returns `session_id`, `exercices`, `row_count`
- `POST /chat` → returns `final_answer` (markdown) + `response_blocks[]` (typed rich blocks)

The 7 block types are: `metric_card`, `table`, `chart`, `waterfall_card`, `sector_gauge`, `alert`, `text`.

We want a chat-first generative BI frontend where users upload a FEC file on a landing page, then chat and see results rendered as cards, charts, tables — not just plain text.

---

## Tech Stack

- **Next.js 15** (App Router) in `frontend/` subdirectory
- **assistant-ui** — `useLocalRuntime` with custom `ChatModelAdapter` (no AI SDK needed)
- **tool-ui** — `chart`, `data-table`, `stats-display` for BI blocks
- **shadcn/ui + Tailwind** — base UI components (included by assistant-ui CLI)

---

## Step-by-Step Plan

### 1. Add CORS to backend (`main.py`)

```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"], allow_headers=["*"])
```

**File:** `main.py` (modify existing, after `app = FastAPI(...)`)

---

### 2. Bootstrap Next.js + assistant-ui

From `frontend/` directory:
```bash
npx assistant-ui@latest create . -t minimal --yes
```

This scaffolds: Next.js, shadcn/ui, Tailwind, `@assistant-ui/react`, `@assistant-ui/react-markdown`, and the `components/assistant-ui/thread.tsx` primitive.

---

### 3. Install tool-ui components

```bash
npx shadcn@latest add @tool-ui/chart @tool-ui/data-table @tool-ui/stats-display
npm install recharts  # peer dep for chart
```

These install into `components/tool-ui/{chart,data-table,stats-display}/`.

---

### 4. App pages

**`app/page.tsx`** — Landing upload page:
- Dropzone for `.xlsx` / `.csv` FEC files
- On file select → `POST http://localhost:8000/upload-fec`
- Saves `{ session_id, exercices, row_count }` to `localStorage`
- Shows success state (filename, row count, fiscal years)
- "Start Analysis →" button navigates to `/chat`

**`app/chat/page.tsx`** — Chat page:
- Reads `session_id` from `localStorage`; redirects to `/` if missing
- Shows company info chip (RD CANNES, NAF 96.02A, exercices)
- Renders `<BiAssistant />` wrapping the thread

---

### 5. Custom ChatModelAdapter (`lib/fec-adapter.ts`)

```typescript
import { ChatModelAdapter } from "@assistant-ui/react";

export const createFecAdapter = (sessionId: string): ChatModelAdapter => ({
  async run({ messages, abortSignal }) {
    const lastUser = messages.findLast(m => m.role === "user");
    const text = lastUser?.content
      .filter(p => p.type === "text").map(p => p.text).join(" ") ?? "";

    const res = await fetch("http://localhost:8000/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId }),
      signal: abortSignal,
    });
    const data = await res.json();

    // Convert response_blocks → pseudo tool-call + tool-result pairs
    const blockParts = (data.response_blocks ?? []).flatMap((block, i) => [
      { type: "tool-call", toolCallId: `block-${i}`, toolName: `show_${block.type}`, args: block },
      { type: "tool-result", toolCallId: `block-${i}`, toolName: `show_${block.type}`, result: block },
    ]);

    return {
      content: [
        { type: "text", text: data.final_answer ?? "" },
        ...blockParts,
      ],
    };
  },
});
```

---

### 6. Toolkit (`components/toolkit.tsx`)

Maps each block type to a tool-ui (or custom) renderer:

| Tool name | Block type | Renderer |
|-----------|-----------|----------|
| `show_metric_card` | `metric_card` | `<StatsDisplay>` (tool-ui) |
| `show_table` | `table` | `<DataTable>` (tool-ui) |
| `show_chart` | `chart` | `<Chart>` (tool-ui/recharts) |
| `show_waterfall_card` | `waterfall_card` | Custom `<WaterfallCard>` |
| `show_sector_gauge` | `sector_gauge` | Custom `<SectorGauge>` |
| `show_alert` | `alert` | shadcn `<Alert>` |
| `show_text` | `text` | `<ReactMarkdown>` |

All entries use `type: "backend"` (no client-side execution needed).

---

### 7. Custom components (no tool-ui equivalent)

**`components/tool-ui/waterfall-card.tsx`**
- Renders a multi-section cascade (sections → steps with +/- operators)
- Highlights subtotals and results
- Uses shadcn `Card`, color-coded by operator (base=gray, add=green, subtract=red, result=blue)

**`components/tool-ui/sector-gauge.tsx`**
- Shows company value vs. BdF quartile band (Q1 → Q3)
- A simple horizontal range bar with a marker dot
- Shows Q1, median, Q3 labels + "position" text

---

### 8. BiAssistant wrapper (`components/bi-assistant.tsx`)

```tsx
"use client";
import { AssistantRuntimeProvider, Tools, useAui } from "@assistant-ui/react";
import { useLocalRuntime } from "@assistant-ui/react";
import { Thread } from "@/components/assistant-ui/thread";
import { toolkit } from "@/components/toolkit";
import { createFecAdapter } from "@/lib/fec-adapter";

export const BiAssistant = ({ sessionId }: { sessionId: string }) => {
  const runtime = useLocalRuntime(createFecAdapter(sessionId));
  const aui = useAui({ tools: Tools({ toolkit }) });
  return (
    <AssistantRuntimeProvider runtime={runtime} aui={aui}>
      <div className="h-dvh">
        <Thread />
      </div>
    </AssistantRuntimeProvider>
  );
};
```

---

## Critical Files

| File | Action |
|------|--------|
| `main.py` | Modify — add CORS middleware |
| `frontend/` | Create — Next.js app (CLI scaffold) |
| `frontend/lib/fec-adapter.ts` | Create — custom ChatModelAdapter |
| `frontend/components/toolkit.tsx` | Create — tool-ui toolkit wiring |
| `frontend/components/tool-ui/waterfall-card.tsx` | Create — custom renderer |
| `frontend/components/tool-ui/sector-gauge.tsx` | Create — custom renderer |
| `frontend/app/page.tsx` | Create — landing + upload page |
| `frontend/app/chat/page.tsx` | Create — chat page |
| `frontend/components/bi-assistant.tsx` | Create — runtime wrapper |

---

## Verification

1. Start backend: `python main.py` (port 8000)
2. Start frontend: `cd frontend && npm run dev` (port 3000)
3. Open `http://localhost:3000` — landing page with upload dropzone
4. Upload the RD CANNES `.xlsx` FEC file
5. See success state (9,375 rows, exercices)
6. Click "Start Analysis" → `/chat`
7. Ask: _"Analyse la structure financière de l'entreprise"_
8. Verify: `final_answer` renders as markdown, `response_blocks` render as:
   - KPI cards (metric_card → StatsDisplay)
   - Tables (data-table)
   - Trend charts (chart → recharts LineChart)
   - Waterfall cascades (custom WaterfallCard)
   - Sector gauge (custom SectorGauge)
