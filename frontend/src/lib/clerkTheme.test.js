import { clerkAppearance } from "@/lib/clerkTheme";

// Clerk's "Last used" badge hangs partly above the first social button. Any container
// around that button that clips (overflow hidden) cuts the badge in half, so every
// element between the page and the button must stay overflow-visible.
describe("Clerk sign-in does not clip the Last used badge", () => {
  const chain = ["rootBox", "cardBox", "card", "scrollBox", "main", "socialButtons", "socialButtonsBlockButton"];

  test.each(chain)("%s is overflow-visible, with priority over Clerk's own styles", (key) => {
    expect(clerkAppearance.elements[key]).toMatch(/(^|\s)!overflow-visible(\s|$)/);
  });

  test("the styling still matches the black sign-in button", () => {
    expect(clerkAppearance.elements.socialButtonsBlockButton).toContain("bg-mk-black");
  });
});
