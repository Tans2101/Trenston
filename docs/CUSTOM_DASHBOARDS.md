# Custom dashboards

A done-for-you service on top of Trenston for larger companies. The client keeps all of
normal Trenston (Business plan) and gets one extra sidebar section built from a widget config.

## Who can do what

- **Operator** (Trenston): the email(s) in `ANALYTICS_ADMIN_EMAIL` on Render, with a
  Clerk-verified address. Sees **Custom clients** in the app sidebar (`/app/custom-clients`).
- **Client members**: anyone in the client company. The owner always sees the dashboard.
  With "Only approved emails can see it" on, other members need to be on the approved list.

## Flow

1. A company sends the form on `trenston.com/custom`. It is saved under **Custom clients >
   Inquiries** and emailed to the operator (reply goes straight to them). 5 per hour per network.
2. Scope it by hand, agree the tier and price (Configured / Tailored / Bespoke).
3. **Set up as client** (or **New client company**): creates their company on Business with
   `billing_source: custom` (no Paddle, invoice by hand) and invites the owner email.
   Or convert an existing Trenston company by its owner's email. A company still paying
   through Paddle must cancel first, or keep Paddle billing.
4. Edit the dashboard: title, widgets, approved emails. **Preview** uses sample data only and
   never reads the client's records. **Save** goes live on their next refresh.
5. People sign in at trenston.com with an approved, verified email and land in the company.

Self-serve plan changes are refused for custom billing; their Billing page says to contact us.

## Widgets

Standard (read live Trenston data, same permissions as the rest of the app):
`financial_kpi` (cash, burn, MRR, ARR, runway, gross margin), `revenue_expenses_chart`,
`tasks_summary`, `decisions_open`, `briefing_headline`. Money widgets show "no access" to
people without Financials.

Entered by the operator: `manual_kpi`, `manual_table`, `note`.

Bespoke: `custom` with a component id. Build the component in
`frontend/src/components/custom/`, register it in `bespoke.js`, deploy, then set the id in the
widget. Until it is registered the client sees "This part of the dashboard is still being built."

## Code

- Backend logic: `backend/custom_dashboards.py`; routes in `server.py` under "Custom dashboards".
- Tests: `backend/tests/test_custom_dashboards.py`.
- Frontend: `pages/CustomDashboards.jsx` (public), `pages/CustomDashboard.jsx` (client view),
  `pages/CustomClients.jsx` (operator), `components/custom/`.
