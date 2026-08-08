"use client";

import { useEffect, useRef, useState } from "react";
import { api, Account, Post } from "@/lib/api";
import {
  Upload, Film, CheckSquare, Square, X, Loader2, CheckCircle, XCircle, Sparkles
} from "lucide-react";

type Platform = "tiktok" | "instagram" | "twitter";

type PostResult = {
  post_id: string;
  accounts: { username: string; status: string; error_message?: string }[];
};

const GROQ_API_KEY = process.env.NEXT_PUBLIC_GROQ_API_KEY || "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";

const PLATFORM_META: Record<Platform, { label: string; color: string; bg: string; border: string; dot: string }> = {
  tiktok:    { label: "TikTok",    color: "text-[#FF2D55]", bg: "bg-[#FF2D55]", border: "border-[#FF2D55]", dot: "#FF2D55" },
  instagram: { label: "Instagram", color: "text-[#E1306C]", bg: "bg-[#E1306C]", border: "border-[#E1306C]", dot: "#E1306C" },
  twitter:   { label: "X / Twitter", color: "text-[#1D9BF0]", bg: "bg-[#1D9BF0]", border: "border-[#1D9BF0]", dot: "#1D9BF0" },
};

function PlatformDot({ platform }: { platform: Platform }) {
  return (
    <span
      className="inline-block w-2 h-2 rounded-full flex-shrink-0"
      style={{ background: PLATFORM_META[platform].dot }}
    />
  );
}

