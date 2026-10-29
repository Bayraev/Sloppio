import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "@/components/status-badge";

describe("StatusBadge", () => {
  it("renders terminal statuses with the right intent colors", () => {
    render(<StatusBadge status="completed" />);
    expect(screen.getByTestId("status-completed")).toHaveTextContent("completed");
  });
  it("humanizes snake_case statuses", () => {
    render(<StatusBadge status="needs_reconciliation" />);
    expect(screen.getByTestId("status-needs_reconciliation")).toHaveTextContent("needs reconciliation");
  });
});
