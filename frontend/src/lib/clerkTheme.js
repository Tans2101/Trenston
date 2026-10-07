/** Shared Clerk SignIn/SignUp appearance — white auth panel (light), matching
 * the marketing site's black / navy / white system.
 *
 * Auth pages are white/black. Do not use ink/cream dark tokens here — global
 * dark Clerk CSS used to force cream-on-ink inputs and left black voids under
 * the form. Pill buttons use rounded-full; card radius stays modest.
 */
import palette from "@/design/palette.json";

export const clerkAppearance = {
  variables: {
    colorBackground: "#ffffff",
    colorInputBackground: "#ffffff",
    colorInputText: "#0a0a0a",
    colorText: "#0a0a0a",
    colorTextSecondary: "#555555",
    colorPrimary: "#0a0a0a",
    colorDanger: palette.statusNegative,
    colorNeutral: "#555555",
    colorShimmer: "#ffffff",
    // Modest shell radius only — never 9999px (that circled the whole card).
    borderRadius: "0.25rem",
    fontFamily: "inherit",
  },
  elements: {
    // Clerk's "Last used" pill hangs partly above the first social button, so none of the
    // containers around that button may clip (!overflow-visible beats Clerk's own rule).
    rootBox: "w-full !overflow-visible",
    cardBox: "w-full bg-white shadow-none border-0 !overflow-visible",
    card: "w-full bg-white shadow-none border-0 p-0 gap-4 !overflow-visible",
    main: "bg-white gap-4 !overflow-visible",
    scrollBox: "bg-white !overflow-visible",
    header: "hidden",
    headerTitle: "hidden",
    headerSubtitle: "hidden",
    // Page already has Sign in / Create account — hide Clerk footer (stops black void + duplicate link).
    footer: "hidden",
    footerAction: "hidden",
    footerActionLink: "hidden",
    // Native social buttons — Paths are on www now; custom AuthSocialButtons fought SignUp state.
    socialButtons: "flex flex-col gap-2 w-full !overflow-visible",
    socialButtonsBlockButton:
      "w-full h-12 justify-center rounded-[2px] border border-mk-black bg-mk-black text-white font-semibold transition-colors hover:bg-mk-navy hover:border-mk-navy shadow-none !overflow-visible",
    socialButtonsProviderIcon: "brightness-0 invert",
    dividerRow: "flex items-center gap-3 my-2",
    dividerLine: "bg-mk-line",
    dividerText: "text-mk-gray text-xs",
    formButtonPrimary:
      "w-full justify-center rounded-[2px] bg-mk-black text-white border-0 font-semibold transition-colors hover:bg-mk-navy shadow-none h-12",
    formFieldLabel: "text-mk-gray text-xs",
    formFieldInput:
      "rounded-[2px] bg-white border border-mk-line text-mk-black caret-mk-navy placeholder:text-mk-gray h-12 focus:border-mk-navy",
    formFieldInputShowPasswordButton: "text-mk-gray hover:text-mk-black",
    otpCodeFieldInputs: "justify-center gap-2",
    otpCodeFieldInput:
      "bg-white border border-mk-line text-mk-black text-lg font-mono caret-mk-navy rounded-[2px]",
    formResendCodeLink: "text-mk-navy hover:text-mk-black",
    alertText: "text-mk-black",
    formFieldErrorText: "text-helm-status-negative",
    identityPreviewEditButton: "text-mk-navy",
    // Keep bot-protection widget in layout so signup is not blocked.
    captcha: "min-h-[65px] flex justify-center my-2",
  },
};
