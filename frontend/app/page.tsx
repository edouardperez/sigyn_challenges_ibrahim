"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface UploadResult {
  session_id: string;
  exercices: number[];
  row_count: number;
  message: string;
}

export default function Home() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  function handleFile(f: File) {
    setFile(f);
    setResult(null);
    setError(null);
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  }

  async function upload() {
    if (!file) return;
    setLoading(true);
    setError(null);
    const body = new FormData();
    body.append("file", file);

    try {
      const res = await fetch("http://localhost:8000/upload-fec", {
        method: "POST",
        body,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail ?? `Erreur ${res.status}`);
      }
      const data: UploadResult = await res.json();
      localStorage.setItem("fec_session_id", data.session_id);
      localStorage.setItem("fec_exercices", JSON.stringify(data.exercices));
      localStorage.setItem("fec_filename", file.name);
      localStorage.setItem("fec_row_count", String(data.row_count));
      setResult(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-dvh flex flex-col items-center justify-center bg-background p-6">
      <div className="w-full max-w-lg space-y-6">
        {/* Header */}
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">PCG FEC Agent</h1>
          <p className="text-sm text-muted-foreground">
            Analysez vos écritures comptables par conversation
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Charger un fichier FEC</CardTitle>
            <CardDescription>Formats acceptés : .xlsx, .xls, .csv</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Drop zone */}
            <div
              className={`relative flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 transition-colors cursor-pointer
                ${dragging ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/40"}`}
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
            >
              <span className="text-3xl select-none">📁</span>
              {file ? (
                <p className="text-sm font-medium text-center">{file.name}</p>
              ) : (
                <p className="text-sm text-muted-foreground text-center">
                  Glissez votre fichier ici ou{" "}
                  <span className="underline">parcourir</span>
                </p>
              )}
              <input
                ref={inputRef}
                type="file"
                accept=".xlsx,.xls,.csv"
                className="hidden"
                onChange={onInputChange}
              />
            </div>

            {error && (
              <p className="text-sm text-destructive bg-destructive/10 rounded px-3 py-2">
                {error}
              </p>
            )}

            {file && !result && (
              <Button onClick={upload} disabled={loading} className="w-full">
                {loading ? "Chargement en cours…" : "Analyser le fichier"}
              </Button>
            )}

            {result && (
              <div className="space-y-3">
                <div className="rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 p-3 text-sm space-y-1">
                  <p className="font-medium text-emerald-700 dark:text-emerald-300">
                    Fichier chargé avec succès
                  </p>
                  <p className="text-muted-foreground">
                    {result.row_count.toLocaleString("fr-FR")} écritures · Exercices :{" "}
                    {result.exercices.join(", ")}
                  </p>
                </div>
                <Button onClick={() => router.push("/chat")} className="w-full">
                  Démarrer l&apos;analyse →
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <p className="text-center text-xs text-muted-foreground">
          Un FEC est déjà pré-chargé sur le serveur.{" "}
          <button
            className="underline hover:text-foreground transition-colors"
            onClick={() => {
              localStorage.setItem("fec_session_id", "default");
              localStorage.setItem("fec_exercices", "[]");
              localStorage.setItem("fec_filename", "FEC pré-chargé");
              localStorage.setItem("fec_row_count", "0");
              router.push("/chat");
            }}
          >
            Utiliser la session par défaut
          </button>
        </p>
      </div>
    </main>
  );
}
