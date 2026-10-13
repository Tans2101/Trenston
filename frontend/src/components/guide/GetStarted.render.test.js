import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/lib/api", () => ({ api: { post: jest.fn() } }));
jest.mock("@/hooks/useFetch", () => ({ useFetch: () => ({}) }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("react-router-dom", () => ({ useNavigate: () => () => {}, useLocation: () => ({ pathname: "/app" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: null, setUser: () => {} }) }));

// eslint-disable-next-line import/first
import { GetStartedView } from "@/components/guide/GetStarted";

const checklist = {
  steps: [
    { id: "tour", label: "Take the 1-minute tour", done: true, hint: "h0", route: "/app", tour: "briefing" },
    { id: "financials", label: "Add your cash", done: false, hint: "Runway starts working from this.", route: "/app/financials", tour: "financials" },
    { id: "decision", label: "Log one decision", done: false, hint: "Anything you need to decide.", route: "/app/decisions", tour: "decisions" },
  ],
};

describe("GetStartedView", () => {
  const html = renderToStaticMarkup(<GetStartedView checklist={checklist} onShow={() => {}} onHide={() => {}} busy={false} />);

  it("shows progress and a Show me button for each open step", () => {
    expect(html).toContain("1 of 3 done");
    expect(html).toContain("width:33%");
    expect(html).toContain("setup-show-financials");
    expect(html).toContain("setup-show-decision");
    expect(html).not.toContain("setup-show-tour");
  });

  it("explains each open step, and not the finished ones", () => {
    expect(html).toContain("Runway starts working from this.");
    expect(html).not.toContain(">h0<");
  });
});
