/** Shared Clerk SignIn/SignUp appearance — cream auth panel (light).
 *
 * Auth pages are cream/navy. Do not use ink/cream dark tokens here — global
 * dark Clerk CSS used to force cream-on-ink inputs and left black voids under
 * the form. Pill buttons use rounded-full; card radius stays modest.
 */
import palette from "@/design/palette.json";

export const clerkAppearance = {
  variables: {
    colorBackground: palette.cream,
    colorInputBackground: "#ffffff",
    colorInputText: palette.navy,
    colorText: palette.navy,
    colorTextSecondary: palette.slate,
    colorPrimary: palette.navy,
    colorDanger: palette.statusNegative,
    colorNeutral: palette.slate,
    colorShimmer: "#ffffff",
    // Modest shell radius only — never 9999px (that circled the whole card).
    borderRadius: "0.75rem",
    fontFamily: "inherit",
  },
  elements: {
    rootBox: "w-full",
    cardBox: "w-full bg-helm-cream shadow-none border-0",
    card: "w-full bg-helm-cream shadow-none border-0 p-0 gap-4",
    main: "bg-helm-cream gap-4",
    scrollBox: "bg-helm-cream",
    header: "hidden",
    headerTitle: "hidden",
    headerSubtitle: "hidden",
    // Page already has Sign in / Create account — hide Clerk footer (stops black void + duplicate link).
    footer: "hidden",
    footerAction: "hidden",
    footerActionLink: "hidden",
    socialButtons: "hidden",
    socialButtonsBlockButton: "hidden",
    socialButtonsProviderIcon: "hidden",
    dividerRow: "hidden",
    // Prefer our AuthSocialButtons (absolute www SSO callback) over Clerk's
    // built-ins, which can bounce through accounts.trenston.com.
    formButtonPrimary:
      "w-full justify-center rounded-full bg-helm-navy text-helm-cream border-0 font-medium hover:bg-helm-navy/90 shadow-none h-11",
    formFieldLabel: "text-helm-slate text-xs",
    formFieldInput:
      "rounded-full bg-white border border-helm-navy/15 text-helm-navy caret-helm-gold placeholder:text-helm-slate h-11",
    formFieldInputShowPasswordButton: "text-helm-slate hover:text-helm-navy",
    otpCodeFieldInputs: "justify-center gap-2",
    otpCodeFieldInput:
      "bg-white border border-helm-navy/20 text-helm-navy text-lg font-mono caret-helm-gold rounded-lg",
    formResendCodeLink: "text-helm-navy hover:text-helm-navy/80",
    dividerLine: "bg-helm-navy/10",
    dividerText: "text-helm-slate",
    alertText: "text-helm-navy",
    formFieldErrorText: "text-helm-status-negative",
    identityPreviewEditButton: "text-helm-navy",
    // Keep bot-protection widget in layout so signup is not blocked.
    captcha: "min-h-[65px] flex justify-center my-2",
  },
};
