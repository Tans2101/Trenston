/**
 * @author: @kokonutui / Trenston
 * @description: Profile Dropdown — account menu in the top bar (KokonutUI, restyled).
 * Settings lives in the sidebar, so it is deliberately not repeated here.
 * @website: https://kokonutui.com
 */

import { CreditCard, HelpCircle, LogOut, Plug, ChevronDown } from "lucide-react";
import * as React from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export default function ProfileDropdown({
  name = "You",
  picture,
  planLabel,
  showBilling = false,
  onBilling,
  onIntegrations,
  onHelp,
  onLogout,
  // Avatar-only trigger for narrow screens.
  compact = false,
  className,
  ...props
}) {
  const initial = name?.[0] || "C";

  return (
    <div className={cn("relative w-fit max-w-full", className)} {...props}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className={cn(
              "inline-flex max-w-full items-center rounded-full text-left transition-colors hover:bg-helm-fg/[0.04] focus:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold/40",
              compact ? "gap-1 p-1" : "gap-2.5 px-3 py-2",
            )}
            aria-label="Account menu"
          >
            {picture ? (
              <img
                src={picture}
                alt=""
                className="w-8 h-8 rounded-full object-cover border border-helm-line shrink-0"
              />
            ) : (
              <div className="w-8 h-8 rounded-full bg-helm-fg/10 flex items-center justify-center text-xs text-helm-fg shrink-0">
                {initial}
              </div>
            )}
            {!compact && (
              <div className="min-w-0">
                <p className="text-xs text-helm-fg truncate">{name}</p>
                {planLabel ? (
                  <p className="text-[10px] text-helm-muted truncate font-mono uppercase tracking-wide">
                    {planLabel}
                  </p>
                ) : null}
              </div>
            )}
            <ChevronDown className="w-3.5 h-3.5 text-helm-muted shrink-0" />
          </button>
        </DropdownMenuTrigger>

        <DropdownMenuContent
          align="end"
          side="bottom"
          sideOffset={6}
          className="w-56 rounded-md border border-helm-line bg-helm-card p-1 shadow-xl text-helm-fg"
        >
          {showBilling && (
            <DropdownMenuItem
              data-testid="sidebar-billing-link"
              className="cursor-pointer gap-2 rounded-sm px-2 py-2 text-sm text-helm-fg focus:bg-helm-fg/5 focus:text-helm-fg"
              onSelect={() => onBilling?.()}
            >
              <CreditCard className="h-4 w-4 text-helm-muted" />
              Billing
            </DropdownMenuItem>
          )}
          <DropdownMenuItem
            data-testid="sidebar-integrations-link"
            className="cursor-pointer gap-2 rounded-sm px-2 py-2 text-sm text-helm-fg focus:bg-helm-fg/5 focus:text-helm-fg"
            onSelect={() => onIntegrations?.()}
          >
            <Plug className="h-4 w-4 text-helm-muted" />
            Integrations
          </DropdownMenuItem>
          <DropdownMenuItem
            data-testid="sidebar-help-link"
            className="cursor-pointer gap-2 rounded-sm px-2 py-2 text-sm text-helm-fg focus:bg-helm-fg/5 focus:text-helm-fg"
            onSelect={() => onHelp?.()}
          >
            <HelpCircle className="h-4 w-4 text-helm-muted" />
            Help
          </DropdownMenuItem>
          <DropdownMenuSeparator className="bg-helm-line" />
          <DropdownMenuItem
            data-testid="logout-btn"
            className="cursor-pointer gap-2 rounded-sm px-2 py-2 text-sm text-helm-fg focus:bg-helm-fg/5 focus:text-helm-fg"
            onSelect={() => onLogout?.()}
          >
            <LogOut className="h-4 w-4 text-helm-muted" />
            Log out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
