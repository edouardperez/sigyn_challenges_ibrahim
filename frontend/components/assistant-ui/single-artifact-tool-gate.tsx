"use client";

import { useAuiState } from "@assistant-ui/react";
import { type ReactNode, useMemo } from "react";

/**
 * Names of backend tools registered in `toolkit.tsx` that render a visible
 * block in the chat. For one assistant message, only the first such tool call
 * is shown so the thread does not stack multiple cards.
 */
const VISUAL_TOOLKIT_TOOLS = new Set([
	"show_metric_card",
	"show_table",
	"show_chart",
	"show_waterfall_card",
	"show_sector_gauge",
	"show_alert",
]);

function normalizeToolName(name: string): string {
	return name.trim().toLowerCase().replace(/-/g, "_");
}

function isVisualToolkitTool(toolName: string): boolean {
	const n = normalizeToolName(toolName);
	return VISUAL_TOOLKIT_TOOLS.has(toolName) || VISUAL_TOOLKIT_TOOLS.has(n);
}

type SingleArtifactToolGateProps = {
	toolCallId: string;
	toolName: string;
	children: ReactNode;
};

/**
 * Wraps a single tool-call render. If this message includes several visual
 * toolkit tools, only the first one is rendered; later ones render a hidden
 * placeholder so assistant-ui does not fall back to `DefaultPartFallback`
 * (returning `null` would re-show the tool UI).
 */
export function SingleArtifactToolGate({
	toolCallId,
	toolName,
	children,
}: SingleArtifactToolGateProps) {
	const parts = useAuiState((s) => s.message.parts);

	const { firstVisualIndex, myIndex } = useMemo(() => {
		const first = parts.findIndex(
			(p) => p.type === "tool-call" && isVisualToolkitTool(p.toolName),
		);
		const idx = parts.findIndex(
			(p) => p.type === "tool-call" && p.toolCallId === toolCallId,
		);
		return { firstVisualIndex: first, myIndex: idx };
	}, [parts, toolCallId]);

	if (!isVisualToolkitTool(toolName)) {
		return <>{children}</>;
	}
	if (firstVisualIndex < 0 || myIndex < 0) {
		return <>{children}</>;
	}
	if (myIndex !== firstVisualIndex) {
		/* Not null — MessagePrimitive.Parts would otherwise fall back to DefaultPartFallback and re-show the tool UI. */
		return <span className="hidden" aria-hidden="true" />;
	}
	return <>{children}</>;
}
