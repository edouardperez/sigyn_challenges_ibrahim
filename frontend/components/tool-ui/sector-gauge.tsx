"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface SectorGaugeProps {
  label?: string;
  value?: number;
  q1?: number;
  mediane?: number;
  q3?: number;
  position?: string;
  unit?: string;
}

function fmt(v?: number, unit?: string): string {
  if (v == null) return "—";
  const s = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(v);
  return unit ? `${s} ${unit}` : s;
}

export function SectorGauge({ label, value, q1, mediane, q3, position, unit }: SectorGaugeProps) {
  const hasQuartiles = q1 != null && q3 != null;

  // Compute marker position as % along [q1..q3] band
  let pct = 50;
  if (hasQuartiles && value != null && q3! > q1!) {
    const clamped = Math.max(q1!, Math.min(q3!, value));
    pct = ((clamped - q1!) / (q3! - q1!)) * 100;
  }

  const statusColor =
    position?.toLowerCase().includes("dessus") || position?.toLowerCase().includes("q3")
      ? "text-emerald-600 dark:text-emerald-400"
      : position?.toLowerCase().includes("dessous") || position?.toLowerCase().includes("q1")
      ? "text-rose-600 dark:text-rose-400"
      : "text-amber-600 dark:text-amber-400";

  return (
    <Card className="w-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{label ?? "Positionnement sectoriel"}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold tabular-nums">{fmt(value, unit)}</span>
          {position && (
            <span className={cn("text-sm font-medium", statusColor)}>{position}</span>
          )}
        </div>

        {hasQuartiles && (
          <div className="space-y-1">
            {/* Quartile band */}
            <div className="relative h-3 rounded-full bg-muted overflow-visible">
              {/* Band fill */}
              <div className="absolute inset-0 rounded-full bg-gradient-to-r from-rose-200 via-amber-200 to-emerald-200 dark:from-rose-900 dark:via-amber-900 dark:to-emerald-900" />
              {/* Median tick */}
              {mediane != null && q1 != null && q3 != null && q3 > q1 && (
                <div
                  className="absolute top-0 w-0.5 h-full bg-foreground/40"
                  style={{ left: `${((mediane - q1) / (q3 - q1)) * 100}%` }}
                />
              )}
              {/* Value marker */}
              <div
                className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-4 h-4 rounded-full border-2 border-background bg-primary shadow-sm"
                style={{ left: `${pct}%` }}
              />
            </div>

            {/* Labels */}
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Q1 {fmt(q1, unit)}</span>
              {mediane != null && (
                <span>Médiane {fmt(mediane, unit)}</span>
              )}
              <span>Q3 {fmt(q3, unit)}</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
