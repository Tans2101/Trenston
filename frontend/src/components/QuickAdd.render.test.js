import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QuickAddPanel } from "@/components/QuickAdd";
import { parseCommand } from "@/lib/commandBar";

jest.mock("react-router-dom", () => ({ useNavigate: () => () => {} }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("@/lib/api", () => ({ api: {}, apiErrorMessage: () => "x" }));

const now = new Date(2026, 9, 13);
const members = [
  { user_id: "a", name: "Ann Lee", email: "ann@x.com" },
  { user_id: "b1", name: "Bob Stone", email: "b1@x.com" },
  { user_id: "b2", name: "Bob Reyes", email: "b2@x.com" },
];
const html = (text, extra = {}) => renderToStaticMarkup(
  <QuickAddPanel parsed={parseCommand(text, { now, members, myUserId: "me" })} loadingTeam={false} saving={false} onPick={() => {}} {...extra} />,
);

describe("QuickAddPanel", () => {
  it("shows what was understood and says Enter saves", () => {
    const out = html("task call the supplier friday for Ann !high");
    expect(out).toContain("New task");
    expect(out).toContain("Call the supplier");
    expect(out).toContain("Fri 16 Oct");
    expect(out).toContain("Ann Lee");
    expect(out).toContain("High");
    expect(out).toContain("Press Enter to save");
  });

  it("asks which person when the name is ambiguous and does not offer to save", () => {
    const out = html("task send contract for Bob");
    expect(out).toContain("Which");
    expect(out).toContain("Bob Stone");
    expect(out).toContain("Bob Reyes");
    expect(out).not.toContain("Press Enter to save");
  });

  it("shows problems instead of guessing", () => {
    const out = html("task call friday or monday");
    expect(out).toContain("more than one date");
    expect(out).toContain("Fix the above");
  });

  it("notes are verbatim and have no date or priority rows", () => {
    const out = html("note ask Sam friday");
    expect(out).toContain("New private note");
    expect(out).not.toContain("Due");
  });
});
