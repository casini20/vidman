"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, Upload, Video } from "lucide-react";

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
        <div className="relative w-8 h-8 flex items-center justify-center">
          <div className="absolute inset-0 rounded-lg bg-gradient-to-br from-cyan to-red opacity-20" />
          <Video size={18} className="text-white relative z-10" />
        </div>
        <span className="font-bold text-sm tracking-wide">Vidman</span>
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
                ${active
                  ? "bg-[#1E1E2E] text-white"
                  : "text-muted hover:text-white hover:bg-[#16161E]"
                }
              `}
              style={active ? { boxShadow: "inset 0 0 0 1px rgba(255,45,85,0.4)" } : {}}
            >
              <Icon size={18} className={active ? "text-red" : ""} />
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
        <p className="text-xs text-muted">Vidman — Multi-platform manager</p>
      </div>
    </aside>
  );
}
