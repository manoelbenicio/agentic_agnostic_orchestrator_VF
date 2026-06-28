"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import {
  Bot,
  Brain,
  Copy,
  Loader2,
  MessageSquare,
  RotateCcw,
  Send,
  Terminal,
  Trash2,
  UserRound,
} from "lucide-react";

import { api } from "@/lib/api-client";
import type { ChatCompletionRequest, ChatMessage } from "@/lib/api-types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { PageHeader } from "@/components/page-kit";

type ConsoleMessage = ChatMessage & {
  id: string;
  createdAt: string;
  status?: "ok" | "error" | "local";
  traceId?: string;
};

type RuntimeMode = "socket" | "terminal";

const defaultSystemPrompt =
  "You are the AOP runtime assistant. Keep answers operational, precise, and scoped to the current control-plane context.";

const modelOptions = [
  { value: "glm-5.2", label: "GLM-5.2" },
  { value: "gpt-5-codex", label: "GPT-5 Codex" },
  { value: "claude-opus-4.5", label: "Claude Opus 4.5" },
  { value: "gemini-3-pro", label: "Gemini 3 Pro" },
];

const quickPrompts = [
  "Summarize current operational risk.",
  "Draft a dispatch prompt for a backend agent.",
  "Explain the last failed health check.",
  "Create a concise QA checklist.",
];

function newId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function nowLabel() {
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date());
}

function responseContent(response: Awaited<ReturnType<typeof api.chatCompletion>>) {
  return response.choices?.[0]?.message?.content ?? response.message?.content ?? response.content ?? "";
}

function localFallback(prompt: string, model: string, runtimeId: string) {
  return [
    `Gateway indisponivel para ${model} em ${runtimeId}.`,
    "",
    "Payload preparado para reenvio:",
    prompt,
  ].join("\n");
}

