"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Send, User } from "lucide-react";
import { v4 as uuidv4 } from "uuid";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || ""; // local dev can set http://localhost:8000

export default function Twin() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string>("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () =>
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });

  useEffect(() => scrollToBottom(), [messages]);

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userText = input;
    const userMessage: Message = {
      id: uuidv4(),
      role: "user",
      content: userText,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userText,
          session_id: sessionId || undefined,
        }),
      });

      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || "Request failed");
      }

      const data = await res.json();

      if (!sessionId) setSessionId(data.session_id);

      const assistantMessage: Message = {
        id: uuidv4(),
        role: "assistant",
        content: data.response,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (e) {
      const assistantMessage: Message = {
        id: uuidv4(),
        role: "assistant",
        content:
          "Sorry — I hit an error. Check server logs / env vars and try again.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } finally {
      setIsLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  };

  const onKeyDown: React.KeyboardEventHandler<HTMLInputElement> = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-50 rounded-2xl shadow-lg overflow-hidden border border-gray-200">
      <div className="bg-gradient-to-r from-slate-700 to-slate-800 text-white p-4">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Bot className="w-6 h-6" />
          Digital Twin Chat
        </h2>
        <p className="text-sm text-slate-300 mt-1">
          FastAPI + Next.js (static) on App Runner
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 mt-10">
            <Bot className="w-12 h-12 mx-auto mb-3 text-gray-400" />
            <p className="text-lg">Hello! I&apos;m your Digital Twin.</p>
            <p className="text-sm mt-2">Ask me anything!</p>
          </div>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex gap-3 ${
              m.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            {m.role === "assistant" && (
              <div className="w-8 h-8 bg-slate-700 rounded-full flex items-center justify-center shrink-0">
                <Bot className="w-5 h-5 text-white" />
              </div>
            )}

            <div
              className={`max-w-[75%] rounded-2xl px-4 py-3 ${
                m.role === "user"
                  ? "bg-slate-700 text-white"
                  : "bg-white border border-gray-200 text-gray-800"
              }`}
            >
              <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
              <p
                className={`text-xs mt-2 ${
                  m.role === "user" ? "text-slate-300" : "text-gray-500"
                }`}
              >
                {m.timestamp.toLocaleTimeString()}
              </p>
            </div>

            {m.role === "user" && (
              <div className="w-8 h-8 bg-gray-600 rounded-full flex items-center justify-center shrink-0">
                <User className="w-5 h-5 text-white" />
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-3 justify-start">
            <div className="w-8 h-8 bg-slate-700 rounded-full flex items-center justify-center shrink-0">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3">
              <div className="flex space-x-2">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-gray-200 p-4 bg-white">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Type your message..."
            disabled={isLoading}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-slate-600 focus:border-transparent text-gray-800"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isLoading}
            className="px-4 py-2 bg-slate-700 text-white rounded-xl hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            aria-label="Send"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
