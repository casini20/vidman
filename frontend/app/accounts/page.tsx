"use client";

import { useEffect, useState } from "react";
import { api, Account } from "@/lib/api";
import {
  Plus, Trash2, RefreshCw, Users, Heart, UserCheck, Eye, X, ChevronDown, ChevronUp
} from "lucide-react";

type Platform = "tiktok" | "instagram" | "twitter";

const PLATFORM_META: Record<Platform, {
  label: string; color: string; border: string; bg: string;
  accentHex: string; comingSoon?: boolean;
}> = {
  tiktok:    { label: "TikTok",      color: "text-[#FF2D55]", border: "border-[#FF2D55]", bg: "bg-[#FF2D55]", accentHex: "#FF2D55" },
  instagram: { label: "Instagram",   color: "text-[#E1306C]", border: "border-[#E1306C]", bg: "bg-[#E1306C]", accentHex: "#E1306C" },
  twitter:   { label: "X / Twitter", color: "text-[#1D9BF0]", border: "border-[#1D9BF0]", bg: "bg-[#1D9BF0]", accentHex: "#1D9BF0", comingSoon: true },
};

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [activePlatform, setActivePlatform] = useState<Platform | null>(null);
  const [cookies, setCookies] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");
  const [syncing, setSyncing] = useState<string | null>(null);
  const [showInstructions, setShowInstructions] = useState(false);

  const load = () =>
    api.accounts.list().then(setAccounts).finally(() => setLoading(false));

  useEffect(() => { load(); }, []);

  const connect = async () => {
    setConnecting(true);
    setError("");
    try {
      await api.accounts.add(cookies, activePlatform!);
      setCookies("");
      setActivePlatform(null);
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setConnecting(false);
    }
  };

  const remove = async (id: string, username: string) => {
    if (!confirm(`Remove @${username}?`)) return;
    await api.accounts.remove(id);
    setAccounts((prev) => prev.filter((a) => a.id !== id));
  };

  const sync = async (id: string) => {
    setSyncing(id);
    try {
      const updated = await api.accounts.sync(id);
      setAccounts((prev) => prev.map((a) => (a.id === id ? { ...a, ...updated } : a)));
    } catch (e: any) {
      alert(`Sync failed: ${e.message}`);
    } finally {
      setSyncing(null);
    }
  };

  const platformAccounts = (p: Platform) =>
    accounts.filter((a) => (a.platform as Platform) === p || (!a.platform && p === "tiktok"));

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Accounts</h1>
        <p className="text-muted text-sm mt-1">Connect your social media accounts to post everywhere at once.</p>
      </div>

      {/* Platform sections */}
      <div className="space-y-8">
        {(["tiktok", "instagram", "twitter"] as Platform[]).map((platform) => {
          const meta = PLATFORM_META[platform];
          const platAccounts = platformAccounts(platform);

          return (
            <div key={platform}>
              {/* Section header */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <span
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ background: meta.accentHex }}
                  />
                  <h2 className={`font-semibold text-sm uppercase tracking-widest ${meta.color}`}>
                    {meta.label}
                  </h2>
                  {meta.comingSoon && (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-surface text-muted border border-border">
                      Coming soon
                    </span>
                  )}
                  <span className="text-muted text-xs">{platAccounts.length} connected</span>
                </div>
                {!meta.comingSoon && (
                  <button
                    onClick={() => { setActivePlatform(platform); setError(""); setCookies(""); }}
                    className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border transition
                      ${meta.color} ${meta.border} border-opacity-40 hover:border-opacity-80 bg-opacity-0 hover:bg-opacity-10 ${meta.bg}`}
                  >
                    <Plus size={13} />
                    Connect
                  </button>
                )}
              </div>

              {/* Divider */}
              <div className="h-px bg-border mb-3" style={{ background: `linear-gradient(to right, ${meta.accentHex}33, transparent)` }} />

              {/* Account list */}
              {loading ? (
                <p className="text-muted text-sm py-4">Loading…</p>
              ) : platAccounts.length === 0 ? (
                <div className="bg-card border border-border rounded-xl p-6 text-center">
                  <p className="text-muted text-sm">
                    {meta.comingSoon
                      ? `${meta.label} posting is coming soon.`
                      : <>No {meta.label} accounts connected. <button onClick={() => { setActivePlatform(platform); setError(""); setCookies(""); }} className={`${meta.color} hover:underline`}>Connect one</button>.</>}
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {platAccounts.map((acc) => (
                    <div key={acc.id} className="bg-card border border-border rounded-xl p-4 flex items-center gap-4 tt-glow">
                      {/* Avatar */}
                      <div className="w-10 h-10 rounded-full bg-surface border border-border flex items-center justify-center flex-shrink-0 overflow-hidden">
                        {acc.avatar_url
                          // eslint-disable-next-line @next/next/no-img-element
                          ? <img src={acc.avatar_url} alt={acc.username} className="w-full h-full object-cover" />
                          : <span className="text-sm font-bold text-muted">{acc.username.charAt(0).toUpperCase()}</span>}
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold truncate">{acc.display_name || `@${acc.username}`}</p>
                        <p className="text-muted text-xs">@{acc.username}</p>
                      </div>

                      {/* Stats */}
                      <div className="hidden sm:flex items-center gap-4 text-sm">
                        <div className="flex items-center gap-1.5 text-muted">
                          <Users size={12} />
                          <span className="font-mono text-xs">{acc.followers}</span>
                          <span className="text-xs">followers</span>
                        </div>
                        <div className="flex items-center gap-1.5 text-muted">
                          <UserCheck size={12} />
                          <span className="font-mono text-xs">{acc.following}</span>
                        </div>
                        <div className="flex items-center gap-1.5 text-muted">
                          <Heart size={12} />
                          <span className="font-mono text-xs">{acc.likes}</span>
                        </div>
                        <div className="flex items-center gap-1.5 text-muted">
                          <Eye size={12} />
                          <span className="font-mono text-xs">{acc.views ?? "0"}</span>
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <button
                          onClick={() => sync(acc.id)}
                          disabled={syncing === acc.id}
                          className="p-2 text-muted hover:text-cyan transition rounded-lg hover:bg-surface"
                          title="Sync stats"
                        >
                          <RefreshCw size={14} className={syncing === acc.id ? "animate-spin" : ""} />
                        </button>
                        <button
                          onClick={() => remove(acc.id, acc.username)}
                          className="p-2 text-muted hover:text-error transition rounded-lg hover:bg-surface"
                          title="Remove"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Connect modal */}
      {activePlatform && (
        <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-4">
          <div className="bg-surface border border-border rounded-2xl w-full max-w-lg shadow-2xl">
            {/* Modal header */}
            <div className="flex items-center justify-between p-6 border-b border-border">
              <div className="flex items-center gap-2">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ background: PLATFORM_META[activePlatform].accentHex }}
                />
                <h2 className="font-semibold">Connect {PLATFORM_META[activePlatform].label} account</h2>
              </div>
              <button
                onClick={() => { setActivePlatform(null); setError(""); setCookies(""); }}
                className="text-muted hover:text-white transition"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-6 space-y-4">
              {/* Instructions toggle */}
              <div className="bg-card border border-border rounded-xl overflow-hidden">
                <button
                  onClick={() => setShowInstructions(!showInstructions)}
                  className="w-full flex items-center justify-between px-4 py-3 text-sm hover:bg-surface transition"
                >
                  <span className={PLATFORM_META[activePlatform].color}>How to export cookies</span>
                  {showInstructions ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
                {showInstructions && (
                  <div className="px-4 pb-4 text-sm text-muted space-y-1.5 border-t border-border pt-3">
                    <p><span className="text-white font-medium">1.</span> Install <a href="https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm" target="_blank" rel="noopener noreferrer" className="text-cyan underline">Cookie-Editor</a> for Chrome.</p>
                    <p><span className="text-white font-medium">2.</span> Log into {PLATFORM_META[activePlatform].label} in your browser.</p>
                    <p><span className="text-white font-medium">3.</span> Click Cookie-Editor → <strong className="text-white">Export as JSON</strong>.</p>
                    <p><span className="text-white font-medium">4.</span> Paste below and connect.</p>
                    <p className="text-xs pt-1">⚠️ Never share your cookies — they give full account access.</p>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Paste cookie JSON</label>
                <textarea
                  value={cookies}
                  onChange={(e) => setCookies(e.target.value)}
                  placeholder='[{"name":"sessionid","value":"...","domain":"..."}]'
                  className="w-full h-36 bg-bg border border-border rounded-lg p-3 text-xs font-mono text-white resize-none focus:outline-none focus:border-cyan placeholder-muted"
                />
              </div>

              {error && (
                <p className="text-error text-sm bg-error bg-opacity-10 border border-error border-opacity-30 rounded-lg px-3 py-2">{error}</p>
              )}

              <button
                onClick={connect}
                disabled={!cookies.trim() || connecting}
                className={`w-full disabled:opacity-50 disabled:cursor-not-allowed transition text-white py-2.5 rounded-lg text-sm font-semibold
                  ${PLATFORM_META[activePlatform].bg} hover:opacity-90`}
              >
                {connecting ? "Verifying session…" : `Connect ${PLATFORM_META[activePlatform].label} account`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}