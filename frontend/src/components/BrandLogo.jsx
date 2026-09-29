import { MONO_PATHS, SLACK_MONO, COLOR_MARKS } from "@/lib/integrationLogoData";

/** Maps display names used on marketing pages to integration ids. */
const NAME_TO_ID = {
  google: "google",
  "google calendar & gmail": "google",
  quickbooks: "quickbooks",
  xero: "xero",
  "sap business one": "sap_b1",
  sap: "sap_b1",
  hubspot: "hubspot",
  slack: "slack",
  github: "github",
};

export function integrationIdFor(nameOrId) {
  const key = String(nameOrId || "").trim().toLowerCase();
  return NAME_TO_ID[key] || key;
}

export function hasBrandLogo(nameOrId) {
  const id = integrationIdFor(nameOrId);
  return Boolean(COLOR_MARKS[id] || MONO_PATHS[id]);
}

/**
 * Vendor logo for an integration.
 *   variant="color": the vendor's own colour mark (in-app).
 *   variant="mono":  single-colour silhouette in currentColor (marketing site).
 */
export default function BrandLogo({ id: rawId, variant = "color", className, title }) {
  const id = integrationIdFor(rawId);

  if (variant === "mono") {
    if (id === "slack") {
      return (
        <svg
          viewBox={`0 0 ${SLACK_MONO.w} ${SLACK_MONO.h}`}
          className={className}
          role={title ? "img" : undefined}
          aria-hidden={title ? undefined : true}
          aria-label={title}
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: SLACK_MONO.body }}
        />
      );
    }
    const d = MONO_PATHS[id];
    if (!d) return null;
    return (
      <svg
        viewBox="0 0 24 24"
        className={className}
        role={title ? "img" : undefined}
        aria-hidden={title ? undefined : true}
        aria-label={title}
      >
        <path fill="currentColor" d={d} />
      </svg>
    );
  }

  const mark = COLOR_MARKS[id];
  if (!mark) return null;
  return (
    <svg
      viewBox={`0 0 ${mark.w} ${mark.h}`}
      className={className}
      preserveAspectRatio="xMidYMid meet"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      // Static, bundled SVG markup (see integrationLogoData.js); never user input.
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: mark.body }}
    />
  );
}
