"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, Upload, Music2 } from "lucide-react";

const nav = [
  { href: "/", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/accounts", icon: Users, label: "Accounts" },
  { href: "/upload", icon: Upload, label: "Upload" },
];

export default function Sidebar() {
  const path = usePathname();

  return (
    <aside className="w-60 flex-shrink-0 bg-surface border-r border-border flex flex-col">
      {/* Logo */}
      <div className="p-6 flex items-center gap-3 border-b border-border">
        <div className="relative w-8 h-8">
          {/* TikTok-style dual icon */}
          <Music2
            size={20}
            className="absolute top-1 left-1 text-cyan"
            style={{ filter: "blur(0px)" }}
          />
          <Music2
            size={20}
            className="absolute top-0.5 left-0.5 text-red opacity-80"
          />
        </div>
        <span className="font-semibold text-sm tracking-wide">TikTok Manager</span>
      </div>

      {/* Nav items */}
      <nav className="flex-1 p-4 space-y-1">
        {nav.map(({ href, icon: Icon, label }) => {
          const active = path === href;
          return (
            <Link
              key={href}
              href={href}
              className={`
                flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium
                transition-all duration-150
                ${
                  active
                    ? "bg-[#1E1E2E] text-white"
                    : "text-muted hover:text-white hover:bg-[#16161E]"
                }
              `}
              style={
                active
                  ? {
                      boxShadow: "inset 0 0 0 1px rgba(255,45,85,0.4)",
                    }
                  : {}
              }
            >
              <Icon
                size={18}
                className={active ? "text-red" : ""}
              />
              {label}
              {active && (
                <span
                  className="ml-auto w-1.5 h-1.5 rounded-full bg-red"
                  style={{ boxShadow: "0 0 6px #FF2D55" }}
                />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-border">
        <p className="text-xs text-muted">
          Sessions via Cookie-Editor
        </p>
      </div>
    </aside>
  );
}
