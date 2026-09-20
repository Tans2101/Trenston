/** Shared Clerk SignIn/SignUp appearance — Trenston auth split (cream panel).
 *
 * Button shape notes (Clerk appearance API limits):
 * - socialButtonsBlockButton → "Continue with Google" (solid dark pill)
 * - formButtonPrimary / alternativeMethodsBlockButton → email continue (outlined pill)
 * Clerk does not expose per-provider style hooks beyond social vs form/alternative, so we
 * cannot independently restyle a second OAuth provider differently from Google. Full-width
 * stacking is supported; exact Folk-style padding/label copy is controlled by Clerk, not us.
 */
import palette from "@/design/palette.json";

export const clerkAppearance = {
  variables: {
    colorBackground: "transparent",
    colorInputBackground: "#ffffff",
    colorInputText: palette.navy,
    colorText: palette.navy,
    colorTextSecondary: palette.slate,
    colorPrimary: palette.navy,
    colorDanger: palette.statusNegative,
    colorNeutral: palette.slate,
    colorShimmer: palette.cream,
    borderRadius: "9999px",
    fontFamily: "inherit",
  },
  elements: {
    rootBox: "w-full",
    card: "bg-transparent shadow-none border-0 p-0",
    header: "hidden",
    headerTitle: "hidden",
    headerSubtitle: "hidden",
    socialButtonsBlockButton:
      "w-full justify-center rounded-full bg-helm-navy text-helm-cream border-0 font-medium hover:bg-helm-navy/90 shadow-none",
    socialButtonsBlockButtonText: "text-helm-cream font-medium",
    socialButtonsProviderIcon: "brightness-0 invert",
    alternativeMethodsBlockButton:
      "w-full justify-center rounded-full bg-transparent text-helm-navy border border-helm-navy/20 font-medium hover:bg-helm-navy/[0.04] shadow-none",
    formButtonPrimary:
      "w-full justify-center rounded-full bg-transparent text-helm-navy border border-helm-navy/25 font-medium hover:bg-helm-navy/[0.04] shadow-none",
    footerActionLink: "text-helm-navy hover:text-helm-navy/80 underline-offset-2",
    identityPreviewEditButton: "text-helm-navy",
    formFieldLabel: "text-helm-slate",
    formFieldInput:
      "rounded-full bg-white border-helm-navy/15 text-helm-navy caret-helm-gold placeholder:text-helm-slate",
    formFieldInput__input:
      "rounded-full bg-white border-helm-navy/15 text-helm-navy caret-helm-gold placeholder:text-helm-slate",
    formFieldInputShowPasswordButton: "text-helm-slate hover:text-helm-navy",
    otpCodeFieldInputs: "justify-center gap-2",
    otpCodeFieldInput:
      "bg-white border border-helm-navy/20 text-helm-navy text-lg font-mono caret-helm-gold rounded-lg",
    otpCodeFieldInput__input: "text-helm-navy bg-white",
    formResendCodeLink: "text-helm-navy hover:text-helm-navy/80",
    dividerLine: "bg-helm-navy/10",
    dividerText: "text-helm-slate",
    alertText: "text-helm-navy",
    formFieldErrorText: "text-helm-status-negative",
  },
};
