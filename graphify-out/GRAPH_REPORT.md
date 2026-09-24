# Graph Report - Trenston  (2026-09-24)

## Corpus Check
- Large corpus: 890 files · ~521,938 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder.

## Summary
- 5946 nodes · 13952 edges · 233 communities (214 shown, 19 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 263 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 72
- Community 73
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 83
- Community 84
- Community 85
- Community 86
- Community 87
- Community 88
- Community 89
- Community 90
- Community 91
- Community 92
- Community 93
- Community 94
- Community 95
- Community 96
- Community 97
- Community 98
- Community 99
- Community 100
- Community 101
- Community 102
- Community 103
- Community 104
- Community 105
- Community 106
- Community 107
- Community 108
- Community 109
- Community 110
- Community 111
- Community 112
- Community 113
- Community 114
- Community 115
- Community 116
- Community 117
- Community 118
- Community 119
- Community 120
- Community 121
- Community 122
- Community 123
- Community 124
- Community 125
- Community 126
- Community 127
- Community 128
- Community 129
- Community 130
- Community 131
- Community 132
- Community 133
- Community 134
- Community 135
- Community 136
- Community 137
- Community 138
- Community 139
- Community 140
- Community 141
- Community 142
- Community 143
- Community 144
- Community 145
- Community 146
- Community 147
- Community 148
- Community 149
- Community 150
- Community 151
- Community 152
- Community 153
- Community 154
- Community 155
- Community 156
- Community 157
- Community 158
- Community 159
- Community 160
- Community 161
- Community 162
- Community 163
- Community 164
- Community 165
- Community 166
- Community 167
- Community 168
- Community 169
- Community 170
- Community 171
- Community 172
- Community 173
- Community 174
- Community 175
- Community 176
- Community 177
- Community 178
- Community 179
- Community 180
- Community 181
- Community 182
- Community 183
- Community 184
- Community 185
- Community 186
- Community 187
- Community 188
- Community 189
- Community 190
- Community 191
- Community 192
- Community 193
- Community 194
- Community 195
- Community 196
- Community 197
- Community 198
- Community 199
- Community 200
- Community 201
- Community 202
- Community 203
- Community 204
- Community 205
- Community 206
- Community 207
- Community 208
- Community 209
- Community 210
- Community 211
- Community 212
- Community 213
- Community 214
- Community 215
- Community 216
- Community 217
- Community 218
- Community 219
- Community 221
- Community 222
- Community 223
- Community 224
- Community 225
- Community 226
- Community 227
- Community 229
- Community 230

## God Nodes (most connected - your core abstractions)
1. `cn()` - 349 edges
2. `react` - 148 edges
3. `invalidate_workspace_list_cache()` - 81 edges
4. `get_ws()` - 79 edges
5. `lucide-react` - 75 edges
6. `useFetch()` - 54 edges
7. `fetchErrorMessage()` - 48 edges
8. `react-router-dom` - 47 edges
9. `get_department_membership()` - 45 edges
10. `resolutions` - 43 edges

## Surprising Connections (you probably didn't know these)
- `test_normalize_section_grants_filters_and_dedupes()` --calls--> `normalize_section_grants()`  [EXTRACTED]
  backend/tests/test_member_section_grants.py → backend/access_sections.py
- `test_entry_amount_for_totals_prefers_net_home()` --calls--> `entry_amount_for_totals()`  [EXTRACTED]
  backend/tests/test_stable_ids_currency_tax.py → backend/accounting_map.py
- `test_clerk_accounts_host_risks_flags_accounts_urls()` --calls--> `clerk_accounts_host_risks()`  [EXTRACTED]
  backend/tests/test_clerk_sync.py → backend/clerk_auth.py
- `test_sync_skipped_when_not_configured()` --calls--> `sync_clerk_instance()`  [EXTRACTED]
  backend/tests/test_clerk_sync.py → backend/clerk_auth.py
- `test_overdue_tasks_uses_parseable_dates_only()` --calls--> `detect_overdue_tasks()`  [EXTRACTED]
  backend/tests/test_decision_insights.py → backend/decision_engine.py

## Import Cycles
- None detected.

## Communities (233 total, 19 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.02
Nodes (212): RingChart(), CirEditBtn(), DangerConfirmCard(), DocumentStamp(), InviteCeoCard(), ProBadge(), Spinner(), ActionSearchBar (+204 more)

### Community 1 - "Community 1"
Cohesion: 0.02
Nodes (148): add_person(), AgeConfirmInput, AppearanceInput, _assemble_financial_export_for(), _can_request_leave_for_employee(), _check_join_rate_limit(), _client_ip(), CompanySetupInput (+140 more)

### Community 2 - "Community 2"
Cohesion: 0.04
Nodes (138): annotate_possibly_stale(), Return shallow copies with possibly_stale set (does not mutate inputs)., get_department_membership(), apply_status_completion(), Stamp completed_at when a record first reaches its done status., _blocking_production_order_entry(), _blocking_production_orders_by_maintenance_ticket(), _blocking_production_orders_by_request() (+130 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (96): AiSummaryMeta(), formatAsOf(), PossiblyStaleBadge(), CirDeleteBtn(), ConfidenceBadge(), DecisionCard(), LIST_MOTION, statusStyle (+88 more)

### Community 4 - "Community 4"
Cohesion: 0.04
Nodes (96): credentials_present(), Connection check that works for sealed and plaintext storage., _acquire_ai_extract_quota(), approve_decision_suggestion(), assign_delegate_suggestion(), _branding_data_url(), _can_use_integration_tokens(), clear_sample_data() (+88 more)

### Community 5 - "Community 5"
Cohesion: 0.03
Nodes (70): About, AccountSettings, App(), AppHelp, AppRouter(), AuthShell(), Billing, Briefing (+62 more)

### Community 6 - "Community 6"
Cohesion: 0.04
Nodes (57): test_xero_currency_and_subtotal(), asyncio, Unit tests for Xero token refresh and invoice/bill mapping., test_exclude_submitted_invoices(), test_fetch_connections_maps_tenants(), test_map_accpay_bill_to_expense(), test_map_accrec_invoice_to_revenue(), test_map_bank_receive_and_spend() (+49 more)

### Community 7 - "Community 7"
Cohesion: 0.04
Nodes (69): gen_join_code(), api_root(), ask_history(), _audit_document_access(), auth_me(), briefing(), _load_fin(), can_access_financials() (+61 more)

### Community 8 - "Community 8"
Cohesion: 0.03
Nodes (59): browserslist, development, production, name, packageManager, private, version, FormControl (+51 more)

### Community 9 - "Community 9"
Cohesion: 0.03
Nodes (69): dependencies, axios, class-variance-authority, @clerk/clerk-react, clsx, cmdk, cra-template, d3-array (+61 more)

### Community 10 - "Community 10"
Cohesion: 0.05
Nodes (57): config, path, webpackConfig, ALLOW_PATH_PREFIXES, __dirname, FORBIDDEN, isAllowed(), main() (+49 more)

### Community 11 - "Community 11"
Cohesion: 0.05
Nodes (66): AsyncIOMotorClient, _activate_invites(), _allowed_auth_redirect(), _auth_redirect_uri(), _bearer_token(), _bootstrap(), cleanup_orphaned_documents_admin(), clear_session_cookie() (+58 more)

### Community 12 - "Community 12"
Cohesion: 0.05
Nodes (31): asyncio, _activity_heatmap_for_workspace(), Aggregate db.activities into a Bklit heatmap grid (Sunday-first week columns).…, Cross-integration mapper parity — QB / Xero / SAP B1 share one ledger shape., Regression: accounting sync insert races on qb_txn_id unique index., asyncio, Unit tests for Telemetry activity heatmap aggregation., test_activity_heatmap_empty_workspace() (+23 more)

### Community 13 - "Community 13"
Cohesion: 0.05
Nodes (61): normalize_section_access(), normalize_section_grants(), Any, Canonical section IDs for Team & Access → Manage Access grants., Normalize membership.section_grants to unique manageable section ids., Normalize workspace.section_access to {section_id: [department, ...]}., _access_cache(), accessible_department_ids() (+53 more)

### Community 14 - "Community 14"
Cohesion: 0.05
Nodes (63): delete_calendar_event(), has_scope(), patch_calendar_event(), _annotate_helm_event_permissions(), _briefing_email_threads(), _briefing_gmail_fetch_and_store(), _build_helm_event(), calendar() (+55 more)

### Community 15 - "Community 15"
Cohesion: 0.04
Nodes (17): attach_users_in_find(), find(), Mongo mock helpers for unit tests., Route users.find($in) through users.find_one so batch lookups work on mocks., CollStore, _match(), fixture, HR summary stats + pending leave Decision Center signals. (+9 more)

### Community 16 - "Community 16"
Cohesion: 0.06
Nodes (57): _all_day_exclusive_end(), _compute_hours(), _counts_toward_hours(), create_calendar_event(), _email_domain(), fetch_important_threads(), fetch_today_calendar(), fetch_week_calendar() (+49 more)

### Community 17 - "Community 17"
Cohesion: 0.05
Nodes (33): Render build script — installs production deps only., _auth_configured(), main(), _mongo_configured(), Fail fast if critical production env vars are missing. Run on Render build or…, POST /api/internal/run-accounting-sync for the Render cron job (stdlib only)., POST /api/internal/run-daily-alerts for the Render cron job (stdlib only).…, POST /api/internal/run-daily-briefing for the Render cron job (stdlib only).… (+25 more)

### Community 18 - "Community 18"
Cohesion: 0.05
Nodes (58): normalize_entry_name(), Always return a non-empty line-item label. Prefer an explicit name. If…, currency_symbol(), fmt_money(), normalize_currency(), Format a number with the workspace currency symbol (compact K/M style)., _apply_report_snapshot(), _briefing_finance_metrics() (+50 more)

### Community 19 - "Community 19"
Cohesion: 0.07
Nodes (52): AskTrenston, DocumentsLibrarySettings(), openPathIsSafe(), useAuth(), buildDelegateOptions(), decisionOwnerIsSelf(), isOpenDecision(), useDecisionActions() (+44 more)

### Community 20 - "Community 20"
Cohesion: 0.07
Nodes (44): DepartmentPlaceholder, AppLayout(), departmentNavTo(), departmentNavVisible(), isTypingTarget(), NAV, navItemVisible(), navShortcutLabel() (+36 more)

### Community 21 - "Community 21"
Cohesion: 0.07
Nodes (43): Security, MarketingFooter(), isActive(), MarketingNav(), NAV_LINKS, useMarketingAuth(), CHANGELOG_ENTRIES, CHANGELOG_INTRO (+35 more)

### Community 22 - "Community 22"
Cohesion: 0.05
Nodes (26): Hourly QuickBooks/Xero auto-sync cron., test_accounting_auto_sync_clears_expired_quickbooks(), test_accounting_auto_sync_runs_connected_workspaces(), test_accounting_auto_sync_skips_xero_without_tenant(), asyncio, test_upsert_accounting_sync_handles_duplicate_key(), _expired_tokens(), asyncio (+18 more)

### Community 23 - "Community 23"
Cohesion: 0.07
Nodes (45): acquire_ask_helm_slot(), acquire_event_slot(), acquire_insights_slot(), acquire_join_slot(), _acquire_window_bucket(), ask_helm_over_limit(), count_ask_helm_events(), count_events() (+37 more)

### Community 24 - "Community 24"
Cohesion: 0.07
Nodes (44): build_workspace(), last_n_months(), Per-workspace data template for Trenston — Northwind Robotics sample + empty…, 6 months of recurring revenue + categorized expenses (in USD)., sample_financial_entries(), apply_template(), _clear_sample_workspace(), _normalize_telemetry_targets() (+36 more)

### Community 25 - "Community 25"
Cohesion: 0.07
Nodes (38): Financials, Telemetry, ASSISTANT_PROMPTS, BriefingCockpitHero(), decisionQueueStatus(), METRIC_KEYS, pickMetric(), spendColors() (+30 more)

### Community 26 - "Community 26"
Cohesion: 0.11
Nodes (34): ClerkLoadError(), ClerkModeContext, ClerkProviderBootstrap(), clerkProxyUrl(), useClerkMode(), AuthMarketingHeader(), LINKS, AuthProductShowcase() (+26 more)

### Community 27 - "Community 27"
Cohesion: 0.06
Nodes (37): health(), Liveness probe for Render — must return 200 within 5s even when Mongo is down.…, _bump_generation(), clear(), _current_generation(), get_or_set(), invalidate_prefix(), Any (+29 more)

### Community 28 - "Community 28"
Cohesion: 0.06
Nodes (34): DepartmentsShowcase(), ease, fade, ease, fade, IntegrationsShowcase(), DecisionScreen(), ProductScreens() (+26 more)

### Community 29 - "Community 29"
Cohesion: 0.05
Nodes (44): public_api_origin(), Public HTTPS origin for OAuth callbacks (Vercel proxies /api to Render)., _alert_recipient_emails(), _app_base_url(), _apply_unsubscribe_token(), assemble_ops_briefing_data(), _load_ops(), _briefing_ops_metrics() (+36 more)

### Community 30 - "Community 30"
Cohesion: 0.12
Nodes (37): generateHeatmapSkeletonFromTarget(), computeHeatmapEnterFadeDelayMs(), computeHeatmapLevelRange(), HEATMAP_DEFAULT_ENTER_DURATION_MS, HEATMAP_DEFAULT_ENTER_EASE, HEATMAP_DEFAULT_ENTER_TRANSITION, HEATMAP_DEFAULT_LOADING_CELL_MAX_OPACITY, HEATMAP_DEFAULT_LOADING_CELL_RANDOMNESS (+29 more)

### Community 31 - "Community 31"
Cohesion: 0.05
Nodes (43): resolutions, **/anymatch/picomatch, **/axios/form-data, @babel/plugin-transform-modules-systemjs, **/cosmiconfig/yaml, **/css-loader/postcss, **/css-minimizer-webpack-plugin/postcss, **/cssnano/yaml (+35 more)

### Community 32 - "Community 32"
Cohesion: 0.08
Nodes (40): _client(), compress_branding_image(), _content_type_key(), delete_document(), get_document_bytes(), get_presigned_url(), maybe_compress_image(), probe_r2() (+32 more)

### Community 33 - "Community 33"
Cohesion: 0.12
Nodes (40): Attach all new department-ops endpoints onto api_router. `db` is resolved at…, register(), _can_lead_maint(), _can_lead_proc(), _can_lead_sales(), create_maintenance_contract(), create_maintenance_cost(), create_maintenance_schedule() (+32 more)

### Community 34 - "Community 34"
Cohesion: 0.09
Nodes (39): assert_encryption_ready(), CredentialCryptoError, decrypt_credential(), encrypt_credential(), encryption_key_is_fernet(), _fernet(), _fernet_key_bytes(), _is_production() (+31 more)

### Community 35 - "Community 35"
Cohesion: 0.08
Nodes (39): _assert_public_service_layer_host(), ensure_session(), _fetch_collection(), _fetch_collection_page(), fetch_sap_transactions(), _is_blocked_ip(), _line_category(), login() (+31 more)

### Community 36 - "Community 36"
Cohesion: 0.09
Nodes (38): _api_base(), _base_mapped_fields(), _cdc_deleted_ids(), _once(), fetch_qb_transactions(), _is_pl_account_type(), _is_prod_like(), map_qb_journal_entry() (+30 more)

### Community 37 - "Community 37"
Cohesion: 0.09
Nodes (34): FaqItem(), ABOUT_DIFFERENTIATOR, ABOUT_PROBLEM, ABOUT_STORY, CEO_DAY, FEATURE_MODULES, FOUNDED_DATE, FOUNDER_CREDIT (+26 more)

### Community 38 - "Community 38"
Cohesion: 0.07
Nodes (12): _cleanup_updates_and_tasks(), exec_ctx(), member(), mongo(), owner(), fixture, Iteration 5 tests: - Daily Update loop (POST /api/updates one-per-day-edit,…, Brand new user with no membership -> needs_workspace true, /app/welcome. (+4 more)

### Community 39 - "Community 39"
Cohesion: 0.07
Nodes (27): create_gmail_draft(), _post(), create_spreadsheet(), download_drive_file(), _fetch_calendar_events(), _once(), _page(), GmailDraftError (+19 more)

### Community 40 - "Community 40"
Cohesion: 0.08
Nodes (33): any_paddle_price_configured(), is_downgrade(), is_upgrade(), paddle_price_id_for(), plan_allows(), plan_allows_provider(), plan_for_paddle_price(), plan_rank() (+25 more)

### Community 41 - "Community 41"
Cohesion: 0.07
Nodes (22): _deadlines_as_events(), _department_calendar_upcoming(), Load open department dates from CALENDAR_DATE_SOURCES for this workspace.…, Turn upcoming deadline rows into calendar events. Uses source=\"deadline\" (not…, cal_db(), DocStore, _match(), asyncio (+14 more)

### Community 42 - "Community 42"
Cohesion: 0.07
Nodes (14): _public_addrinfo(), asyncio, SAP Business One Service Layer client + catalog wiring., Pretend host resolves to a public address (not RFC1918 / loopback)., Stored service_layer_url must be re-checked on outbound sync (DNS rebinding)., test_catalog_sap_credentials_connected(), test_catalog_sap_not_connected_by_default(), test_fetch_collection_revalidates_url_each_page() (+6 more)

### Community 43 - "Community 43"
Cohesion: 0.09
Nodes (30): DEFAULT_CHART_LIFECYCLE, DEFAULT_CHART_STATUS, DEFAULT_Y_DOMAIN_TWEEN_MS, resolveRestingChartPhase(), Y_DOMAIN_TWEEN_SKIP_THRESHOLD, computeHeatmapDimensions(), DEFAULT_MARGIN, HeatmapChartInner() (+22 more)

### Community 44 - "Community 44"
Cohesion: 0.12
Nodes (36): _bapi_headers(), clerk_accounts_host_risks(), clerk_configured(), clerk_custom_domain_ssl_ok(), _clerk_fapi_display_config(), clerk_jwks_host(), _clerk_primary_domain_record(), clerk_signup_policy() (+28 more)

### Community 45 - "Community 45"
Cohesion: 0.06
Nodes (7): catalog_entry(), Any, Fixed department catalog — not stored per workspace. Future department-specific…, Reserved collection name for a department's future stages feature., stages_collection_name(), Engineering & Maintenance ops panels API tests (spares, schedules, AMCs, costs,…, Sales order book + monthly target API tests.

### Community 46 - "Community 46"
Cohesion: 0.19
Nodes (30): _db(), _override_owner(), asyncio, CEO-to-CEO referral tracking — shareable links only, no rewards., Must not raise 'User not found' — that string looked like invite-field…, _referrals_store(), find_one(), update_one() (+22 more)

### Community 47 - "Community 47"
Cohesion: 0.11
Nodes (34): build_equipment_history(), collect_department_signals(), compute_average_cycle_time(), compute_downtime(), detect_chronic_equipment_failure(), detect_pending_leave_requests(), detect_stalled_onboarding(), detect_urgent_maintenance() (+26 more)

### Community 48 - "Community 48"
Cohesion: 0.09
Nodes (34): apply_department_filter(), Attach department_id constraint. ``None`` = CEO bypass (unchanged filter)., apply_before_filter(), clamp_limit(), encode_cursor(), next_cursor(), Any, Cursor-based pagination helpers for list endpoints. Uses a composite cursor… (+26 more)

### Community 49 - "Community 49"
Cohesion: 0.09
Nodes (33): assemble_ops_briefing_data(), Gather structured ops snapshot for one workspace. Returns sections keyed by…, department_day_summary(), enrich_daily_log(), normalize_log_date(), normalize_unit(), _parse_date(), parse_nonneg_float() (+25 more)

### Community 50 - "Community 50"
Cohesion: 0.10
Nodes (32): expand_entries_by_month(), expand_expense_category_totals(), expense_monthly_amount(), iter_expense_month_amounts(), line_items_for_period(), month_add(), _monthlyized(), months_inclusive() (+24 more)

### Community 51 - "Community 51"
Cohesion: 0.09
Nodes (18): ensure_fresh_user(), H(), fixture, parametrize, Iteration 3: Onboarding + entry-driven Financials + flow-through into…, Owner (kalun) already has sample applied per test_credentials note., Add a recurring revenue entry for the latest month, verify MRR flows into…, Owner (fresh) applies sample template, verifies data materialized. (+10 more)

### Community 52 - "Community 52"
Cohesion: 0.09
Nodes (16): frontend_src_assets_trenston_mark, frontend_src_assets_trenston_mark_navy, frontend_src_assets_trenston_wordmark_black, frontend_src_assets_trenston_wordmark_cream, frontend_src_assets_trenston_wordmark_navy, ErrorBoundary, HelmMark(), FounderCredit() (+8 more)

### Community 53 - "Community 53"
Cohesion: 0.11
Nodes (26): CHART_SCALE_VARS, chartScaleCssVars, HeatmapChart(), buildHeatmapColorScale(), buildHeatmapColorScaleFromStyles(), buildHeatmapFillScale(), defaultHeatmapFillScale, HEATMAP_DEFAULT_LEVEL_STYLES (+18 more)

### Community 54 - "Community 54"
Cohesion: 0.07
Nodes (18): Map pack permissions to manageable section ids the user already has via pack., section_pack_perm(), sections_for_perms(), asyncio, Calendar write permission: pack + section grants, not hardcoded can_write., test_calendar_is_manageable_section(), test_can_section_write_calendar_via_member_grant(), test_member_without_calendar_grant_cannot_write() (+10 more)

### Community 55 - "Community 55"
Cohesion: 0.08
Nodes (16): api_client(), _empty_cursor(), asyncio, fixture, People ↔ Team & Access sync., Membership gone but People row still has membership_id — delete must succeed., test_delete_person_allowed_after_access_revoked_stale_link(), test_department_names_by_user_id_maps_memberships() (+8 more)

### Community 56 - "Community 56"
Cohesion: 0.09
Nodes (28): clerk_authorized_parties(), clerk_multi_domain_auth(), clerk_post_auth_url(), clerk_primary_origin(), _clerk_redirect_url_list(), helm_frontend_origins(), _origin_registrable_host(), primary_frontend_origin() (+20 more)

### Community 57 - "Community 57"
Cohesion: 0.09
Nodes (31): count_possibly_stale(), calendar_for_synthesis(), company_context_for_synthesis(), company_profile_for_synthesis(), onboarding_for_synthesis(), pipeline_for_synthesis(), Stage/headcount for AI: blank or default-zero is not a measured 0-person…, Calendar for AI: not connected / fetch failure is not the same as a free day. (+23 more)

### Community 58 - "Community 58"
Cohesion: 0.09
Nodes (30): detect_runway_risk(), detect_stalled_department_item(), Fire if runway < 6 months, or burn rose materially month over month. Missing…, Flag open department records with no `updated_at` movement past…, _validate_decision_draft(), Unit tests for decision_engine detectors + LLM draft validation + rate limit., Disabled departments are omitted by the caller; no extra signals., _sess() (+22 more)

### Community 59 - "Community 59"
Cohesion: 0.12
Nodes (30): anthropic, AsyncAnthropic, anthropic_configured(), _coerce_label(), combine_daily_report_digest(), complete(), _current_month(), draft_decision() (+22 more)

### Community 60 - "Community 60"
Cohesion: 0.12
Nodes (28): assemble_financial_export(), _expand_ledger(), _fill(), format_export_amount(), period_label(), period_line_items(), Any, datetime (+20 more)

### Community 61 - "Community 61"
Cohesion: 0.09
Nodes (30): get_lifetime_extract_count(), ai_extracts_lifetime_limit(), ai_extracts_limit(), ask_helm_monthly_limit(), is_paid_plan(), normalize_plan(), plan_def(), Map legacy/unknown plans to a canonical id. Existing paying workspaces stored… (+22 more)

### Community 62 - "Community 62"
Cohesion: 0.08
Nodes (21): _sign_state(), client(), fixture, Free-tier AI briefing must persist on GET /briefing (not stripped by is_pro)., Google OAuth callback must never 500 after the user clicks Allow., test_google_callback_never_500s_on_unexpected_error(), test_google_callback_succeeds_with_naive_state_expiry(), test_quickbooks_callback_save_failure_includes_provider() (+13 more)

### Community 63 - "Community 63"
Cohesion: 0.11
Nodes (29): collect_signals(), detect_missed_followups(), detect_overdue_procurement_requests(), detect_overdue_tasks(), detect_overdue_work_orders(), detect_recurring_blockers(), detect_upcoming_followups(), detect_upcoming_legal_deadlines() (+21 more)

### Community 64 - "Community 64"
Cohesion: 0.10
Nodes (25): acquire_lifetime_extract_slot(), acquire_period_ask_slot(), acquire_period_extract_slot(), acquire_seat_slot(), get_period_ask_count(), Atomically consume one AI-extract slot for the billing period. False when at…, Return one period extract slot after a failed/aborted extract., Ask Trenston messages used in this billing period (separate from AI extracts). (+17 more)

### Community 65 - "Community 65"
Cohesion: 0.14
Nodes (28): buildHeatmapQuarterSeparatorGroups(), buildHeatmapRowOpacity(), CALENDAR_QUARTER_START_MONTHS, countHeatmapWeekDaysOnOrAfter(), filterHeatmapColumns(), findHeatmapColumnIndexForDate(), getCalendarQuarter(), getCalendarQuarterStartDatesBetween() (+20 more)

### Community 66 - "Community 66"
Cohesion: 0.10
Nodes (19): clear_access_ids_cache(), Drop request memo (tests)., _clear_memo(), _Coll, _Cursor, _mock_db(), asyncio, fixture (+11 more)

### Community 67 - "Community 67"
Cohesion: 0.10
Nodes (14): _iso_week_key(), UTC ISO week id for weekly digest debounce (e.g. 2026-W38)., _Cursor, asyncio, Proactive daily alerts + weekly digest cron runners and internal endpoints., test_iso_week_key_format(), test_run_daily_alerts_isolates_workspace_failures(), test_run_daily_briefing_emails_and_debounces() (+6 more)

### Community 68 - "Community 68"
Cohesion: 0.11
Nodes (24): argparse, _created_at_sort_key(), _entity_hint_from_doc(), legacy_dated_patterns_for_stable(), main(), migrate(), Any, qb_entity_slug_from_hints() (+16 more)

### Community 69 - "Community 69"
Cohesion: 0.13
Nodes (23): is_possibly_stale(), item_timestamp(), _latest_collection_ts(), _max_ts(), parse_iso_ts(), pick_data_as_of(), Any, datetime (+15 more)

### Community 70 - "Community 70"
Cohesion: 0.13
Nodes (26): _auth_headers(), _fetch_company_names(), _fetch_deal_company_ids(), fetch_deals(), _fetch_stage_labels(), HubSpotAuthError, _list_or_search_deals(), map_hubspot_deal() (+18 more)

### Community 71 - "Community 71"
Cohesion: 0.11
Nodes (14): decode_cursor(), deals_client(), mock_principal(), FakeAggregateCursor, FakeCollection, FakeCursor, _make_deals(), _pagination_db() (+6 more)

### Community 72 - "Community 72"
Cohesion: 0.12
Nodes (25): financials_for_synthesis(), format_mrr_display(), format_runway_display(), Human runway label: months, profitable/breakeven, or missing-data copy., MRR label: formatted amount, confirmed $0, or missing-data copy — never fake $0., Numbers for AI prompts: missing fields stay null instead of looking like $0., _entries_cursor(), Null-vs-zero for MRR/runway: expense-only ≠ $0 MRR; profitable ≠ missing runway. (+17 more)

### Community 73 - "Community 73"
Cohesion: 0.07
Nodes (6): client(), fixture, Document upload + AI extraction for financial entries., test_cleanup_deletes_old_uncommitted_documents(), test_extract_returns_cached_result_without_second_claude_call(), test_rate_limit_scoped_per_workspace()

### Community 74 - "Community 74"
Cohesion: 0.12
Nodes (19): CHART_CLIP_PASSTHROUGH, CLIP_EXCLUDED_COMPONENT_NAMES, isChartClipPassthrough(), resolveChartChildElement(), UNDERLAY_COMPONENT_NAMES, getChildComponentName(), isHeatmapSeparatorElement(), normalizeHeatmapSeparatorConfig() (+11 more)

### Community 75 - "Community 75"
Cohesion: 0.14
Nodes (24): compute_next_due_at(), contracts_needing_attention(), enrich_contract(), enrich_schedule(), enrich_spare(), equipment_key(), overdue_schedules(), overhead_rollup() (+16 more)

### Community 76 - "Community 76"
Cohesion: 0.18
Nodes (25): CalendarPage, addDays(), AgendaSidebar(), CalendarPage(), DAY_LABELS, durationBetween(), endTimeFromStart(), eventCoversDay() (+17 more)

### Community 77 - "Community 77"
Cohesion: 0.11
Nodes (24): financial_pdf_filename(), financial_xlsx_filename(), test_pdf_filename_includes_workspace_and_date(), test_pdf_filename_strips_unsafe_chars(), test_render_rejects_empty(), test_render_weekly_pack_pdf_is_legible_pdf(), _inline_xml(), markdown_to_flowables() (+16 more)

### Community 78 - "Community 78"
Cohesion: 0.14
Nodes (18): trial_reminder_due(), asyncio, Trial-ending and inactivity retention emails — no live Resend required., test_bullets_are_specific(), test_empty_workspace_has_no_bullets(), test_endpoint_runs_with_cron_header(), test_inactivity_can_fire_again_after_return(), test_inactivity_due_after_five_days() (+10 more)

### Community 79 - "Community 79"
Cohesion: 0.09
Nodes (5): CollStore, leave_api(), _match(), fixture, HR leave / time-off request API + calendar range visibility.

### Community 80 - "Community 80"
Cohesion: 0.17
Nodes (17): ChartConfigContext, DEFAULT_CHART_CONFIG, resolveTooltipBoxMotion(), useChartConfig(), chartCssVars, ChartTooltip(), ChartTooltipInner, DatePillTrackerInner() (+9 more)

### Community 81 - "Community 81"
Cohesion: 0.14
Nodes (19): RingCenter(), generateRingArcPath(), isRing(), isRingCenter(), RingChartCore, defaultRingColors, ringCssVars, RingHoverContext (+11 more)

### Community 82 - "Community 82"
Cohesion: 0.16
Nodes (23): clerk_jwt_audiences(), clerk_jwt_issuer(), decode_clerk_jwt(), Verify JWT signature against async-cached public JWKS. Defense-in-depth…, Verify Clerk session JWT — BAPI session check first (Render-safe), JWKS…, Clerk Frontend API URL — the `iss` claim on session tokens. Derived from…, Accepted `aud` values when a session/API token includes an audience claim.…, _verify_clerk_jwt_jwks() (+15 more)

### Community 83 - "Community 83"
Cohesion: 0.12
Nodes (23): attribute_signup(), ensure_referral_code(), generate_referral_code(), list_referrals_for_user(), lookup_referrer_by_code(), mark_referral_converted(), _normalize_email(), normalize_referral_code() (+15 more)

### Community 84 - "Community 84"
Cohesion: 0.11
Nodes (18): _briefing_what_to_decide(), Pending decisions + AI suggestions for the Briefing column., mongo(), asyncio, fixture, In-process tests for insights generation, rate limits, and briefing wiring., If every AI draft fails, do not wipe suggestions or stamp insights_generated_at., One failed draft must not erase that signal when others succeed. (+10 more)

### Community 85 - "Community 85"
Cohesion: 0.10
Nodes (24): _complete_oauth_callback(), _persist_tokens(), integration_connect(), oauth_callback(), _oauth_callback_uri(), _oauth_datetime_expired(), _oauth_error_reason_from_token_response(), _oauth_fail_redirect() (+16 more)

### Community 86 - "Community 86"
Cohesion: 0.13
Nodes (22): _me_work_due(), _me_work_row(), date, _cursor(), asyncio, test_collect_for_user_respects_dept_scope(), test_workload_counts_batched_and_overdue(), depts_find() (+14 more)

### Community 87 - "Community 87"
Cohesion: 0.17
Nodes (22): _aware(), build_draft_doc(), completion_time(), dismiss_draft(), filter_completed(), in_week(), list_open_drafts(), mark_published() (+14 more)

### Community 88 - "Community 88"
Cohesion: 0.10
Nodes (10): member(), owner(), fixture, Iteration 5 — computed telemetry/reports + decisions CRUD. Covers: - Decisions…, _sess(), TestCalendarLiveFlag, TestIntegrationsPrompt, TestOnboardingChecklist (+2 more)

### Community 89 - "Community 89"
Cohesion: 0.11
Nodes (10): _create_deal(), DealStore, DocStore, fixture, Won deal → automatic revenue entry + production prompt., test_no_production_prompt_when_production_disabled(), test_resaving_won_does_not_duplicate_entry(), test_won_creates_revenue_entry_and_production_prompt() (+2 more)

### Community 90 - "Community 90"
Cohesion: 0.09
Nodes (4): dept_api(), FakeDepartments, FakeDeptMembers, fixture

### Community 91 - "Community 91"
Cohesion: 0.10
Nodes (8): member(), mongo(), owner(), fixture, parametrize, Iteration 4 tests: Access Packs (Phase 0), Activity/Briefing loop (Phase 1),…, _sess(), test_regression_owner_reads()

### Community 92 - "Community 92"
Cohesion: 0.13
Nodes (20): build_alert_email_html(), build_slack_text(), _esc(), high_severity_suggestions(), new_high_alerts(), Any, Best-effort high-severity alert notifications (email + optional Slack)., Stable fingerprint for debounce across regenerations. (+12 more)

### Community 93 - "Community 93"
Cohesion: 0.13
Nodes (20): _cached_health(), clerk_api_ok(), clerk_jwks_ok(), ensure_allowed_origins(), _fetch_bapi_jwks_sync(), fetch_clerk_user_profile(), _fetch_jwks_sync(), _fetch_public_jwks_sync() (+12 more)

### Community 94 - "Community 94"
Cohesion: 0.12
Nodes (21): expense_totals_by_month_category(), personal_later_card_from_signal(), Build {YYYY-MM: {category: amount}} from financial_entries (expense only).…, Whether the CEO can hand work to someone else. Explicit `has_team` on the…, Solo-founder stand-in for a delegate draft: no assignee, flag-for-later only., workspace_has_team(), _briefing_what_to_delegate(), _generate_insights() (+13 more)

### Community 95 - "Community 95"
Cohesion: 0.12
Nodes (15): _validate_report_summary(), client(), asyncio, fixture, Report digest: spreadsheet text conversion + upload/summarize API., test_bills_upload_still_rejects_xlsx(), test_combine_digest_uses_fast_model(), test_report_summarize_xlsx() (+7 more)

### Community 96 - "Community 96"
Cohesion: 0.17
Nodes (21): _add_months(), billing_anchor(), current_usage_period(), get_monthly_extract_count(), get_period_extract_count(), increment_lifetime_extract(), increment_monthly_extract(), increment_period_extract() (+13 more)

### Community 97 - "Community 97"
Cohesion: 0.13
Nodes (19): analytics_summary(), _count_by_meta(), _distinct_workspaces(), emit_billing_funnel(), log_event(), log_event_once(), Any, First-party product usage events — Trenston's MongoDB only, no third-party… (+11 more)

### Community 98 - "Community 98"
Cohesion: 0.16
Nodes (18): One-time migration: seal plaintext google_tokens / quickbooks_tokens at rest.…, _config(), _h(), mongo(), fixture, Iteration 6 tests: Paddle Billing. Webhook POSTs are sent to the LOCAL app…, _sign(), test_billing_plans_paddle_ready() (+10 more)

### Community 99 - "Community 99"
Cohesion: 0.17
Nodes (21): _access_by_type(), _ask_period(), _enabled_by_type(), _mock_coll(), asyncio, Flatten ask_helm system prompt (str or Anthropic content-block list) for…, Sales member: sales data in prompt; every other dept restricted; no raw foreign…, Integration with real helper: non-member gets no rows; filter applied for… (+13 more)

### Community 100 - "Community 100"
Cohesion: 0.16
Nodes (18): _access_token(), document_ai_configured(), _entity_amount(), _entity_month(), _entity_text(), extract_invoice(), map_invoice_document(), processor_name() (+10 more)

### Community 101 - "Community 101"
Cohesion: 0.11
Nodes (17): _load_financial(), _load_reports(), loader(), mongo(), owner(), asyncio, fixture, Weekly CEO Pack context + report trend snapshot behavior. (+9 more)

### Community 102 - "Community 102"
Cohesion: 0.13
Nodes (16): _enforce_production_config(), Refuse to boot with known-insecure settings when ENVIRONMENT=production., Read a bounded upload and verify its bytes match the claimed media type., _read_validated_document(), parametrize, UploadFile, Security helpers and production guardrails., test_allowed_auth_redirect() (+8 more)

### Community 103 - "Community 103"
Cohesion: 0.11
Nodes (8): _empty_cursor(), isolation_api(), chat_find(), mem_find(), fixture, parametrize, Workspace isolation, role gates, and auth guards (replaces legacy live Kalun…, test_unauthenticated_read_returns_401()

### Community 104 - "Community 104"
Cohesion: 0.10
Nodes (20): aliases, components, hooks, lib, ui, utils, iconLibrary, registries (+12 more)

### Community 105 - "Community 105"
Cohesion: 0.15
Nodes (19): enroll_user_in_sales_finance(), ensure_department_member(), ensure_enabled_department(), finance_department_id(), get_enabled_department(), get_enabled_departments_by_type(), migrate_all_workspaces_sales_finance(), migrate_workspace_sales_finance() (+11 more)

### Community 106 - "Community 106"
Cohesion: 0.19
Nodes (18): current_month(), is_current_or_past_month(), is_future_month(), is_valid_month(), partition_ledger_entries(), datetime, Recurring financial entry helpers — monthly/annual expansion for burn/runway.…, Latest month to expand recurring entries through for burn/MRR/runway. Always… (+10 more)

### Community 107 - "Community 107"
Cohesion: 0.21
Nodes (19): briefing_url(), collect_change_bullets(), days_inactive(), effective_trial_end(), _email_shell(), _esc(), inactivity_email_html(), inactivity_nudge_due() (+11 more)

### Community 108 - "Community 108"
Cohesion: 0.23
Nodes (19): ask_context_for_synthesis(), _ask_dept_restricted(), _ask_slice_context(), Enabled → membership → data. Disabled → not tracked. No access → restricted., Ask Trenston snapshot: live facts only, with unknown vs confirmed-zero…, _company(), _deals(), _legal() (+11 more)

### Community 109 - "Community 109"
Cohesion: 0.15
Nodes (14): mongo_db(), Shared helpers for Trenston backend integration tests., set_workspace_plan(), workspace_id_for(), member(), member_dept_engineering(), mongo(), owner() (+6 more)

### Community 110 - "Community 110"
Cohesion: 0.12
Nodes (4): DocStore, _match_query(), ops_api(), fixture

### Community 111 - "Community 111"
Cohesion: 0.10
Nodes (3): Procurement request queue API tests., Requests linked to awaiting/blocked work orders float to the top with badges., test_blocking_production_orders_enrichment_and_sort()

### Community 112 - "Community 112"
Cohesion: 0.13
Nodes (18): Delta(), AnimatedMetricValue(), BentoGrid(), cardWidthClass(), groupMetricsBySection(), MetricTile(), parseMetricValue(), resolveStatus() (+10 more)

### Community 113 - "Community 113"
Cohesion: 0.14
Nodes (17): api_unsubscribe_url(), _b64decode(), _b64encode(), list_unsubscribe_headers(), make_unsubscribe_token(), parse_unsubscribe_token(), CAN-SPAM / marketing-email compliance helpers for Resend sends. Classification…, Direct API URL for List-Unsubscribe / one-click POST. (+9 more)

### Community 114 - "Community 114"
Cohesion: 0.20
Nodes (18): attach_lead_time_metrics(), _days_between(), department_lead_time_summary(), is_currently_late(), lead_time_metrics(), _mean(), _parse_date(), _parse_iso_dt() (+10 more)

### Community 115 - "Community 115"
Cohesion: 0.18
Nodes (18): add_months(), attribute_month(), compute_total(), _created_month(), current_month(), next_n_months(), normalize_month(), order_book_summary() (+10 more)

### Community 116 - "Community 116"
Cohesion: 0.12
Nodes (7): DocStore, _match(), fixture, GET /api/me/work-items — cross-department personal work feed., Member is assigned on a Legal matter but is not a Legal member — must not…, test_inaccessible_department_assignment_hidden(), work_api()

### Community 117 - "Community 117"
Cohesion: 0.13
Nodes (4): DocStore, _match(), prod_api(), fixture

### Community 118 - "Community 118"
Cohesion: 0.12
Nodes (6): asyncio, _Resp, test_qb_query_incomplete_when_max_pages_hit(), get(), test_qb_query_paginates_until_short_page(), test_xero_pages_until_short()

### Community 119 - "Community 119"
Cohesion: 0.15
Nodes (17): Production, CATEGORY_LABELS, CLOSED, compareOrders(), emptyDailyLog(), emptyForm(), formatCycleTime(), formatQty() (+9 more)

### Community 120 - "Community 120"
Cohesion: 0.22
Nodes (14): chartCenterContainerClassName, chartCenterLabelClassName, chartCenterValueClassName, ChartStatFlow(), defaultChartStatFlowFormat, formatStatValue(), useNumberFlowElementReady(), crossAxisAlign (+6 more)

### Community 121 - "Community 121"
Cohesion: 0.18
Nodes (13): extractReferenceAreaConfigs(), getChildComponentName(), isReferenceAreaElement(), useChartInteraction(), defaultDedupeKey(), useScheduledTooltip(), buildYScalesForLines(), buildYScalesFromDomains() (+5 more)

### Community 122 - "Community 122"
Cohesion: 0.16
Nodes (17): classify_refresh_http_failure(), classify_refresh_transport_error(), _error_code_from_body(), IntegrationRetryableError, is_revoked_refresh_response(), Exception, Response, Shared OAuth/integration error classification helpers. (+9 more)

### Community 123 - "Community 123"
Cohesion: 0.18
Nodes (16): merge_integrations(), Any, Canonical integration definitions — user-facing connectable services only.…, Build user integration cards with live connection status. Google Calendar/Gmail…, _token_scope(), Integration catalog merge and status tests., Legacy workspace-level google_tokens must not mark the user as connected., test_coming_soon_integrations() (+8 more)

### Community 124 - "Community 124"
Cohesion: 0.18
Nodes (11): DocStore, _get_calendar(), _match(), fixture, Department-scoped calendar read visibility (helm events + derived deadlines)., test_finance_event_visible_to_finance_and_ceo_only(), test_legacy_event_without_visibility_is_personal(), test_member_two_departments_sees_both() (+3 more)

### Community 125 - "Community 125"
Cohesion: 0.13
Nodes (4): maint_api(), _match_query(), fixture, TicketStore

### Community 126 - "Community 126"
Cohesion: 0.25
Nodes (15): DEFAULT_NOTCH_ENTER_TRANSITION, GaugeArcInner(), GaugeLinearInner(), GaugeNotchSvg(), useGaugeFillState(), collectGaugeDefsElements(), createNotchPath(), DEFAULT_ACTIVE_FILL_OPACITY (+7 more)

### Community 127 - "Community 127"
Cohesion: 0.12
Nodes (5): DealStore, owner_api(), fixture, _users_find_factory(), find()

### Community 128 - "Community 128"
Cohesion: 0.17
Nodes (13): _cursor(), asyncio, _Result, _store(), delete_one(), find_one(), update_one(), test_dismiss_and_publish_endpoints() (+5 more)

### Community 129 - "Community 129"
Cohesion: 0.15
Nodes (8): _Cursor, library_client(), fixture, Document library + download audit logging., test_financial_document_get_logs_download(), test_library_owner_sees_all_contexts_without_presigned_urls(), as_owner(), test_report_document_get_logs_download()

### Community 130 - "Community 130"
Cohesion: 0.12
Nodes (3): legal_api(), MatterStore, fixture

### Community 131 - "Community 131"
Cohesion: 0.14
Nodes (4): _match_query(), proc_api(), fixture, RequestStore

### Community 132 - "Community 132"
Cohesion: 0.13
Nodes (8): asyncio, Sales & Accounting/Finance department migration + access filtering., Unit-level: sales_department_id helper returns Sales dept id., Concurrent first-enable must not 500 on unique (workspace_id, type)., test_apply_department_filter(), test_create_deal_auto_department_id_unit(), test_ensure_enabled_department_handles_insert_race(), test_migration_idempotent_creates_enrolls_backfills()

### Community 133 - "Community 133"
Cohesion: 0.14
Nodes (4): DocStore, _match_query(), fixture, sales_api()

### Community 134 - "Community 134"
Cohesion: 0.18
Nodes (15): apply_exchange_rate(), entry_amount_for_totals(), entry_signed_amount(), fallback_category(), normalize_mapped_amount(), Any, Shared financial_entries shape for QuickBooks, Xero, and SAP B1 mappers. Stable…, Return (non-negative amount, is_credit). Credits/refunds (negative source… (+7 more)

### Community 135 - "Community 135"
Cohesion: 0.16
Nodes (16): clerk_keys_aligned(), clerk_secret_mode(), clerk_secret_publishable_mode_match(), derive_publishable_key_from_jwks(), publishable_key_instance_host(), Derive pk_* from JWKS host when CLERK_PUBLISHABLE_KEY is unset on Render., Decode the Clerk frontend host embedded in a publishable key., True when publishable key and JWKS URL refer to the same Clerk frontend. (+8 more)

### Community 136 - "Community 136"
Cohesion: 0.13
Nodes (16): detect_expense_spike(), detect_new_expense_category(), detect_stalled_deals(), _new_expense_category_threshold(), Fire per category where latest month spend is up >25% vs prior month., Material-spend floor: flat minimum, raised for large prior-month totals., Fire for categories with $0 prior-month spend and material current-month spend.…, Fire for open deals with no stage change (updated_at) in `days` days. (+8 more)

### Community 137 - "Community 137"
Cohesion: 0.22
Nodes (15): ContractInput, ContractPatch, MaintCostCreate, MaintSettingsPut, OrderBookCreate, OrderBookPatch, ProcSettingsPut, BaseModel (+7 more)

### Community 138 - "Community 138"
Cohesion: 0.12
Nodes (3): asyncio, HR per-hire onboarding API tests., test_ensure_template_idempotent()

### Community 139 - "Community 139"
Cohesion: 0.12
Nodes (3): CollStore, hr_api(), fixture

### Community 140 - "Community 140"
Cohesion: 0.12
Nodes (3): Legal matter queue API tests., Legal department members who are neither lead nor assignee get 403 on GET., test_non_assignee_cannot_download_document()

### Community 141 - "Community 141"
Cohesion: 0.12
Nodes (3): Engineering & Maintenance ticket queue API tests., Tickets linked to blocked work orders float to the top with badges., test_blocking_production_orders_enrichment_and_sort()

### Community 142 - "Community 142"
Cohesion: 0.24
Nodes (11): lerpDomain(), snapDomains(), tweenDomains(), useAnimatedYDomains(), computeYDomainsByAxis(), domainsEqual(), isYDomainTweenPhase(), mergeYDomainRecords() (+3 more)

### Community 143 - "Community 143"
Cohesion: 0.20
Nodes (13): _norm_header(), _parse_amount(), parse_financial_csv(), _parse_month(), _parse_type(), Any, Parse historical financial CSV uploads into preview rows (no DB writes).…, Return {valid: [...], skipped: [{row, reason}], parsed_row_count} without… (+5 more)

### Community 144 - "Community 144"
Cohesion: 0.23
Nodes (14): Any, Manual create/edit: a specific item name is required., require_entry_name(), add_fin_entry(), FinEntryInput, test_financial_entry_commits_its_source_document(), Financial ledger item names — distinct from category., test_add_fin_entry_maps_duplicate_key_to_409() (+6 more)

### Community 145 - "Community 145"
Cohesion: 0.13
Nodes (15): _line_category(), map_qb_transaction(), Map a QuickBooks transaction to financial_entries fields. Polarity: - Revenue:…, Refunds must lower burn the same way regardless of which mapper produced the…, Comparable fields after vendor-specific ids/notes are stripped., Same refund + bare category must yield identical type/amount/credit/category., _shape(), test_credit_reduces_expense_totals_identically() (+7 more)

### Community 146 - "Community 146"
Cohesion: 0.15
Nodes (11): ask_helm(), _ask_helm_department_slice(), AskInput, Any, Load Ask Trenston rows with the same membership rule as department pages.…, _period(), asyncio, test_ask_helm_uses_compact_json_cached_system_and_capped_tokens() (+3 more)

### Community 148 - "Community 148"
Cohesion: 0.13
Nodes (15): devDependencies, autoprefixer, @babel/plugin-proposal-private-property-in-object, @craco/craco, dotenv, eslint, @eslint/js, eslint-plugin-import (+7 more)

### Community 149 - "Community 149"
Cohesion: 0.29
Nodes (10): _briefing_gmail_swr(), _gmail_briefing_cache_key(), Serve cached Gmail threads immediately; refresh in the background when soft-…, asyncio, Briefing Gmail stale-while-revalidate + parallel assembly., test_gmail_cold_miss_single_flight(), test_gmail_swr_cold_miss_awaits_live_fetch(), test_gmail_swr_serves_cache_without_waiting_on_live_fetch() (+2 more)

### Community 150 - "Community 150"
Cohesion: 0.19
Nodes (10): _ensure_procurement_expense_entry(), _procurement_expense_month(), YYYY-MM from delivery / order date when parseable, else current UTC month., Create (or refresh) one expense financial_entries row for a delivered request.…, FinStore, asyncio, test_delivered_priced_request_creates_expense(), test_idempotent_then_updates_cost() (+2 more)

### Community 151 - "Community 151"
Cohesion: 0.14
Nodes (6): Department framework foundation tests., Industry (e.g. SaaS) must not gate which catalog departments a CEO can enable., Re-enabling must reuse the soft-disabled id so old deals stay visible., test_disable_reenable_keeps_department_id_for_deals(), test_enable_ignores_workspace_industry(), test_is_workspace_ceo()

### Community 152 - "Community 152"
Cohesion: 0.14
Nodes (3): fixture, RequestStore, settings_api()

### Community 153 - "Community 153"
Cohesion: 0.22
Nodes (12): defaultHeatmapColorScale, useHeatmapInteractionOptional(), HEATMAP_INACTIVE_TRANSITION, HeatmapLegendGradient, HEATMAP_INACTIVE_TRANSITION, HEATMAP_LEGEND_LEVELS, HeatmapLegend, buildHeatmapLegendGradient() (+4 more)

### Community 154 - "Community 154"
Cohesion: 0.14
Nodes (13): build, env, GENERATE_SOURCEMAP, REACT_APP_CLERK_PUBLISHABLE_KEY, REACT_APP_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL, REACT_APP_CLERK_SIGN_IN_URL, REACT_APP_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL, REACT_APP_CLERK_SIGN_UP_URL (+5 more)

### Community 155 - "Community 155"
Cohesion: 0.27
Nodes (12): draft_gmail_reply(), fallback_gmail_draft_body(), Template used when AI is unavailable — never invents conversation details., AI-written Gmail reply body with Trenston disclaimer. Falls back on any AI…, asyncio, Gmail draft replies: AI body when available, template fallback when not., test_ai_draft_empty_snippet_still_calls_model_with_guardrail(), test_ai_draft_uses_model_text_and_appends_disclaimer() (+4 more)

### Community 156 - "Community 156"
Cohesion: 0.24
Nodes (12): _paddle_price_id_from_event(), _paddle_provision(), Best-effort price id from a Paddle Billing subscription/transaction payload., asyncio, Unit tests for Paddle provision plan mapping (no live webhook required)., P0 regression: TTL'd/missing intent must not ACK-and-drop a paid checkout., test_atomic_intent_claim_before_entitlements(), test_missing_intent_still_provisions_from_custom_data() (+4 more)

### Community 157 - "Community 157"
Cohesion: 0.18
Nodes (7): asyncio, Weekly CEO Pack PDF export — no LLM, no rewards., test_export_pdf_endpoint_returns_attachment(), mock_principal(), test_export_pdf_forbidden_without_pack_perm(), test_export_pdf_rejects_empty_body(), test_weekly_pack_system_prompt_has_no_board()

### Community 158 - "Community 158"
Cohesion: 0.24
Nodes (10): Background(), clampFadeLength(), fadeMaskStops(), ChartHoverContext, ChartStableContext, defaultScatterColors, useChart(), useChartHover() (+2 more)

### Community 159 - "Community 159"
Cohesion: 0.26
Nodes (7): HSegment(), hSegmentPath(), SegmentLabel(), VSegment(), vSegmentPath(), useEnterComplete(), useMountProgress()

### Community 160 - "Community 160"
Cohesion: 0.23
Nodes (11): PieCenter(), PieCenterShell(), defaultPieColors, pieCssVars, PieHoverContext, PieProvider(), PieStableContext, usePie() (+3 more)

### Community 161 - "Community 161"
Cohesion: 0.33
Nodes (11): ClerkHelmBridge(), exchangeClerkSession(), sleep(), AuthProvider(), setClerkTokenGetter(), clearClerkTokenCache(), getCachedClerkToken(), jwtExpMs() (+3 more)

### Community 162 - "Community 162"
Cohesion: 0.21
Nodes (10): is_stale_deploy_url(), Canonical Trenston URLs — single source of truth for production domain., True when Render/Vercel env still points at old preview hosts., Cookie domain that works for both apex and www (e.g. trenston.com)., registrable_cookie_domain(), Tests for helm_config URL helpers., test_is_stale_deploy_url(), test_public_api_origin_defaults_to_canonical() (+2 more)

### Community 163 - "Community 163"
Cohesion: 0.26
Nodes (10): daily_briefing_email_html(), _fmt_days(), _money(), ops_briefing_metric_cards(), Any, Shared ops briefing assembly for /briefing cards and the daily morning email.…, Map assemble_ops_briefing_data → Briefing page metric cards., Plain scannable HTML morning briefing. Reuses weekly digest CAN-SPAM footer. (+2 more)

### Community 164 - "Community 164"
Cohesion: 0.24
Nodes (10): ip_allowed(), _parse_cidrs(), Paddle webhook source IPs — fetched from https://api.paddle.com/ips, never…, Return cached IPv4 networks, refreshing from Paddle when stale., refresh_paddle_ip_networks(), reset_cache_for_tests(), Paddle webhook IP allowlist — list comes from api.paddle.com/ips., test_ip_allowed_matches_cidr() (+2 more)

### Community 165 - "Community 165"
Cohesion: 0.20
Nodes (5): member_client(), owner_client(), principal(), fixture, Activity log CSV export — owner/admin only.

### Community 166 - "Community 166"
Cohesion: 0.27
Nodes (8): _owner_principal(), mock_principal(), _patch_export_deps(), Income Statement + Cash Summary financial export., test_export_forbidden_without_finance_write(), test_export_rejects_bad_period(), test_pdf_endpoint_returns_attachment(), test_xlsx_endpoint_returns_attachment()

### Community 167 - "Community 167"
Cohesion: 0.24
Nodes (8): asyncio, Per-user Google Calendar/Gmail token storage., test_briefing_email_threads_uses_caller_tokens_only(), test_google_calendar_snapshot_no_fallback_without_user_tokens(), test_store_and_load_user_google_tokens_are_sealed(), test_store_integration_tokens_rejects_google_field(), test_store_user_google_tokens_clears_gmail_briefing_cache(), test_two_users_keep_separate_google_tokens()

### Community 168 - "Community 168"
Cohesion: 0.23
Nodes (10): assert_natural_pack_style(), pack_style_flags(), asyncio, Weekly CEO Pack writing-style contract and scenario samples., Quiet / alarming / mixed notes should not share one rigid section skeleton., Heuristic flags for AI-slop pack formatting (used in tests, not runtime)., test_natural_samples_pass_style_contract(), test_scenario_samples_differ_in_shape() (+2 more)

### Community 169 - "Community 169"
Cohesion: 0.20
Nodes (11): _clerk_google_client_id(), clerk_google_oauth_redirect_uri(), clerk_google_oauth_redirect_uris(), clerk_google_oauth_status(), Google Cloud authorized redirect URIs Clerk may send for this instance., Primary Clerk production Google OAuth callback — must match Google Cloud…, Google OAuth client ID configured in Clerk (from FAPI environment)., Probe whether Google OAuth redirect URI is registered for Clerk sign-in. (+3 more)

### Community 170 - "Community 170"
Cohesion: 0.29
Nodes (9): Shared helpers for financial ledger item names (distinct from category)., in_period(), _parse_iso_dt(), Any, datetime, Procurement spend rollups + optional department budget. Only priced requests…, Attribute spend to the period via created_at (updated_at only if missing)., spend_rollup() (+1 more)

### Community 171 - "Community 171"
Cohesion: 0.29
Nodes (9): entered_cash_amount(), parse_optional_amount(), Currency symbols and compact money formatting for Trenston. Add new codes to…, Return a float when a figure was provided; None when the field was never set.…, Cash on hand if the CEO (or finance) actually entered it. Legacy empty…, Missing cash/MRR/burn must not be coerced to zero., test_confirmed_zero_cash_is_entered(), test_legacy_zero_cash_is_not_entered() (+1 more)

### Community 172 - "Community 172"
Cohesion: 0.20
Nodes (11): _index_suggestions_by_signal(), _merge_partial_draft_fallbacks(), Stable id for matching a live signal to a prior suggestion card., Map signal fingerprint → most recent suggested card (status=suggested)., Minimal undrafted decision card so a failed LLM draft cannot drop the signal., Minimal undrafted delegate card for a failed LLM draft., Keep active signals that failed to draft via prior card or raw-signal fallback., _raw_decision_card_from_signal() (+3 more)

### Community 173 - "Community 173"
Cohesion: 0.29
Nodes (10): _mongo_candidate_urls(), add(), add_pserv(), Ordered Mongo URLs to try — Render pserv first unless USE_ATLAS_MONGO=true., Mongo URL candidate ordering for Render vs Atlas., test_atlas_only_when_use_atlas_true(), test_local_mongo_url_only(), test_mongo_host_override() (+2 more)

### Community 174 - "Community 174"
Cohesion: 0.25
Nodes (9): Pack integrations:manage + plan allows this specific provider., require_integration_provider(), asyncio, Per-provider plan gates on OAuth connect and sync dependencies., test_connect_free_blocks_quickbooks_allows_google(), test_integration_connect_free_plan_403_for_xero(), test_require_integration_provider_allows_starter_quickbooks(), test_require_integration_provider_plan_reason() (+1 more)

### Community 175 - "Community 175"
Cohesion: 0.20
Nodes (4): client_and_store(), FakeDeals, fixture, Deal created_by attribution is set at create and immutable on update.

### Community 176 - "Community 176"
Cohesion: 0.18
Nodes (5): Coll, asyncio, test_department_signal_inputs_skips_disabled_types(), asyncio, test_department_signal_inputs_loads_leave_when_hr_enabled()

### Community 177 - "Community 177"
Cohesion: 0.24
Nodes (8): _csv_to_text(), Convert uploaded report spreadsheets into plain text for LLM summarization., Return (markdown-ish table text, truncated). Caps rows and characters so a…, spreadsheet_bytes_to_text(), _xlsx_to_text(), test_csv_to_text_includes_figures_and_caps_rows(), csv, io

### Community 179 - "Community 179"
Cohesion: 0.27
Nodes (6): asyncio, test_notify_debounce_and_slack_failure_non_blocking(), fake_email(), fake_recipients(), fake_slack(), test_notify_does_not_debounce_when_both_channels_fail()

### Community 180 - "Community 180"
Cohesion: 0.31
Nodes (7): filter_unsuppressed(), is_suppressed(), normalize_email(), Immediate suppression (honored on the next send — no batch delay)., suppress_email(), asyncio, test_suppress_then_filter()

### Community 181 - "Community 181"
Cohesion: 0.33
Nodes (8): _decision_owner_is_self(), _heal_self_delegated_decisions(), True when a delegate/owner label refers to the acting principal (e.g. Myself)., Delegating to yourself must stay actionable — rewrite stuck status=delegated…, Self-delegation must keep a decision actionable (pending), not terminal., test_decision_owner_is_self_myself_and_name(), test_heal_noop_when_nothing_stuck(), test_heal_self_delegated_rewrites_status_to_pending()

### Community 182 - "Community 182"
Cohesion: 0.31
Nodes (8): message_requests_financials(), True when an Ask Trenston message is asking for gated financial figures., parametrize, Financial access: report cards, Ask Trenston context, restricted markers., _sample_fin(), test_ask_context_restricts_financials_when_not_visible(), test_computed_report_cards_omit_money_when_no_fin_access(), test_message_requests_financials()

### Community 183 - "Community 183"
Cohesion: 0.47
Nodes (8): asyncio, Unit tests for atomic decision updates + action allowlist., test_create_decision_uses_push(), test_decision_action_rejects_terminal_transition(), test_decision_action_rejects_unknown_action(), test_decision_action_uses_array_filters(), test_delete_decision_uses_pull(), _ws()

### Community 184 - "Community 184"
Cohesion: 0.28
Nodes (4): Document AI daily spend caps — skip parser, keep Claude., test_document_ai_workspace_and_global_caps(), test_document_ai_zero_limit_is_kill_switch(), _usage_db()

### Community 185 - "Community 185"
Cohesion: 0.22
Nodes (8): background_color, description, display, icons, name, short_name, start_url, theme_color

### Community 186 - "Community 186"
Cohesion: 0.31
Nodes (5): clipRevealTransition(), DEFAULT_ANIMATION_DURATION_MS, DEFAULT_ANIMATION_EASING, DEFAULT_CHART_ENTER_TRANSITION, ChartRevealClip()

### Community 187 - "Community 187"
Cohesion: 0.36
Nodes (7): COMPANY_STAGES, FOUNDER_ROLES, INDUSTRIES, SETUP_STEPS, TEAM_SIZES, CompanySetup(), ROLE_ICONS

### Community 188 - "Community 188"
Cohesion: 0.25
Nodes (3): DealStore, next_step_api(), fixture

### Community 189 - "Community 189"
Cohesion: 0.25
Nodes (3): test_ensure_session_rejects_rebinding_to_private(), test_normalize_rejects_http_and_private_targets(), _private_dns()

### Community 190 - "Community 190"
Cohesion: 0.32
Nodes (5): asyncio, Task delegation email notifications., test_notify_sends_only_when_assignee_changes(), test_notify_skips_self_assign_and_survives_send_failure(), test_send_notification_email_wraps_resend()

### Community 191 - "Community 191"
Cohesion: 0.46
Nodes (7): collectChartDefsChildren(), getChartChildComponentName(), isChartDefsComponent(), isGradientDefComponent(), isPatternDefComponent(), partitionChartDefNodes(), VISX_PATTERN_COMPONENT_NAMES

### Community 192 - "Community 192"
Cohesion: 0.36
Nodes (6): ChartLoadingLabel(), LINE_LOADING_LOOP_PAUSE_MS, LINE_LOADING_PULSE_CYCLE_S, LINE_LOADING_PULSE_EASE, LOADING_LABEL_EXIT_S, LOADING_LABEL_EXIT_Y_PX

### Community 193 - "Community 193"
Cohesion: 0.29
Nodes (7): _fetch_jwks_async(), prefetch_jwks(), Warm JWKS cache at startup (async — works on Render)., JWKS from public Clerk URL using async httpx (Render-safe)., shutdown_db_client(), startup(), on_event

### Community 194 - "Community 194"
Cohesion: 0.29
Nodes (7): compute_impact_score(), rank_and_cap_signals(), Comparable impact proxy for tie-breaks within a severity tier. Dollars (deal…, Sort by severity, then impact (desc); truncate and log when over cap., Same-severity overflow must keep high-impact late-alphabet types.…, test_compute_impact_score_normalizes_dollars_days_hours(), test_rank_and_cap_prefers_impact_over_alphabetical_type()

### Community 195 - "Community 195"
Cohesion: 0.29
Nodes (4): _backfill_financial_entry_names(), Set name = category on legacy ledger rows that have no item name. Idempotent., _Cursor, test_backfill_sets_missing_name_to_category()

### Community 196 - "Community 196"
Cohesion: 0.38
Nodes (6): Pack permission + optional plan feature gate (Free keeps core cockpit writes)., require_pro_perm(), asyncio, require_pro_perm distinguishes permission vs plan 403 bodies., test_require_pro_perm_permission_reason(), test_require_pro_perm_plan_reason_for_ask()

### Community 197 - "Community 197"
Cohesion: 0.29
Nodes (7): scripts, build, check-pricing-drift, prerender, start, sync-llms, test

### Community 198 - "Community 198"
Cohesion: 0.38
Nodes (6): formatBytes(), formatDuration(), os, SERVER_START_TIME, setupHealthEndpoints(), ref_os

### Community 200 - "Community 200"
Cohesion: 0.38
Nodes (5): hmsTimeFmt, intFmt, shortDateFmt, weekdayDateFmt, TooltipContent()

### Community 201 - "Community 201"
Cohesion: 0.29
Nodes (4): LOGIN, LOGOUT, REGISTER, HOME

### Community 202 - "Community 202"
Cohesion: 0.38
Nodes (4): HELM_FLAGGED, HELM_PALETTE, palette, { HELM_PALETTE, HELM_FLAGGED }

### Community 203 - "Community 203"
Cohesion: 0.33
Nodes (4): clerk_proxy_url(), proxy_clerk_fapi(), Public Clerk FAPI proxy — must be on Clerk primary apex (trenston.com), not www., Proxy Clerk Frontend API when clerk.* custom-domain TLS is not ready.

### Community 204 - "Community 204"
Cohesion: 0.33
Nodes (5): Blocking production first, then unresolved, then high → medium → low, then…, In-progress first, then newest., _sort_hr_instances(), _sort_maintenance_tickets(), key()

### Community 205 - "Community 205"
Cohesion: 0.33
Nodes (5): cloudflare, cloudflare-bindings, cloudflare-builds, cloudflare-docs, cloudflare-observability

### Community 206 - "Community 206"
Cohesion: 0.67
Nodes (4): indicatorFadeGradientStops(), resolveVerticalFadeSides(), resolveWidth(), TooltipIndicatorInner()

### Community 207 - "Community 207"
Cohesion: 0.40
Nodes (5): _jwt_payload_unverified(), Parse JWT payload without signature verification (for sid/sub only)., Verify session by checking sid with Clerk Backend API (no local JWKS/crypto)., _verify_clerk_session_via_bapi(), test_jwt_payload_unverified_extracts_sid_sub()

### Community 208 - "Community 208"
Cohesion: 0.40
Nodes (5): _advance_legal_due_date(), Advance YYYY-MM-DD by the recurrence interval. Empty in → empty out., Create the next-cycle compliance matter once when a recurring matter is filed., _spawn_compliance_renewal(), test_advance_legal_due_date_helper()

### Community 210 - "Community 210"
Cohesion: 0.40
Nodes (4): compilerOptions, baseUrl, paths, include

### Community 211 - "Community 211"
Cohesion: 0.40
Nodes (3): Y_AXIS_DEFAULT_TICK_COUNT, Y_AXIS_MAX_TICK_COUNT, Y_AXIS_MIN_TICK_COUNT

### Community 212 - "Community 212"
Cohesion: 0.50
Nodes (4): CirNoteCard(), toastCirNote(), toastGmailDraftNote(), frontend_src_lib_notify_toast

### Community 213 - "Community 213"
Cohesion: 1.00
Nodes (3): need_arg(), validate.sh script, usage()

### Community 214 - "Community 214"
Cohesion: 0.50
Nodes (4): _patch_clerk_json(), AsyncClient, Response, PATCH https://api.clerk.com/v1/<path> — always include /v1 (bare…

### Community 215 - "Community 215"
Cohesion: 0.50
Nodes (4): inject_marketing_footer(), marketing_footer_html(), Insert CAN-SPAM footer into an existing email HTML shell. Prefers injecting a…, test_marketing_footer_has_address_and_unsubscribe()

### Community 216 - "Community 216"
Cohesion: 0.50
Nodes (4): clear_gmail_briefing_cache(), Tests / process recycle., _clear_gmail_cache(), fixture

### Community 226 - "Community 226"
Cohesion: 0.67
Nodes (3): Paddle Billing: next_billed_at (trial conversion) or current period end., trial_end_from_paddle_payload(), test_paddle_next_billed_at()

## Knowledge Gaps
- **426 isolated node(s):** `cloudflare`, `cloudflare-docs`, `cloudflare-bindings`, `cloudflare-builds`, `cloudflare-observability` (+421 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 2174 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **19 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `cn()` connect `Community 0` to `Community 3`, `Community 5`, `Community 8`, `Community 19`, `Community 20`, `Community 21`, `Community 153`, `Community 25`, `Community 28`, `Community 30`, `Community 159`, `Community 160`, `Community 37`, `Community 43`, `Community 52`, `Community 53`, `Community 187`, `Community 192`, `Community 74`, `Community 76`, `Community 80`, `Community 81`, `Community 212`, `Community 112`, `Community 119`, `Community 120`, `Community 126`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Why does `react` connect `Community 0` to `Community 3`, `Community 5`, `Community 8`, `Community 142`, `Community 19`, `Community 20`, `Community 21`, `Community 153`, `Community 25`, `Community 26`, `Community 28`, `Community 30`, `Community 159`, `Community 160`, `Community 158`, `Community 161`, `Community 37`, `Community 43`, `Community 52`, `Community 53`, `Community 187`, `Community 191`, `Community 74`, `Community 76`, `Community 206`, `Community 80`, `Community 81`, `Community 222`, `Community 112`, `Community 119`, `Community 120`, `Community 121`, `Community 126`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Why does `ops_api()` connect `Community 110` to `Community 45`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **What connects `cloudflare`, `cloudflare-docs`, `cloudflare-bindings` to the rest of the system?**
  _426 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.015544479175466757 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.024921575461833392 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.037765788638527455 - nodes in this community are weakly interconnected._