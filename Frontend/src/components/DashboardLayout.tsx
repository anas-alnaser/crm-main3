import {
  AlertTriangle,
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  CalendarClock,
  ChevronDown,
  CheckSquare,
  Columns3,
  ClipboardList,
  DollarSign,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
  Search,
  Settings,
  Sun,
  Trophy,
  UserCog,
  Users,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { AICommandBar } from "./AICommandBar";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Badge, statusTone } from "./ui/badge";
import { Skeleton } from "./ui/skeleton";
import { apiRequest } from "../api/client";
import type { GlobalSearchResponse, SearchResults } from "../api/types";
import { useAuth } from "../lib/auth";
import { useTheme } from "../lib/theme";
import { cn } from "../lib/utils";

const sharedNavItems = [
  { to: "/overview", label: "Dashboard", icon: ClipboardList },
  { to: "/", label: "Pipeline", icon: Columns3 },
  { to: "/deals", label: "Deals", icon: DollarSign },
  { to: "/clients", label: "Companies", icon: Users },
  { to: "/tasks", label: "Tasks", icon: CheckSquare },
  { to: "/schedule", label: "Schedule", icon: CalendarClock },
  { to: "/activities", label: "Activities", icon: MessageSquare },
  { to: "/leaderboard", label: "Leaderboard", icon: Trophy },
];

