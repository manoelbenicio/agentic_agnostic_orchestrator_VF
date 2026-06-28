"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Settings,
  Users,
  BookOpen,
  Github,
  Blocks,
  User,
  SlidersHorizontal,
  BellRing,
  Key,
  FlaskConical,
  Save,
  Plus,
  Trash2,
  Copy,
  Check,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8090";

const TABS = [
  { id: "general", label: "General", icon: Settings },
  { id: "members", label: "Members", icon: Users },
  { id: "repositories", label: "Repositories", icon: BookOpen },
  { id: "github", label: "GitHub", icon: Github },
  { id: "integrations", label: "Integrations", icon: Blocks },
  { id: "profile", label: "Profile", icon: User },
  { id: "preferences", label: "Preferences", icon: SlidersHorizontal },
  { id: "notifications", label: "Notifications", icon: BellRing },
  { id: "api-tokens", label: "API Tokens", icon: Key },
  { id: "labs", label: "Labs", icon: FlaskConical },
] as const;

export function SettingsView() {
  const [activeTab, setActiveTab] = useState<string>("general");

  return (
    <div className="flex h-full flex-col gap-6 lg:flex-row">
      <aside className="w-full lg:w-64 shrink-0">
        <h1 className="mb-4 text-2xl font-semibold tracking-tight">Configurações</h1>
        <nav className="flex flex-row lg:flex-col gap-1 overflow-x-auto pb-2 lg:pb-0">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-3 whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors",
                activeTab === tab.id
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-foreground"
              )}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="flex-1 min-w-0 aop-fade-in">
        <div className="h-full rounded-xl border border-border bg-card p-6 shadow-sm">
          <TabContent activeTab={activeTab} />
        </div>
      </main>
    </div>
  );
}

/* ── General Settings Tab ───────────────────────────────────────── */

