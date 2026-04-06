"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface WaterfallStep {
  label: string;
  rubrique_key?: string;
  value?: number;
  operator?: "base" | "add" | "subtract" | "subtotal" | "result";
  highlight?: boolean;
}

interface WaterfallSection {
  section_label?: string;
  steps: WaterfallStep[];
}

export interface WaterfallCardProps {
  title?: string;
  sections?: WaterfallSection[];
}

const OPERATOR_COLORS: Record<string, string> = {
  base: "text-foreground",
  add: "text-emerald-600 dark:text-emerald-400",
  subtract: "text-rose-600 dark:text-rose-400",
  subtotal: "text-blue-600 dark:text-blue-400 font-semibold",
  result: "text-blue-700 dark:text-blue-300 font-bold",
};

function fmt(v?: number): string {
  if (v == null) return "—";
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(v);
}

export function WaterfallCard({ title, sections }: WaterfallCardProps) {
  if (!sections?.length) return null;
  return (
    <Card className="w-full">
      {title && (
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{title}</CardTitle>
        </CardHeader>
      )}
      <CardContent className="space-y-4">
        {sections.map((section, si) => (
          <div key={si}>
            {section.section_label && (
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                {section.section_label}
              </p>
            )}
            <div className="divide-y divide-border">
              {section.steps.map((step, idx) => {
                const colorClass =
                  OPERATOR_COLORS[step.operator ?? "base"] ?? "text-foreground";
                const isHighlight = step.highlight;
                return (
                  <div
                    key={idx}
                    className={cn(
                      "flex items-center justify-between py-1.5 text-sm",
                      isHighlight && "bg-muted/40 rounded px-2"
                    )}
                  >
                    <span className={cn("flex-1 truncate", colorClass)}>
                      {step.label}
                    </span>
                    <span className={cn("ml-4 font-mono tabular-nums", colorClass)}>
                      {fmt(step.value)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
