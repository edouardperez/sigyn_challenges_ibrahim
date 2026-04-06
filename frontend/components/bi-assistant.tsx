"use client";

import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { Thread } from "@/components/assistant-ui/thread";
import { toolkit } from "@/components/toolkit";
import { createFecAdapter } from "@/lib/fec-adapter";

interface BiAssistantProps {
  sessionId: string;
}

export const BiAssistant = ({ sessionId }: BiAssistantProps) => {
  const runtime = useLocalRuntime(createFecAdapter(sessionId));

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="h-dvh">
        <Thread toolkit={toolkit} />
      </div>
    </AssistantRuntimeProvider>
  );
};