function GeneralSettingsTab() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workspaceName, setWorkspaceName] = useState("");
  const [theme, setTheme] = useState("");

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/settings?tenant_id=tenant-a`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setWorkspaceName(data.settings?.workspace_name ?? "");
      setTheme(data.settings?.theme ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: "tenant-a",
          settings: { workspace_name: workspaceName, theme },
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingSkeleton />;

  return (
    <div className="space-y-6 aop-fade-in">
      <div>
        <h2 className="text-lg font-semibold">General Settings</h2>
        <p className="text-sm text-muted-foreground">Gerencie as configurações gerais do workspace.</p>
      </div>
      {error && <ErrorBanner message={error} />}
      <Card className="shadow-none border-border">
        <CardHeader>
          <CardTitle className="text-base">Nome do Workspace</CardTitle>
          <CardDescription>O nome visível do seu tenant atual.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Input
            value={workspaceName}
            onChange={(e) => setWorkspaceName(e.target.value)}
            placeholder="Nome do workspace"
          />
          <div>
            <label className="block text-sm font-medium mb-1">Tema</label>
            <Input
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              placeholder="dark / light / system"
            />
          </div>
          <Button className="gap-2" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Salvar
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

/* ── Profile Tab ────────────────────────────────────────────────── */

function ProfileTab() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");

  const fetchProfile = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/settings/profile?tenant_id=tenant-a`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setDisplayName(data.profile?.display_name ?? "");
      setEmail(data.profile?.email ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load profile");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchProfile(); }, [fetchProfile]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/settings/profile`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: "tenant-a",
          profile: { display_name: displayName, email },
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save profile");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingSkeleton />;

  return (
    <div className="space-y-6 aop-fade-in">
      <div>
        <h2 className="text-lg font-semibold">Profile</h2>
        <p className="text-sm text-muted-foreground">Informações de perfil do tenant.</p>
      </div>
      {error && <ErrorBanner message={error} />}
      <Card className="shadow-none border-border">
        <CardHeader>
          <CardTitle className="text-base">Perfil</CardTitle>
          <CardDescription>Nome e email do tenant.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Nome</label>
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Seu nome" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Email</label>
            <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email@example.com" />
          </div>
          <Button className="gap-2" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Salvar
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

/* ── Integrations Tab ───────────────────────────────────────────── */

interface Integration {
  integration_id: string;
  tenant_id: string;
  name: string;
  provider: string;
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

function IntegrationsTab() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [provider, setProvider] = useState("");
  const [creating, setCreating] = useState(false);

  const fetchIntegrations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/settings/integrations?tenant_id=tenant-a`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setIntegrations(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load integrations");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchIntegrations(); }, [fetchIntegrations]);

  const handleCreate = async () => {
    if (!name || !provider) return;
    setCreating(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/settings/integrations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: "tenant-a", name, provider }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setName("");
      setProvider("");
      setShowForm(false);
      await fetchIntegrations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create integration");
    } finally {
      setCreating(false);
    }
  };

  if (loading) return <LoadingSkeleton />;

  return (
    <div className="space-y-6 aop-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Integrations</h2>
          <p className="text-sm text-muted-foreground">Integrações externas configuradas.</p>
        </div>
        <Button className="gap-2" size="sm" onClick={() => setShowForm(!showForm)}>
          <Plus className="h-4 w-4" />
          Nova Integração
        </Button>
      </div>
      {error && <ErrorBanner message={error} />}
      {showForm && (
        <Card className="shadow-none border-border">
          <CardContent className="pt-6 space-y-4">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome (ex: Slack)" />
            <Input value={provider} onChange={(e) => setProvider(e.target.value)} placeholder="Provider (ex: slack)" />
            <Button className="gap-2" onClick={handleCreate} disabled={creating}>
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Criar
            </Button>
          </CardContent>
        </Card>
      )}
      {integrations.length === 0 ? (
        <EmptyState
          icon={Blocks}
          title="Nenhuma integração"
          description="Nenhuma integração configurada. Adicione uma nova integração."
        />
      ) : (
        <div className="space-y-3">
          {integrations.map((intg) => (
            <Card key={intg.integration_id} className="shadow-none border-border">
              <CardContent className="flex items-center justify-between py-4">
                <div>
                  <p className="font-medium">{intg.name}</p>
                  <p className="text-sm text-muted-foreground">{intg.provider}</p>
                </div>
                <span className={cn(
                  "text-xs px-2 py-1 rounded-full",
                  intg.enabled ? "bg-green-500/10 text-green-500" : "bg-red-500/10 text-red-500"
                )}>
                  {intg.enabled ? "Ativo" : "Desativado"}
                </span>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── API Tokens Tab ─────────────────────────────────────────────── */

interface ApiToken {
  token_id: string;
  tenant_id: string;
  name: string;
  prefix: string;
  created_at: string | null;
  expires_at: string | null;
  raw_token?: string;
}

function ApiTokensTab() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tokens, setTokens] = useState<ApiToken[]>([]);
  const [newTokenName, setNewTokenName] = useState("");
  const [creating, setCreating] = useState(false);
  const [newlyCreatedToken, setNewlyCreatedToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const fetchTokens = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/settings/api-tokens?tenant_id=tenant-a`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setTokens(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tokens");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTokens(); }, [fetchTokens]);

  const handleCreate = async () => {
    if (!newTokenName) return;
    setCreating(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/settings/api-tokens`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: "tenant-a", name: newTokenName }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setNewlyCreatedToken(data.raw_token);
      setNewTokenName("");
      await fetchTokens();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create token");
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (tokenId: string) => {
    setError(null);
    try {
      const res = await fetch(`${apiBase}/settings/api-tokens/${tokenId}`, { method: "DELETE" });
      if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
      await fetchTokens();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke token");
    }
  };

  const handleCopy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
  };

  if (loading) return <LoadingSkeleton />;

  return (
    <div className="space-y-6 aop-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">API Tokens</h2>
          <p className="text-sm text-muted-foreground">Tokens para acesso programático à API.</p>
        </div>
      </div>
      {error && <ErrorBanner message={error} />}
      {newlyCreatedToken && (
        <Card className="shadow-none border-green-500/30 bg-green-500/5">
          <CardContent className="py-4 space-y-2">
            <p className="text-sm font-medium text-green-600">Token criado com sucesso! Copie agora — ele não será exibido novamente.</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs bg-muted px-3 py-2 rounded-md font-mono break-all">{newlyCreatedToken}</code>
              <Button size="sm" variant="outline" className="gap-1" onClick={() => handleCopy(newlyCreatedToken)}>
                {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                {copied ? "Copiado" : "Copiar"}
              </Button>
            </div>
            <Button size="sm" variant="ghost" onClick={() => setNewlyCreatedToken(null)} className="text-xs">
              Fechar
            </Button>
          </CardContent>
        </Card>
      )}
      <Card className="shadow-none border-border">
        <CardContent className="pt-6 space-y-3">
          <div className="flex gap-2">
            <Input
              value={newTokenName}
              onChange={(e) => setNewTokenName(e.target.value)}
              placeholder="Nome do token (ex: CI/CD Pipeline)"
              className="flex-1"
            />
            <Button className="gap-2" onClick={handleCreate} disabled={creating || !newTokenName}>
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Gerar Token
            </Button>
          </div>
        </CardContent>
      </Card>
      {tokens.length === 0 ? (
        <EmptyState
          icon={Key}
          title="Nenhum token gerado"
          description="Você ainda não possui tokens de API. Gere um novo token para se autenticar programaticamente."
        />
      ) : (
        <div className="space-y-3">
          {tokens.map((token) => (
            <Card key={token.token_id} className="shadow-none border-border">
              <CardContent className="flex items-center justify-between py-4">
                <div>
                  <p className="font-medium">{token.name}</p>
                  <p className="text-xs text-muted-foreground font-mono">
                    {token.prefix}...
                    {token.created_at && ` · Criado em ${new Date(token.created_at).toLocaleDateString("pt-BR")}`}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="gap-1 text-destructive hover:text-destructive"
                  onClick={() => handleRevoke(token.token_id)}
                >
                  <Trash2 className="h-3 w-3" />
                  Revogar
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Shared Components ──────────────────────────────────────────── */

function LoadingSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-6 w-1/4 rounded bg-muted"></div>
      <div className="h-24 rounded-lg bg-muted/50"></div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
      <AlertCircle className="h-4 w-4 shrink-0" />
      {message}
    </div>
  );
}

/* ── Tab Content Router ─────────────────────────────────────────── */

function TabContent({ activeTab }: { activeTab: string }) {
  if (activeTab === "general") return <GeneralSettingsTab />;
  if (activeTab === "profile") return <ProfileTab />;
  if (activeTab === "integrations") return <IntegrationsTab />;
  if (activeTab === "api-tokens") return <ApiTokensTab />;

  // Tabs without dedicated API endpoints — real empty state
  const activeTabConfig = TABS.find((t) => t.id === activeTab);

  return (
    <div className="space-y-6 aop-fade-in">
      <div>
        <h2 className="text-lg font-semibold">{activeTabConfig?.label}</h2>
        <p className="text-sm text-muted-foreground">Configurações para {activeTabConfig?.label.toLowerCase()}.</p>
      </div>
      <EmptyState
        icon={activeTabConfig?.icon}
        title={`Sem dados para ${activeTabConfig?.label}`}
        description={`Não foi possível carregar as informações ou a API não retornou dados para ${activeTabConfig?.label}.`}
      />
    </div>
  );
}
