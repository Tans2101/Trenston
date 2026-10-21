/**
 * Bespoke widgets for custom-dashboard clients.
 *
 * A widget of type "custom" in a client's config names a component id, for
 * example { type: "custom", params: { component: "acme-line-map", props: {...} } }.
 * Build the component in this folder, then register it here under that id.
 * Each component receives { props, widget } and must render inside its card.
 *
 * Keep client-specific components small and data-light: they read only the
 * props the operator saved in the config, or call existing /api routes the
 * signed-in member can already reach. Never add a client's data to the bundle.
 *
 * Example:
 *   import AcmeLineMap from "./clients/AcmeLineMap";
 *   export const BESPOKE_COMPONENTS = { "acme-line-map": AcmeLineMap };
 */
export const BESPOKE_COMPONENTS = {};

export function bespokeComponent(id) {
  return Object.prototype.hasOwnProperty.call(BESPOKE_COMPONENTS, id) ? BESPOKE_COMPONENTS[id] : null;
}
