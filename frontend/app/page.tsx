"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Account, Post } from "@/lib/api";
import { Users, Upload, CheckCircle, AlertCircle, Clock, TrendingUp } from "lucide-react";

function StatCard({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  accent: string;
}) {
  return (
    <div className="bg-card border border-border rounded-xl p-5 flex items-center gap-4">
      <div
        className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
        style={{ background: `${accent}18` }}
      >
        <Icon size={20} style={{ color: accent }} />
      </div>
      <div>
        <p className="text-2xl font-bold">{value}</p>
        <p className="text-xs text-muted mt-0.5">{label}</p>
      </div>
    </div>
  );
}

function statusBadge(status: string) {
  return (
    <span className={`badge-${status} text-xs px-2 py-0.5 rounded-full font-medium`}>
      {status.replace("_", " ")}
    </span>
  );
}

export default function Dashboard() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.accounts.list(), api.posts.list()])
      .then(([a, p]) => { setAccounts(a); setPosts(p); })
      .finally(() => setLoading(false));
  }, []);

  const completedPosts = posts.filter((p) => p.status === "completed").length;
  const failedPosts = posts.filter((p) => p.status === "failed").length;

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted text-sm mt-1">
          Upload once, post to all your TikTok accounts.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="Connected accounts"
          value={accounts.length}
          icon={Users}
          accent="#69C9D0"
        />
        <StatCard
          label="Total posts"
          value={posts.length}
          icon={Upload}
          accent="#FF2D55"
        />
        <StatCard
          label="Successful posts"
          value={completedPosts}
          icon={CheckCircle}
          accent="#00D37C"
        />
        <StatCard
          label="Failed posts"
          value={failedPosts}
          icon={AlertCircle}
          accent="#FF4444"
        />
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-2 gap-4 mb-8">
        <Link
          href="/upload"
          className="bg-red hover:bg-opacity-90 transition text-white rounded-xl p-5 flex items-center gap-3 font-semibold"
        >
          <Upload size={20} />
          Upload a video
        </Link>
        <Link
          href="/accounts"
          className="bg-card border border-border hover:border-cyan transition rounded-xl p-5 flex items-center gap-3 font-semibold text-white"
        >
          <Users size={20} className="text-cyan" />
          Manage accounts
        </Link>
      </div>

      {/* Recent posts */}
      <div>
        <h2 className="text-sm font-semibold text-muted uppercase tracking-wider mb-4">
          Recent posts
        </h2>

        {loading ? (
          <p className="text-muted text-sm">Loading…</p>
        ) : posts.length === 0 ? (
          <div className="bg-card border border-border rounded-xl p-8 text-center">
            <Clock size={32} className="text-muted mx-auto mb-3" />
            <p className="text-muted text-sm">No posts yet. Upload a video to get started.</p>
          </div>
        ) : (
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-5 py-3 text-muted font-medium">Caption</th>
                  <th className="text-left px-5 py-3 text-muted font-medium">Accounts</th>
                  <th className="text-left px-5 py-3 text-muted font-medium">Status</th>
                  <th className="text-left px-5 py-3 text-muted font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {posts.slice(0, 10).map((post) => (
                  <tr key={post.id} className="border-b border-border last:border-0 hover:bg-surface">
                    <td className="px-5 py-3 max-w-xs truncate">{post.caption}</td>
                    <td className="px-5 py-3 text-muted">
                      {post.success_count}/{post.total_accounts}
                    </td>
                    <td className="px-5 py-3">{statusBadge(post.status)}</td>
                    <td className="px-5 py-3 text-muted font-mono text-xs">
                      {new Date(post.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