function PlatformBadge({ platform }: { platform: Platform }) {
  const m = PLATFORM_META[platform];
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${m.color} ${m.border} border-opacity-40 bg-opacity-10 ${m.bg}`}>
      {m.label}
    </span>
  );
}

export default function UploadPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [file, setFile] = useState<File | null>(null);
  const [caption, setCaption] = useState("");
  const [topic, setTopic] = useState("");
  const [generating, setGenerating] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [posting, setPosting] = useState(false);
  const [result, setResult] = useState<PostResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.accounts.list().then((accs) => {
      setAccounts(accs);
      setSelectedIds(new Set(accs.map((a) => a.id)));
    });
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const toggle = (id: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const togglePlatform = (platform: Platform) => {
    const platformAccounts = accounts.filter((a) => (a.platform as Platform) === platform);
    const allSelected = platformAccounts.every((a) => selectedIds.has(a.id));
    setSelectedIds((prev) => {
      const next = new Set(prev);
      platformAccounts.forEach((a) => allSelected ? next.delete(a.id) : next.add(a.id));
      return next;
    });
  };

  const toggleAll = () =>
    setSelectedIds((prev) =>
      prev.size === accounts.length ? new Set() : new Set(accounts.map((a) => a.id))
    );

  const onFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("video/")) setFile(f);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) setFile(f);
  };

  const generateCaption = async () => {
    if (!topic.trim()) return;
    setGenerating(true);
    try {
      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${GROQ_API_KEY}` },
        body: JSON.stringify({
          model: "llama-3.1-8b-instant",
          messages: [
            { role: "system", content: "You are a social media caption writer. Write short, punchy captions with relevant hashtags. Max 150 characters before hashtags. Include 5-8 trending hashtags. Return ONLY the caption text, nothing else." },
            { role: "user", content: `Write a social media caption for a video about: ${topic}` },
          ],
          max_tokens: 200,
          temperature: 0.9,
        }),
      });
      const data = await res.json();
      if (data.error) { alert("Groq error: " + data.error.message); return; }
      const generated = data.choices?.[0]?.message?.content?.trim();
      if (generated) setCaption(generated);
    } catch (e: any) {
      alert("Error: " + e.message);
    } finally {
      setGenerating(false);
    }
  };

  const pollPostStatus = (post_id: string) => {
    pollRef.current = setInterval(async () => {
      try {
        const post: Post = await api.posts.get(post_id);
        if (["completed", "partial", "failed"].includes(post.status)) {
          clearInterval(pollRef.current!);
          setPosting(false);
          setResult({
            post_id,
            accounts: (post.accounts ?? []).map((a) => ({
              username: a.username,
              status: a.status,
              error_message: a.error_message,
            })),
          });
        }
      } catch { /* keep polling */ }
    }, 4000);
  };

  const submit = async () => {
    if (!file || selectedIds.size === 0 || !caption.trim()) return;
    setPosting(true);
    setError("");
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("video", file);
      fd.append("caption", caption);
      fd.append("account_ids", JSON.stringify([...selectedIds]));
      const { post_id } = await api.posts.create(fd);
      pollPostStatus(post_id);
    } catch (e: any) {
      setError(e.message);
      setPosting(false);
    }
  };

  const reset = () => {
    setFile(null); setCaption(""); setTopic(""); setResult(null); setError("");
    setSelectedIds(new Set(accounts.map((a) => a.id)));
  };

  // Group accounts by platform
  const byPlatform = (["tiktok", "instagram", "twitter"] as Platform[]).map((p) => ({
    platform: p,
    accounts: accounts.filter((a) => (a.platform as Platform) === p || (!a.platform && p === "tiktok")),
  })).filter((g) => g.accounts.length > 0);

  if (result) {
    return (
      <div className="max-w-lg mx-auto text-center py-16">
        <CheckCircle size={48} className="text-success mx-auto mb-4" />
        <h2 className="text-xl font-bold mb-2">Post complete</h2>
        <p className="text-muted text-sm mb-6">Here's how each account went:</p>
        <div className="bg-card border border-border rounded-xl overflow-hidden mb-6 text-left">
          {result.accounts.map((a) => (
            <div key={a.username} className="flex items-center gap-3 px-5 py-3 border-b border-border last:border-0">
              {a.status === "success"
                ? <CheckCircle size={16} className="text-success flex-shrink-0" />
                : <XCircle size={16} className="text-error flex-shrink-0" />}
              <span className="text-sm flex-1">@{a.username}</span>
              {a.error_message && <span className="text-xs text-muted max-w-[160px] truncate">{a.error_message}</span>}
            </div>
          ))}
        </div>
        <button onClick={reset} className="bg-red hover:bg-opacity-90 transition text-white px-6 py-2.5 rounded-lg font-semibold text-sm">
          Upload another video
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Upload video</h1>
        <p className="text-muted text-sm mt-1">Post to all selected accounts at once.</p>
      </div>

      {/* Drop zone */}
      <div
        onClick={() => fileInputRef.current?.click()}
        onDragEnter={() => setDragging(true)}
        onDragLeave={() => setDragging(false)}
        onDragOver={(e) => e.preventDefault()}
        onDrop={onFileDrop}
        className={`relative border-2 border-dashed rounded-xl p-10 flex flex-col items-center justify-center cursor-pointer transition-all mb-6
          ${dragging ? "border-red bg-red bg-opacity-5" : "border-border hover:border-muted"}`}
      >
        <input ref={fileInputRef} type="file" accept="video/*" className="hidden" onChange={onFileChange} />
        {file ? (
          <>
            <Film size={32} className="text-red mb-3" />
            <p className="font-medium">{file.name}</p>
            <p className="text-muted text-xs mt-1">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
            <button onClick={(e) => { e.stopPropagation(); setFile(null); }} className="absolute top-3 right-3 text-muted hover:text-white transition">
              <X size={16} />
            </button>
          </>
        ) : (
          <>
            <Upload size={32} className="text-muted mb-3" />
            <p className="font-medium">Drop a video here</p>
            <p className="text-muted text-xs mt-1">or click to select a file</p>
          </>
        )}
      </div>

      {/* AI Caption */}
      <div className="mb-4">
        <label className="block text-sm font-medium mb-2">AI Caption</label>
        <div className="flex gap-2">
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && generateCaption()}
            placeholder="Enter a topic or keyword..."
            className="flex-1 bg-card border border-border rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-cyan placeholder-muted"
          />
          <button
            onClick={generateCaption}
            disabled={!topic.trim() || generating}
            className="flex items-center gap-2 bg-cyan bg-opacity-20 hover:bg-opacity-30 border border-cyan border-opacity-40 disabled:opacity-40 disabled:cursor-not-allowed transition text-cyan px-4 py-2.5 rounded-xl text-sm font-semibold"
          >
            {generating ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            {generating ? "Generating..." : "Generate"}
          </button>
        </div>
      </div>

      {/* Caption */}
      <div className="mb-6">
        <label className="block text-sm font-medium mb-2">Caption</label>
        <textarea
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
          placeholder="Write a caption… #fyp"
          rows={3}
          className="w-full bg-card border border-border rounded-xl p-4 text-sm text-white resize-none focus:outline-none focus:border-cyan placeholder-muted"
        />
      </div>

      {/* Account picker — grouped by platform */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <label className="text-sm font-medium">
            Post to <span className="text-muted font-normal">({selectedIds.size} account{selectedIds.size !== 1 ? "s" : ""} selected)</span>
          </label>
          <button onClick={toggleAll} className="text-xs text-cyan hover:underline">
            {selectedIds.size === accounts.length ? "Deselect all" : "Select all"}
          </button>
        </div>

        {accounts.length === 0 ? (
          <div className="bg-card border border-border rounded-xl p-5 text-center text-sm text-muted">
            No accounts connected. <a href="/accounts" className="text-cyan hover:underline">Add one</a>.
          </div>
        ) : (
          <div className="space-y-5">
            {byPlatform.map(({ platform, accounts: platAccs }) => {
              const meta = PLATFORM_META[platform];
              const allSelected = platAccs.every((a) => selectedIds.has(a.id));
              const someSelected = platAccs.some((a) => selectedIds.has(a.id));
              return (
                <div key={platform}>
                  {/* Platform header */}
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <PlatformDot platform={platform} />
                      <span className={`text-xs font-semibold uppercase tracking-widest ${meta.color}`}>
                        {meta.label}
                      </span>
                      <span className="text-xs text-muted">({platAccs.length})</span>
                    </div>
                    <button
                      onClick={() => togglePlatform(platform)}
                      className={`text-xs hover:underline ${meta.color}`}
                    >
                      {allSelected ? "Deselect all" : someSelected ? "Select all" : "Select all"}
                    </button>
                  </div>

                  {/* Accounts */}
                  <div className="space-y-2">
                    {platAccs.map((acc) => {
                      const checked = selectedIds.has(acc.id);
                      return (
                        <button
                          key={acc.id}
                          onClick={() => toggle(acc.id)}
                          className={`w-full flex items-center gap-3 p-3 rounded-xl border text-left transition
                            ${checked
                              ? `${meta.border} border-opacity-50 bg-opacity-5 ${meta.bg}`
                              : "border-border bg-card hover:border-muted"}`}
                        >
                          {checked
                            ? <CheckSquare size={18} className={`${meta.color} flex-shrink-0`} />
                            : <Square size={18} className="text-muted flex-shrink-0" />}
                          <div className="w-7 h-7 rounded-full bg-surface flex items-center justify-center flex-shrink-0 overflow-hidden">
                            {acc.avatar_url
                              // eslint-disable-next-line @next/next/no-img-element
                              ? <img src={acc.avatar_url} alt={acc.username} className="w-full h-full object-cover" />
                              : <span className="text-xs font-bold text-muted">{acc.username.charAt(0).toUpperCase()}</span>}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium leading-none">@{acc.username}</p>
                            {acc.display_name && <p className="text-xs text-muted mt-0.5">{acc.display_name}</p>}
                          </div>
                          <PlatformBadge platform={platform} />
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {error && (
        <p className="text-error text-sm mb-4 bg-error bg-opacity-10 border border-error border-opacity-30 rounded-lg px-3 py-2">{error}</p>
      )}

      <button
        onClick={submit}
        disabled={!file || selectedIds.size === 0 || !caption.trim() || posting}
        className="w-full bg-red hover:bg-opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition text-white py-3 rounded-xl font-semibold flex items-center justify-center gap-2"
      >
        {posting
          ? <><Loader2 size={18} className="animate-spin" />Posting to {selectedIds.size} account{selectedIds.size !== 1 ? "s" : ""}…</>
          : <><Upload size={18} />Post to {selectedIds.size} account{selectedIds.size !== 1 ? "s" : ""}</>}
      </button>

      {posting && <p className="text-muted text-xs text-center mt-3">This can take a few minutes — don't close this tab.</p>}
    </div>
  );
}