const adminNavItems = [
  { to: "/users", label: "Users", icon: UserCog },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function DashboardLayout() {
  const { logout, user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState("");
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const navItems = user?.role === "admin" ? [...sharedNavItems, ...adminNavItems] : sharedNavItems;
  const pageTitle = useMemo(() => {
    return navItems.find((item) => (item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)))?.label ?? "Workspace";
  }, [location.pathname, navItems]);
  const initials = (user?.first_name || user?.username || "F")
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearchQuery(searchQuery.trim()), 220);
    return () => window.clearTimeout(timer);
  }, [searchQuery]);

  const searchEnabled = debouncedSearchQuery.length >= 2;
  const searchResults = useQuery({
    queryKey: ["workspace-search", debouncedSearchQuery],
    queryFn: () => searchWorkspace(debouncedSearchQuery),
    enabled: searchEnabled,
  });

  const closeSearch = () => setIsSearchOpen(false);
  const openResource = (path: string) => {
    navigate(path);
    closeSearch();
  };

  return (
    <div className="min-h-screen bg-background">
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-[280px] border-r border-border bg-card/95 px-4 py-5 text-card-foreground shadow-soft backdrop-blur transition-transform lg:translate-x-0",
          isSidebarOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="mb-8 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Fueldezign</p>
            <h1 className="mt-1 text-2xl font-semibold leading-none">CRM</h1>
          </div>
          <Button aria-label="Close navigation" className="lg:hidden" size="icon" type="button" variant="ghost" onClick={() => setIsSidebarOpen(false)}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <nav className="space-y-6">
          <NavGroup label="Workspace" items={sharedNavItems} onNavigate={() => setIsSidebarOpen(false)} />
          {user?.role === "admin" && <NavGroup label="Admin" items={adminNavItems} onNavigate={() => setIsSidebarOpen(false)} />}
        </nav>
      </div>

      {isSidebarOpen && <button aria-label="Close navigation overlay" className="fixed inset-0 z-30 bg-black/40 lg:hidden" type="button" onClick={() => setIsSidebarOpen(false)} />}

      <div className="flex min-w-0 flex-col lg:pl-[280px]">
        <header className="sticky top-0 z-20 border-b border-border bg-background/88 px-4 py-3 backdrop-blur lg:px-8">
          <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <Button aria-label="Open navigation" className="lg:hidden" size="icon" type="button" variant="outline" onClick={() => setIsSidebarOpen(true)}>
                <Menu className="h-4 w-4" />
              </Button>
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">Current view</p>
                <p className="text-lg font-semibold leading-tight">{pageTitle}</p>
              </div>
            </div>
            <div className="hidden w-full max-w-xl items-center gap-2 md:flex">
              <div className="relative w-full">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  aria-label="Search workspace"
                  className="pl-9 pr-9"
                  placeholder="Search a company, contact, phone, email, deal..."
                  value={searchQuery}
                  onChange={(event) => {
                    setSearchQuery(event.target.value);
                    setIsSearchOpen(true);
                  }}
                  onFocus={() => setIsSearchOpen(true)}
                />
                {searchQuery && (
                  <button
                    aria-label="Clear search"
                    className="absolute right-3 top-1/2 -translate-y-1/2 rounded text-muted-foreground transition hover:text-foreground"
                    type="button"
                    onClick={() => {
                      setSearchQuery("");
                      setDebouncedSearchQuery("");
                    }}
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
                {isSearchOpen && searchQuery.trim().length > 0 && (
                  <WorkspaceSearchPanel
                    isLoading={searchResults.isLoading}
                    isError={searchResults.isError}
                    query={searchQuery.trim()}
                    results={searchResults.data}
                    searchEnabled={searchEnabled}
                    onOpenResource={openResource}
                  />
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
                title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
                type="button"
                variant="outline"
                size="icon"
                onClick={toggleTheme}
              >
                {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </Button>
              <div className="relative">
                <button
                  className="focus-ring flex h-10 items-center gap-2 rounded-md border border-border bg-card px-2 text-sm shadow-sm transition hover:bg-muted"
                  type="button"
                  onClick={() => setIsUserMenuOpen((open) => !open)}
                >
                  <span className="grid h-7 w-7 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">{initials}</span>
                  <span className="hidden max-w-[120px] truncate font-medium sm:block">{user?.first_name || user?.username}</span>
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                </button>
                {isUserMenuOpen && (
                  <div className="absolute right-0 mt-2 w-56 rounded-lg border border-border bg-card p-2 text-card-foreground shadow-soft">
                    <div className="border-b border-border px-3 py-2">
                      <p className="truncate text-sm font-medium">{user?.first_name || user?.username}</p>
                      {user?.role && <Badge className="mt-2" tone={user.role === "admin" ? "accent" : "neutral"}>{user.role}</Badge>}
                    </div>
                    <Button className="mt-2 w-full justify-start" type="button" variant="ghost" onClick={logout}>
                      <LogOut className="h-4 w-4" />
                      Logout
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </header>
        {user?.role === "admin" && <AICommandBar />}
        <main className="min-w-0 flex-1 px-4 py-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

type WorkspaceSearchResults = SearchResults;

// One authenticated, role-masked endpoint instead of five unbounded fan-out
// requests. The backend scopes results to what the user may read and masks
// restricted values (e.g. deal amounts owned by others).
async function searchWorkspace(query: string): Promise<WorkspaceSearchResults> {
  const response = await apiRequest<GlobalSearchResponse>(`/search/?q=${encodeURIComponent(query)}`);
  return response.results;
}

function WorkspaceSearchPanel({
  isError,
  isLoading,
  onOpenResource,
  query,
  results,
  searchEnabled,
}: {
  isError: boolean;
  isLoading: boolean;
  onOpenResource: (path: string) => void;
  query: string;
  results?: WorkspaceSearchResults;
  searchEnabled: boolean;
}) {
  const totalResults = results ? results.clients.length + results.deals.length + results.meetings.length + results.tasks.length + results.activities.length : 0;
  const possibleDuplicates = Boolean(results && (results.clients.length || results.deals.length));

  return (
    <div className="absolute left-0 top-[calc(100%+8px)] z-50 w-full min-w-[520px] overflow-hidden rounded-lg border border-border bg-card text-card-foreground shadow-soft">
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">Smart search</p>
            <p className="text-xs text-muted-foreground">Check for existing companies, contacts, and open deals before calling.</p>
          </div>
          {possibleDuplicates && (
            <Badge tone="warning">
              <AlertTriangle className="mr-1 h-3 w-3" />
              Possible match
            </Badge>
          )}
        </div>
      </div>

      {!searchEnabled ? (
        <div className="px-4 py-5 text-sm text-muted-foreground">Type at least 2 characters to search the workspace.</div>
      ) : isLoading ? (
        <div className="space-y-3 p-4">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-5/6" />
        </div>
      ) : isError ? (
        <div className="px-4 py-5 text-sm text-muted-foreground">Search failed. Check the backend terminal or browser Network tab.</div>
      ) : !results || totalResults === 0 ? (
        <div className="px-4 py-5">
          <p className="text-sm font-medium">No matches for “{query}”</p>
          <p className="mt-1 text-xs text-muted-foreground">Looks clear, but still double-check spelling before creating a new company or deal.</p>
        </div>
      ) : (
        <div className="max-h-[520px] overflow-y-auto p-2">
          <SearchSection title="Companies and contacts">
            {results.clients.map((client) => (
              <SearchResultButton key={`client-${client.id}`} icon={Building2} onClick={() => onOpenResource("/clients")}>
                <span>
                  <span className="block font-medium">{client.name}</span>
                  <span className="block text-xs text-muted-foreground">
                    {[client.contact_person, client.email, client.phone].filter(Boolean).join(" · ") || "No contact details yet"}
                  </span>
                </span>
                <Badge tone={client.status === "active" ? "success" : "neutral"}>{client.status}</Badge>
              </SearchResultButton>
            ))}
          </SearchSection>

          <SearchSection title="Deals">
            {results.deals.map((deal) => (
              <SearchResultButton key={`deal-${deal.id}`} icon={BriefcaseBusiness} onClick={() => onOpenResource("/deals")}>
                <span>
                  <span className="block font-medium">{deal.title}</span>
                  <span className="block text-xs text-muted-foreground">
                    {[deal.company_name, deal.contact_person, deal.owner_username ? `Owner: ${deal.owner_username}` : ""].filter(Boolean).join(" · ")}
                  </span>
                </span>
                <Badge tone={deal.status === "won" ? "success" : deal.status === "lost" ? "danger" : "info"}>{deal.status}</Badge>
              </SearchResultButton>
            ))}
          </SearchSection>

          <SearchSection title="Tasks">
            {results.tasks.map((task) => (
              <SearchResultButton key={`task-${task.id}`} icon={CheckSquare} onClick={() => onOpenResource("/tasks")}>
                <span>
                  <span className="block font-medium">{task.title}</span>
                  <span className="block text-xs text-muted-foreground">
                    {[task.client_name, task.deal_title, task.due_date ? `Due ${task.due_date}` : ""].filter(Boolean).join(" · ") || "No linked record"}
                  </span>
                </span>
                <Badge tone={task.status === "done" ? "success" : task.status === "doing" ? "warning" : "info"}>{task.status}</Badge>
              </SearchResultButton>
            ))}
          </SearchSection>

          <SearchSection title="Meetings">
            {results.meetings.map((meeting) => (
              <SearchResultButton key={`meeting-${meeting.id}`} icon={CalendarClock} onClick={() => onOpenResource("/schedule")}>
                <span>
                  <span className="block font-medium">{meeting.title}</span>
                  <span className="block text-xs text-muted-foreground">
                    {[meeting.company_name, meeting.deal_title, new Date(meeting.start_datetime).toLocaleDateString()].filter(Boolean).join(" · ") || "Standalone meeting"}
                  </span>
                </span>
                <Badge tone={statusTone(meeting.status)}>{meeting.status}</Badge>
              </SearchResultButton>
            ))}
          </SearchSection>

          <SearchSection title="Recent activity">
            {results.activities.map((activity) => (
              <SearchResultButton key={`activity-${activity.id}`} icon={CalendarDays} onClick={() => onOpenResource("/activities")}>
                <span>
                  <span className="line-clamp-1 block font-medium">{activity.content}</span>
                  <span className="block text-xs text-muted-foreground">
                    {[activity.client_name, activity.deal_title, new Date(activity.created_at).toLocaleDateString()].filter(Boolean).join(" · ")}
                  </span>
                </span>
                <Badge tone="neutral">{activity.type}</Badge>
              </SearchResultButton>
            ))}
          </SearchSection>
        </div>
      )}
    </div>
  );
}

function SearchSection({ children, title }: { children: React.ReactNode; title: string }) {
  if (!children || (Array.isArray(children) && children.length === 0)) return null;
  return (
    <section className="py-2">
      <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{title}</p>
      <div className="space-y-1">{children}</div>
    </section>
  );
}

function SearchResultButton({
  children,
  icon: Icon,
  onClick,
}: {
  children: React.ReactNode;
  icon: typeof Building2;
  onClick: () => void;
}) {
  return (
    <button className="flex w-full items-center justify-between gap-3 rounded-md px-2 py-2 text-left transition hover:bg-muted" type="button" onClick={onClick}>
      <span className="flex min-w-0 items-center gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-border bg-background text-primary">
          <Icon className="h-4 w-4" />
        </span>
        <span className="min-w-0 text-sm">{children}</span>
      </span>
    </button>
  );
}

function NavGroup({
  items,
  label,
  onNavigate,
}: {
  items: typeof sharedNavItems;
  label: string;
  onNavigate: () => void;
}) {
  return (
    <div>
      <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <div className="space-y-1">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "group relative flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition",
                isActive
                  ? "bg-primary/10 text-foreground"
                  : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
              )
            }
          >
            {({ isActive }) => (
              <>
                <span className={cn("absolute left-0 h-5 w-0.5 rounded-full bg-primary opacity-0 transition", isActive && "opacity-100")} />
                <item.icon className={cn("h-4 w-4", isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} />
                {item.label}
              </>
            )}
          </NavLink>
        ))}
      </div>
    </div>
  );
}
