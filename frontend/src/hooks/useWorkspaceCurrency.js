import { useCompanyQuery } from "@/hooks/useCompanyQuery";
import { currencySymbol, normalizeCurrency } from "@/lib/money";

/** Workspace currency from the shared cached /company query (no extra request). */
export function useWorkspaceCurrency() {
  const { data: company } = useCompanyQuery();
  const currency = normalizeCurrency(company?.currency);
  return { currency, symbol: company?.currency_symbol || currencySymbol(currency) };
}
