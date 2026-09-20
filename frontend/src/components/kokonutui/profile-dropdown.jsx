/**
 * @author: @kokonutui / Trenston
 * @description: Profile Dropdown — sidebar identity menu (KokonutUI, restyled)
 * @website: https://kokonutui.com
 */

import { CreditCard, HelpCircle, LogOut, Plug, Settings, ChevronUp } from "lucide-react";
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
  name = "CEO",
  picture,
  planLabel,
  showBilling = false,
  onBilling,
  onIntegrations,
  onSettings,
  onHelp,
  onLogout,
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
            className="inline-flex max-w-full items-center gap-2.5 rounded-full px-3 py-2 text-left transition-colors hover:bg-helm-fg/[0.04] focus:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold/40"
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
            <div className="min-w-0">
              <p className="text-xs text-helm-fg truncate">{name}</p>
              {planLabel ? (
                <p className="text-[10px] text-helm-muted truncate font-mono uppercase tracking-wide">
                  {planLabel}
                </p>
              ) : null}
            </div>
            <ChevronUp className="w-3.5 h-3.5 text-helm-muted shrink-0" />
          </button>
        </DropdownMenuTrigger>

        <DropdownMenuContent
          align="end"
          side="top"
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
            data-testid="settings-link"
            className="cursor-pointer gap-2 rounded-sm px-2 py-2 text-sm text-helm-fg focus:bg-helm-fg/5 focus:text-helm-fg"
            onSelect={() => onSettings?.()}
          >
            <Settings className="h-4 w-4 text-helm-muted" />
            Settings
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
