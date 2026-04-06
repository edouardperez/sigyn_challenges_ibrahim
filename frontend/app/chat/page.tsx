"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BiAssistant } from "@/components/bi-assistant";

interface SessionInfo {
  sessionId: string;
  filename: string;
  rowCount: number;
  exercices: number[];
}

export default function ChatPage() {
  const router = useRouter();
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const sessionId = localStorage.getItem("fec_session_id");
    if (!sessionId) {
      router.replace("/");
      return;
    }

    const exercicesRaw = localStorage.getItem("fec_exercices");
    setSession({
      sessionId,
      filename: localStorage.getItem("fec_filename") ?? "FEC",
      rowCount: Number(localStorage.getItem("fec_row_count") ?? 0),
      exercices: exercicesRaw ? (JSON.parse(exercicesRaw) as number[]) : [],
    });
    setReady(true);
  }, [router]);

  if (!ready || !session) {
    return (
      <div className="h-dvh flex items-center justify-center text-sm text-muted-foreground">
        Chargement…
      </div>
    );
  }

  return (
    <div className="flex flex-col h-dvh">
      {/* Top info bar */}
      <header className="flex items-center gap-3 border-b px-4 py-2 text-xs text-muted-foreground shrink-0">
        <span className="font-semibold text-foreground">PCG FEC Agent</span>
        <span className="text-muted-foreground/40">·</span>
        <span
          className="max-w-[180px] truncate"
          title={session.filename}
        >
          {session.filename}
        </span>
        {session.rowCount > 0 && (
          <>
            <span className="text-muted-foreground/40">·</span>
            <span>{session.rowCount.toLocaleString("fr-FR")} écritures</span>
          </>
        )}
        {session.exercices.length > 0 && (
          <>
            <span className="text-muted-foreground/40">·</span>
            <span>Exercices : {session.exercices.join(", ")}</span>
          </>
        )}
        <span className="ml-auto">
          <button
            className="underline hover:text-foreground transition-colors"
            onClick={() => {
              localStorage.clear();
              router.push("/");
            }}
          >
            Changer de fichier
          </button>
        </span>
      </header>

      {/* Chat area — fills remaining height */}
      <div className="flex-1 min-h-0">
        <BiAssistant sessionId={session.sessionId} />
      </div>
    </div>
  );
}
