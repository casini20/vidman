"use client";

import { useEffect, useState } from "react";
import { api, Account } from "@/lib/api";
import {
  Plus, Trash2, RefreshCw, Users, Heart, UserCheck, X, ChevronDown, ChevronUp
} from "lucide-react";

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [cookies, setCookies] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");
  const [syncing, setSyncing] = useState<string | null>(null);
  const [showInstructions, setShowInstructions] = useState(true);

  const load = () =>
    api.accounts.list().then(setAccounts).finally(() => setLoading(false));

  useEffect(() => { load(); }, []);

  const connect = async () => {
    setConnecting(true);
    setError("");
    try {
      await api.accounts.add(cookies);
      setCookies("");
      setShowModal(false);
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
      setAccounts((prev) =>
        prev.map((a) => (a.id === id ? { ...a, ...updated } : a))
      );
    } catch (e: any) {
      alert(`Sync failed: ${e.message}`);
    } finally {
      setSyncing(null);
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">Accounts</h1>
          <p className="text-muted text-sm mt-1">
            Connect your TikTok accounts using exported cookies.
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-red hover:bg-opacity-90 transition text-white px-4 py-2.5 rounded-lg text-sm font-semibold"
        >
          <Plus size={16} />
          Connect account
        </button>
      </div>

      {/* How-to banner */}
      <div className="bg-card border border-border rounded-xl mb-6 overflow-hidden">
        <button
          onClick={() => setShowInstructions(!showInstructions)}
          className="w-full flex items-center justify-between px-5 py-4 text-sm font-medium hover:bg-surface transition"
        >
          <span className="text-cyan">How to connect an account</span>
          {showInstructions ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
        {showInstructions && (
          <div className="px-5 pb-5 text-sm text-muted space-y-2 border-t border-border pt-4">
            <p>
              <span className="text-white font-medium">1.</span> Install the{" "}
              <a
                href="https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm"
                target="_blank"
                rel="noopener noreferrer"
                className="text-cyan underline"
              >
                Cookie-Editor
              </a>{" "}
              extension for Chrome or Firefox.
            </p>
            <p>
              <span className="text-white font-medium">2.</span> Open{" "}
              <a
                href="https://www.tiktok.com"
                target="_blank"
                rel="noopener noreferrer"
                className="text-cyan underline"
              >
                tiktok.com
              </a>{" "}
              and log into the account you want to add.
            </p>
            <p>
              <span className="text-white font-medium">3.</span> Click the Cookie-Editor icon →{" "}
              <strong className="text-white">Export</strong> →{" "}
              <strong className="text-white">Export as JSON</strong>. This copies the JSON to your clipboard.
            </p>
            <p>
              <span className="text-white font-medium">4.</span> Click{" "}
              <strong className="text-white">Connect account</strong> above and paste the JSON.
            </p>
            <p className="text-xs pt-1">
              ⚠️ Never share your cookies. They give full access to your account.
            </p>
          </div>
        )}
      </div>

      {/* Account list */}
      {loading ? (
        <p className="text-muted text-sm">Loading…</p>
      ) : accounts.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center">
          <Users size={36} className="text-muted mx-auto mb-4" />
          <p className="font-medium mb-1">No accounts connected</p>
          <p className="text-muted text-sm">
            Connect your first TikTok account to get started.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {accounts.map((acc) => (
            <div
              key={acc.id}
              className="bg-card border border-border rounded-xl p-5 flex items-center gap-4 tt-glow"
            >
              {/* Avatar */}
              <div className="w-12 h-12 rounded-full bg-surface border border-border flex items-center justify-center flex-shrink-0 overflow-hidden">
                {acc.avatar_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={acc.avatar_url} alt={acc.username} className="w-full h-full object-cover" />
                ) : (
                  <span className="text-lg font-bold text-muted">
                    {acc.username.charAt(0).toUpperCase()}
                  </span>
                )}
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <p className="font-semibold truncate">
                  {acc.display_name || `@${acc.username}`}
                </p>
                <p className="text-muted text-xs">@{acc.username}</p>
              </div>

              {/* Stats */}
              <div className="hidden sm:flex items-center gap-5 text-sm">
                <div className="flex items-center gap-1.5 text-muted">
                  <Users size={13} />
                  <span className="font-mono text-xs">{acc.followers}</span>
                  <span className="text-xs">followers</span>
                </div>
                <div className="flex items-center gap-1.5 text-muted">
                  <UserCheck size={13} />
                  <span className="font-mono text-xs">{acc.following}</span>
                </div>
                <div className="flex items-center gap-1.5 text-muted">
                  <Heart size={13} />
                  <span className="font-mono text-xs">{acc.likes}</span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={() => sync(acc.id)}
                  disabled={syncing === acc.id}
                  className="p-2 text-muted hover:text-cyan transition rounded-lg hover:bg-surface"
                  title="Sync stats"
                >
                  <RefreshCw
                    size={15}
                    className={syncing === acc.id ? "animate-spin" : ""}
                  />
                </button>
                <button
                  onClick={() => remove(acc.id, acc.username)}
                  className="p-2 text-muted hover:text-error transition rounded-lg hover:bg-surface"
                  title="Remove account"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Connect modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-4">
          <div className="bg-surface border border-border rounded-2xl w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between p-6 border-b border-border">
              <h2 className="font-semibold">Connect TikTok account</h2>
              <button
                onClick={() => { setShowModal(false); setError(""); setCookies(""); }}
                className="text-muted hover:text-white transition"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Paste cookie JSON
                </label>
                <textarea
                  value={cookies}
                  onChange={(e) => setCookies(e.target.value)}
                  placeholder='[{"name":"sessionid","value":"...","domain":".tiktok.com",...}]'
                  className="w-full h-40 bg-bg border border-border rounded-lg p-3 text-xs font-mono text-white resize-none focus:outline-none focus:border-cyan placeholder-muted"
                />
              </div>

              {error && (
                <p className="text-error text-sm bg-error bg-opacity-10 border border-error border-opacity-30 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              <button
                onClick={connect}
                disabled={!cookies.trim() || connecting}
                className="w-full bg-red hover:bg-opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition text-white py-2.5 rounded-lg text-sm font-semibold"
              >
                {connecting ? "Verifying session…" : "Connect account"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
