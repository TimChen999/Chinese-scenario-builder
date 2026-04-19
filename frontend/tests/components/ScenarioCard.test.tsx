/**
 * Unit tests for `<ScenarioCard>`.
 *
 * Pure component, no data fetching -- so we render directly inside a
 * MemoryRouter without a QueryClient.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import ScenarioCard from "../../src/components/ScenarioCard";
import type { ScenarioSummary } from "../../src/api/schemas";

const baseScenario: ScenarioSummary = {
  id: "abc123",
  request_prompt: "ordering breakfast in Beijing",
  scene_type: "menu",
  scene_setup: "你刚走进早餐店。",
  source_image_url: "/api/scenarios/abc123/image",
  source_url: null,
  created_at: new Date().toISOString(),
  task_count: 3,
};

function renderCard(scenario = baseScenario) {
  return render(
    <MemoryRouter>
      <ScenarioCard scenario={scenario} />
    </MemoryRouter>,
  );
}

describe("ScenarioCard", () => {
  it("renders_required_fields", () => {
    renderCard();
    expect(screen.getByText(baseScenario.request_prompt)).toBeInTheDocument();
    expect(screen.getByText("menu")).toBeInTheDocument();
    expect(screen.getByText(/3 tasks/i)).toBeInTheDocument();
  });

  it("link_to_scenario", () => {
    renderCard();
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/scenarios/abc123");
  });

  it("handles_missing_image", () => {
    renderCard({ ...baseScenario, source_image_url: null });
    expect(screen.getByText(/no image/i)).toBeInTheDocument();
    // No <img> rendered when source_image_url is null.
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
