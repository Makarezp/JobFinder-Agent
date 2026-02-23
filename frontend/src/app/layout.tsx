import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CVviewer AI Navigator Dashboard",
  description: "The Tinder for Jobs — AI-powered job matching agent",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-background-light dark:bg-background-dark text-slate-900 dark:text-slate-100 h-screen flex flex-col overflow-hidden">
        {/* Top Navigation / Pulse Widget */}
        <header className="h-16 shrink-0 border-b border-glass-border bg-[#131221]/90 backdrop-blur-md z-20 flex items-center justify-between px-6">
          {/* Brand */}
          <div className="flex items-center gap-3">
            <div className="size-8 rounded-lg bg-primary/20 flex items-center justify-center text-primary">
              <span className="material-symbols-outlined">smart_toy</span>
            </div>
            <h1 className="text-xl font-bold tracking-tight text-white">
              CVviewer
            </h1>
          </div>

          {/* Advisory Pulse Widgets (Active Filters Placeholder) */}
          <div className="hidden md:flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-full bg-surface-dark border border-glass-border px-3 py-1.5 animate-pulse-slow">
              <span className="material-symbols-outlined text-primary text-sm">
                search
              </span>
              <span className="text-xs font-medium text-slate-300">
                Searching...
              </span>
            </div>
          </div>

          {/* User Actions Placeholder */}
          <div className="flex items-center gap-4">
            <button className="relative p-2 text-slate-400 hover:text-white transition-colors rounded-full hover:bg-white/5">
              <span className="material-symbols-outlined">notifications</span>
              <span className="absolute top-2 right-2 size-2 bg-red-500 rounded-full border border-background-dark"></span>
            </button>
            <div
              className="size-9 rounded-full bg-cover bg-center border border-glass-border ring-2 ring-transparent hover:ring-primary/50 transition-all cursor-pointer bg-slate-800"
              title="User Profile"
            />
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
