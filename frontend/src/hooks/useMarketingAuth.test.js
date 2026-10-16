import { hasSessionHint } from "./useMarketingAuth";

test("signed-in Clerk cookie counts as a session hint", () => {
  expect(hasSessionHint("a=1; __client_uat=1760600000; b=2")).toBe(true);
  expect(hasSessionHint("__client_uat_Ab12=1760600000")).toBe(true);
});

test("signed-out or missing cookie does not", () => {
  expect(hasSessionHint("__client_uat=0")).toBe(false);
  expect(hasSessionHint("__client_uat_Ab12=0; x=1")).toBe(false);
  expect(hasSessionHint("x=1")).toBe(false);
  expect(hasSessionHint("")).toBe(false);
});
