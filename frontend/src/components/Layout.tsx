import {
  BarChart3,
  ChevronRight,
  CircleHelp,
  LayoutDashboard,
  ShoppingBag,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import type { ReactNode } from "react";
import type { Page } from "../types";

const navigation = [
  { name: "Dashboard" as const, icon: LayoutDashboard },
  { name: "Analytics" as const, icon: BarChart3 },
  { name: "Sales" as const, icon: ShoppingBag },
  { name: "AI Insights" as const, icon: Sparkles },
];
export function Layout({
  page,
  setPage,
  children,
}: {
  page: Page;
  setPage: (page: Page) => void;
  children: ReactNode;
}) {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <a
          href="#dashboard"
          className="brand"
          onClick={() => setPage("Dashboard")}
        >
          <span className="brand-icon">
            <BarChart3 size={23} />
          </span>
          clarity<span className="brand-dot">.</span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">S</span>
          <div>
            <strong>Sales workspace</strong>
            <small>Analytics overview</small>
          </div>
          <span className="workspace-badge">PRO</span>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navigation.map(({ name, icon: Icon }) => (
            <button
              key={name}
              aria-current={page === name ? "page" : undefined}
              className={"nav-item " + (page === name ? "active" : "")}
              onClick={() => setPage(name)}
            >
              <Icon size={19} />
              <span>{name}</span>
              {name === "AI Insights" && <span className="new-badge">AI</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-tip">
            <TrendingUp size={22} />
            <strong>See the bigger picture.</strong>
            <p>
              Your data. Clearer decisions.
              <br />
              One place to make it happen.
            </p>
          </div>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="docs-link"
            onClick={(event) => {
              event.preventDefault();
              window.open(
                (import.meta.env.VITE_API_URL || "http://localhost:8000") +
                  "/docs",
                "_blank",
                "noopener,noreferrer",
              );
            }}
          >
            <CircleHelp size={17} /> API documentation{" "}
            <ChevronRight size={14} />
          </a>
          <div className="profile">
            <div className="avatar">AD</div>
            <div>
              <strong>Admin workspace</strong>
              <small>Demo environment</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
            <strong>{page}</strong>
          </div>
          <div className="topbar-right">
            <span className="demo-label">
              <span /> Demo workspace
            </span>
            <div className="avatar small">AD</div>
          </div>
        </header>
        <main id="main">{children}</main>
        <footer>
          Clarity Analytics{" "}
          <span>
            Built for better business decisions · Amounts in Toman; legacy
            totals unavailable · Dates in UTC
          </span>
        </footer>
      </div>
    </div>
  );
}
