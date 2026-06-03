"use client";

import { useState } from "react";
import { chatSuggestionChips, scriptedConversations } from "@/lib/studio/scripted-chat";
import type { ChatTurn } from "@/lib/studio/scripted-chat";

export function IterationChat() {
  const [transcript, setTranscript] = useState<ChatTurn[]>([
    { role: "agent", message: "Want to tweak anything? Try one of these:" },
  ]);

  const choose = (id: string) => {
    const turns = scriptedConversations[id];
    if (!turns) return;
    setTranscript(t => [...t, ...turns]);
  };

  return (
    <div className="bg-stone-50 border border-stone-200 rounded-md p-5 space-y-5">
      <div className="text-xs uppercase tracking-wider text-amber-700/90">Iterate with the agent</div>

      <ul className="space-y-3">
        {transcript.map((turn, i) => (
          <li key={i} className={turn.role === "agent" ? "" : "flex justify-end"}>
            <div
              className={`inline-block max-w-[85%] rounded-md px-4 py-2.5 text-sm ${
                turn.role === "agent"
                  ? "bg-white border border-stone-200 text-stone-700"
                  : "bg-amber-50 border border-amber-200 text-stone-900"
              }`}
            >
              {turn.message}
            </div>
            {turn.alternates && (
              <div className="grid sm:grid-cols-3 gap-2 mt-3 w-full">
                {turn.alternates.map(a => (
                  <div key={a.tag} className="bg-white border border-stone-200 rounded-md p-3 text-xs space-y-2">
                    <div className="font-medium text-stone-900 leading-snug">{a.description}</div>
                    <div className="text-stone-500">₹{a.priceInr.toLocaleString("en-IN")}</div>
                    <button className="text-amber-700 text-xs hover:underline font-medium">Pick this →</button>
                  </div>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>

      <div className="border-t border-stone-200 pt-4 space-y-3">
        <div className="text-xs text-stone-500">Suggested:</div>
        <div className="flex flex-wrap gap-2">
          {chatSuggestionChips.map(c => (
            <button
              key={c.id}
              type="button"
              onClick={() => choose(c.id)}
              className="text-xs border border-stone-300 text-stone-700 hover:border-amber-700 hover:text-amber-700 rounded-full px-3 py-1.5 transition bg-white"
            >
              {c.label}
            </button>
          ))}
        </div>
        <input
          type="text"
          placeholder="Or type your own…"
          className="w-full bg-white border border-stone-200 rounded-md px-3 py-2 text-sm placeholder-stone-400 text-stone-700 focus:border-stone-400 outline-none mt-1"
        />
        <p className="text-xs text-stone-400">Prototype: only the chips trigger scripted responses for now.</p>
      </div>
    </div>
  );
}
