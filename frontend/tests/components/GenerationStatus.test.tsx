/**
 * Unit tests for `<GenerationStatus>`.
 *
 * Covers the named test cases from DESIGN.md Step 10:
 *   - all stages render with the correct status
 *   - the current stage carries an animation class
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import GenerationStatus from "../../src/components/GenerationStatus";

describe("GenerationStatus", () => {
  it("renders_all_stages", () => {
    render(<GenerationStatus currentStage="ocr_in_progress" isDone={false} />);

    // All six stage labels visible.
    expect(screen.getByText("Generated search queries")).toBeInTheDocument();
    expect(screen.getByText("Found candidate images")).toBeInTheDocument();
    expect(screen.getByText("Downloaded images")).toBeInTheDocument();
    expect(screen.getByText("Filtered for quality")).toBeInTheDocument();
    expect(screen.getByText("Reading text from images")).toBeInTheDocument();
    expect(screen.getByText("Assembling scenario")).toBeInTheDocument();

    // Stages before the current one are completed; current is current; after is pending.
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveAttribute("data-stage-state", "completed");
    expect(items[1]).toHaveAttribute("data-stage-state", "completed");
    expect(items[2]).toHaveAttribute("data-stage-state", "completed");
    expect(items[3]).toHaveAttribute("data-stage-state", "completed");
    expect(items[4]).toHaveAttribute("data-stage-state", "current");
    expect(items[5]).toHaveAttribute("data-stage-state", "pending");
  });

  it("current_stage_animated", () => {
    render(<GenerationStatus currentStage="ocr_in_progress" isDone={false} />);
    const currentItem = screen
      .getByText("Reading text from images")
      .closest("li");
    expect(currentItem).toHaveClass("animate-pulse");
  });
});
