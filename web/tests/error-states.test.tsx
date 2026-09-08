import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const listQuizzes = vi.fn();
const getSession = vi.fn();

vi.mock("@/lib/api/client", () => ({
  listQuizzes: (...a: unknown[]) => listQuizzes(...a),
}));
vi.mock("@/lib/supabase/server", () => ({
  createClient: () => Promise.resolve({ auth: { getSession } }),
}));

import AppError from "@/app/(app)/error";
import QuizzesPage from "@/app/(app)/quizzes/page";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("route error boundary (B8)", () => {
  it("renders a recover-able state and 'Try again' calls reset", () => {
    const reset = vi.fn();
    render(<AppError error={new Error("boom")} reset={reset} />);

    expect(screen.getByTestId("route-error")).toBeTruthy();
    screen.getByRole("button", { name: "Try again" }).click();
    expect(reset).toHaveBeenCalledOnce();
  });
});

describe("server-component data failure (B8)", () => {
  it("QuizzesPage keeps its shell and shows an inline error when the fetch throws", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "t" } } });
    listQuizzes.mockRejectedValue(new Error("backend 500"));

    render(await QuizzesPage());

    expect(screen.getByRole("heading", { name: "Quizzes" })).toBeTruthy();
    expect(screen.getByTestId("load-error")).toBeTruthy();
    // The "New quiz" action stays available.
    expect(screen.getByRole("link", { name: "New quiz" })).toBeTruthy();
  });

  it("QuizzesPage renders the list normally when the fetch succeeds", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "t" } } });
    listQuizzes.mockResolvedValue([{ id: "q1", title: "Midterm", created_at: "2026-09-01T00:00:00Z" }]);

    render(await QuizzesPage());

    expect(screen.getByText("Midterm")).toBeTruthy();
    expect(screen.queryByTestId("load-error")).toBeNull();
  });
});
