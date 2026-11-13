import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GuestHome } from "./guest-home";

describe("GuestHome", () => {
  it("introduces guest services and clearly identifies the disconnected preview", () => {
    render(<GuestHome />);

    expect(screen.getByRole("heading", { level: 1, name: "Guest services" })).toBeInTheDocument();
    expect(screen.getByLabelText("Preview status")).toHaveTextContent(
      "This preview is not connected to hotel systems. No guest information is loaded or saved here.",
    );
  });
});