export function ChatConsole() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [projectId, setProjectId] = useState("project-a");
  const [runtimeId, setRuntimeId] = useState("runtime-local");
  const [model, setModel] = useState("glm-5.2");
  const [mode, setMode] = useState<RuntimeMode>("socket");
  const [temperature, setTemperature] = useState(0.2);
  const [systemPrompt, setSystemPrompt] = useState(defaultSystemPrompt);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ConsoleMessage[]>([
    {
      id: "assistant-seed",
      role: "assistant",
      content: "Console pronto.",
      createdAt: nowLabel(),
      status: "local",
    },
  ]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);

  const requestMessages = useMemo<ChatMessage[]>(() => {
    const history = messages
      .filter((message) => message.role === "user" || message.role === "assistant")
      .map(({ role, content }) => ({ role, content }));
    return [{ role: "system", content: systemPrompt }, ...history];
  }, [messages, systemPrompt]);

  const tokenEstimate = useMemo(() => {
    const chars = requestMessages.reduce((total, message) => total + message.content.length, 0) + draft.length;
    return Math.max(1, Math.ceil(chars / 4));
  }, [draft.length, requestMessages]);

  async function sendMessage(event?: FormEvent) {
    event?.preventDefault();
    const prompt = draft.trim();
    if (!prompt || sending) return;

    const userMessage: ConsoleMessage = {
      id: newId("user"),
      role: "user",
      content: prompt,
      createdAt: nowLabel(),
    };
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setSending(true);
    setError(null);

    const payload: ChatCompletionRequest = {
      tenant_id: tenantId,
      project_id: projectId,
      runtime_id: runtimeId,
      model,
      messages: [...requestMessages, { role: "user", content: prompt }],
      temperature,
      max_tokens: 1200,
      stream: false,
      metadata: {
        source: "aop-web-chat-console",
        operation_mode: mode,
      },
    };

    try {
      const response = await api.chatCompletion(payload);
      const content = responseContent(response);
      setMessages((current) => [
        ...current,
        {
          id: response.id ?? newId("assistant"),
          role: "assistant",
          content: content || "Resposta vazia do gateway.",
          createdAt: nowLabel(),
          status: "ok",
          traceId: response.trace_id,
        },
      ]);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      setError(message);
      setMessages((current) => [
        ...current,
        {
          id: newId("assistant-error"),
          role: "assistant",
          content: localFallback(prompt, model, runtimeId),
          createdAt: nowLabel(),
          status: "error",
        },
      ]);
    } finally {
      setSending(false);
      requestAnimationFrame(() => draftRef.current?.focus());
    }
  }

  function resetConversation() {
    setMessages([
      {
        id: "assistant-reset",
        role: "assistant",
        content: "Console reiniciado.",
        createdAt: nowLabel(),
        status: "local",
      },
    ]);
    setError(null);
    setDraft("");
  }

  async function copyTranscript() {
    const transcript = messages
      .map((message) => `[${message.createdAt}] ${message.role.toUpperCase()}: ${message.content}`)
      .join("\n\n");
    await navigator.clipboard.writeText(transcript);
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Chat Console"
        description="Console operacional para conversas com runtimes e modelos conectados ao control-plane."
        icon={MessageSquare}
        eyebrow="AI Agents"
        actions={
          <>
            <Button type="button" variant="outline" onClick={copyTranscript}>
              <Copy data-icon="inline-start" />
              Transcript
            </Button>
            <Button type="button" variant="subtle" onClick={resetConversation}>
              <RotateCcw data-icon="inline-start" />
              Reset
            </Button>
          </>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Card className="min-h-[640px] overflow-hidden">
          <CardHeader className="border-b border-border">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Terminal className="size-4 text-muted-foreground" />
                  Runtime Session
                </CardTitle>
                <CardDescription>
                  {model} · {runtimeId} · {mode}
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={error ? "warning" : "success"}>
                  {error ? "degraded" : "ready"}
                </Badge>
                <Badge variant="outline">{tokenEstimate} est. tokens</Badge>
              </div>
            </div>
          </CardHeader>

          <CardContent className="flex min-h-[560px] flex-col p-0">
            <div className="flex max-h-[430px] min-h-[430px] flex-col gap-3 overflow-y-auto p-4">
              {messages.map((message) => (
                <article
                  key={message.id}
                  className={cn(
                    "flex gap-3 rounded-lg border p-3",
                    message.role === "user"
                      ? "border-primary/30 bg-primary/5"
                      : "border-border bg-background",
                  )}
                >
                  <div
                    className={cn(
                      "flex size-8 shrink-0 items-center justify-center rounded-md",
                      message.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground",
                    )}
                  >
                    {message.role === "user" ? <UserRound /> : <Bot />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold uppercase text-muted-foreground">
                        {message.role}
                      </span>
                      <span className="text-xs text-muted-foreground">{message.createdAt}</span>
                      {message.status && (
                        <Badge
                          variant={
                            message.status === "ok"
                              ? "success"
                              : message.status === "error"
                                ? "warning"
                                : "secondary"
                          }
                        >
                          {message.status}
                        </Badge>
                      )}
                      {message.traceId && <Badge variant="outline">{message.traceId}</Badge>}
                    </div>
                    <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6 text-foreground">
                      {message.content}
                    </pre>
                  </div>
                </article>
              ))}
              {sending && (
                <div className="flex items-center gap-2 rounded-lg border border-border bg-muted px-3 py-2 text-sm text-muted-foreground">
                  <Loader2 className="animate-spin" />
                  Gerando resposta
                </div>
              )}
            </div>

            <form onSubmit={sendMessage} className="border-t border-border p-4">
              {error && (
                <div className="mb-3 rounded-md border border-warning bg-warning/10 px-3 py-2 text-sm text-foreground">
                  {error}
                </div>
              )}
              <div className="flex flex-col gap-3">
                <textarea
                  ref={draftRef}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                      void sendMessage();
                    }
                  }}
                  placeholder="Mensagem para o runtime"
                  className="aop-focus min-h-28 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground shadow-sm placeholder:text-muted-foreground"
                />
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex flex-wrap gap-2">
                    {quickPrompts.map((prompt) => (
                      <Button
                        key={prompt}
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setDraft(prompt)}
                      >
                        {prompt}
                      </Button>
                    ))}
                  </div>
                  <Button type="submit" disabled={!draft.trim() || sending}>
                    {sending ? <Loader2 className="animate-spin" /> : <Send data-icon="inline-start" />}
                    Send
                  </Button>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>

        <aside className="flex flex-col gap-5">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Brain className="size-4 text-muted-foreground" />
                Session Controls
              </CardTitle>
              <CardDescription>Runtime, model and request envelope.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Model
                <Select value={model} onChange={(event) => setModel(event.target.value)}>
                  {modelOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Runtime
                <Input value={runtimeId} onChange={(event) => setRuntimeId(event.target.value)} />
              </label>
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Tenant
                <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} />
              </label>
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Project
                <Input value={projectId} onChange={(event) => setProjectId(event.target.value)} />
              </label>
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Mode
                <Select value={mode} onChange={(event) => setMode(event.target.value as RuntimeMode)}>
                  <option value="socket">socket</option>
                  <option value="terminal">terminal</option>
                </Select>
              </label>
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Temperature
                <Input
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  value={temperature}
                  onChange={(event) => setTemperature(Number(event.target.value))}
                />
              </label>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>System Prompt</CardTitle>
              <CardDescription>Base instruction sent with each request.</CardDescription>
            </CardHeader>
            <CardContent>
              <textarea
                value={systemPrompt}
                onChange={(event) => setSystemPrompt(event.target.value)}
                className="aop-focus min-h-44 w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground shadow-sm"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="mt-3"
                onClick={() => setSystemPrompt(defaultSystemPrompt)}
              >
                <Trash2 data-icon="inline-start" />
                Restore default
              </Button>
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
