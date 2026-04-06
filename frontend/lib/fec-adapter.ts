import type { ChatModelAdapter } from "@assistant-ui/react";

export type JSONValue =
	| string
	| number
	| boolean
	| null
	| JSONValue[]
	| { [key: string]: JSONValue };

export interface ResponseBlock {
	type: string;
	[key: string]: JSONValue;
}

/** Rich blocks that should not stack; `text` is excluded so a text block does not hide cards. */
const VISUAL_BLOCK_TYPES = new Set([
	"metric_card",
	"sector_gauge",
	"chart",
	"table",
	"waterfall_card",
	"alert",
]);

function normalizeBlockType(type: string): string {
	return String(type).trim().toLowerCase().replace(/-/g, "_");
}

/**
 * Keeps only the first visual block; drops later metric_card + sector_gauge (etc.)
 * so the UI never stacks multiple cards from one reply.
 */
function keepFirstVisualBlockOnly(blocks: ResponseBlock[]): ResponseBlock[] {
	let seenVisual = false;
	const out: ResponseBlock[] = [];
	for (const block of blocks) {
		const t = normalizeBlockType(block.type);
		const isVisual = VISUAL_BLOCK_TYPES.has(t);

		if (isVisual) {
			if (seenVisual) {
				continue;
			}
			seenVisual = true;
		}
		out.push(block);
	}
	return out;
}

interface ChatResponse {
	final_answer: string;
	response_blocks: ResponseBlock[];
	alerts: Array<{ rubrique_key: string; status: string; label: string }>;
	session_id: string;
}

/**
 * Stream text gradually for a natural typing effect.
 * Streams word by word with realistic delays.
 */
async function* streamText(text: string): AsyncGenerator<string> {
	const words = text.split(/(\s+)/); // Split by whitespace, keeping the spaces
	let accumulatedText = "";
	
	for (let i = 0; i < words.length; i++) {
		const word = words[i];
		accumulatedText += word;
		
		// Yield after each word (including spaces)
		if (word.trim().length > 0 || i === words.length - 1) {
			yield accumulatedText;
			
			// Variable delay based on punctuation
			let delay = 50; // Base delay (50ms per word)
			
			if (/[.!?]$/.test(word.trim())) {
				delay = 200; // Longer pause after sentence
			} else if (/[,;:]$/.test(word.trim())) {
				delay = 100; // Medium pause after comma/semicolon
			}
			
			await new Promise(resolve => setTimeout(resolve, delay));
		}
	}
}

export const createFecAdapter = (sessionId: string): ChatModelAdapter => ({
	async *run({ messages, abortSignal }) {
		const lastUser = [...messages].reverse().find((m) => m.role === "user");
		const text =
			lastUser?.content
				.filter((p): p is { type: "text"; text: string } => p.type === "text")
				.map((p) => p.text)
				.join(" ") ?? "";

		const res = await fetch("http://localhost:8000/chat", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ message: text, session_id: sessionId }),
			signal: abortSignal,
		});

		if (!res.ok) {
			const err = await res.json().catch(() => ({}));
			throw new Error(
				(err as { detail?: string }).detail ?? `Backend error ${res.status}`,
			);
		}

		const data: ChatResponse = await res.json();
		const blocks = keepFirstVisualBlockOnly(data.response_blocks ?? []);

		// Each response_block becomes a tool-call part with its result included inline.
		// The toolkit (type: "backend") renders each block from `result`.
		const blockParts = blocks.map((block, i) => {
			const key = normalizeBlockType(block.type);
			const toolName = `show_${key}`;
			return {
				type: "tool-call" as const,
				toolCallId: `block-${i}`,
				toolName,
				args: block,
				argsText: JSON.stringify(block),
				result: block,
			};
		});

		// Stream the text gradually
		if (data.final_answer) {
			for await (const chunk of streamText(data.final_answer)) {
				yield {
					content: [
						{ type: "text" as const, text: chunk },
					],
				};
			}
			
			// Final yield with all content including tool calls
			yield {
				content: [
					{ type: "text" as const, text: data.final_answer },
					...blockParts,
				],
			};
		} else {
			// No text, just yield the tool calls
			yield {
				content: blockParts,
			};
		}
	},
});
