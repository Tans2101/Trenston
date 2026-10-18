import full from "./dashboard-briefing.webp";
import small from "./dashboard-briefing-800.webp";

// Responsive pair for the Briefing screenshot: phones and laptop-frame widths
// get the 800px file, only very wide or high-density screens fetch the 1600px one.
export const briefingImage = {
  src: full,
  srcSet: `${small} 800w, ${full} 1600w`,
  sizes: "(min-width: 1024px) 620px, 92vw",
};
