/**
 * Generate page -- prompt form + live SSE progress + redirect on done.
 *
 * Flow:
 *   1. User fills the form and submits.
 *   2. `useGenerateScenario` POSTs and returns a `job_id`.
 *   3. We pass the id to `useJobStream`, which opens an EventSource.
 *   4. `<GenerationStatus>` renders progress as events arrive.
 *   5. On "done" we navigate to `/scenarios/{scenario_id}`.
 *   6. On "failed" we render an `<ErrorBanner>` and let the user retry.
 *
 * See DESIGN.md Section 8 (Generate page).
 */

import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import ErrorBanner from "../components/ErrorBanner";
import GenerationStatus from "../components/GenerationStatus";
import { useGenerateScenario } from "../hooks/useGenerateScenario";
import { useJobStream } from "../hooks/useJobStream";

const SCENE_HINTS = [
  { value: "", label: "Any" },
  { value: "menu", label: "Menu" },
  { value: "sign", label: "Sign" },
  { value: "notice", label: "Notice" },
  { value: "label", label: "Label" },
  { value: "instruction", label: "Instruction" },
  { value: "map", label: "Map" },
];

const FORMAT_HINTS = [
  { value: "", label: "Any" },
  { value: "handwritten", label: "Handwritten" },
  { value: "printed", label: "Printed" },
  { value: "digital", label: "Digital" },
];

export default function GeneratePage() {
  const [prompt, setPrompt] = useState("");
  const [sceneHint, setSceneHint] = useState("");
  const [region, setRegion] = useState("");
  const [formatHint, setFormatHint] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const navigate = useNavigate();
  const generate = useGenerateScenario();
  const stream = useJobStream(jobId);

  // Auto-redirect on success. Effect rather than inline so the
  // `useNavigate` call doesn't fire during render.
  useEffect(() => {
    if (stream.isDone && stream.scenarioId) {
      navigate(`/scenarios/${stream.scenarioId}`);
    }
  }, [stream.isDone, stream.scenarioId, navigate]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setValidationError(null);
    if (!prompt.trim()) {
      setValidationError("Please enter a prompt to generate a scenario.");
      return;
    }
    try {
      const response = await generate.mutateAsync({
        prompt: prompt.trim(),
        scene_hint: sceneHint || undefined,
        region: region.trim() || undefined,
        format_hint: formatHint || undefined,
      });
      setJobId(response.job_id);
    } catch {
      // mutation.error is rendered below; nothing else to do here.
    }
  };

  const handleReset = () => {
    setJobId(null);
    setValidationError(null);
    generate.reset();
  };

  // Show form whenever no job is in flight; otherwise show the
  // progress + (on failure) a "Try again" affordance.
  const inFlight = jobId !== null && !stream.isDone && !stream.error;

  return (
    <section className="scenario-generate-page max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold text-slate-900">
        Generate a scenario
      </h1>

      {!inFlight ? (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label
              htmlFor="prompt"
              className="block text-sm font-medium text-slate-700"
            >
              What do you want to read?
            </label>
            <textarea
              id="prompt"
              name="prompt"
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="ordering breakfast at a Beijing 早餐店"
              // No `required` attribute -- we validate in JS so the
              // empty-prompt test path can observe the inline error
              // banner instead of the browser's native tooltip.
              className="scenario-generate-prompt w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="block text-sm">
              <span className="block font-medium text-slate-700">Scene type</span>
              <select
                name="scene_hint"
                value={sceneHint}
                onChange={(e) => setSceneHint(e.target.value)}
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
              >
                {SCENE_HINTS.map((h) => (
                  <option key={h.label} value={h.value}>
                    {h.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm">
              <span className="block font-medium text-slate-700">Region</span>
              <input
                type="text"
                name="region"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                placeholder="Beijing"
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
              />
            </label>

            <label className="block text-sm">
              <span className="block font-medium text-slate-700">Format</span>
              <select
                name="format_hint"
                value={formatHint}
                onChange={(e) => setFormatHint(e.target.value)}
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
              >
                {FORMAT_HINTS.map((h) => (
                  <option key={h.label} value={h.value}>
                    {h.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {validationError ? (
            <ErrorBanner message={validationError} />
          ) : null}

          {generate.error ? (
            <ErrorBanner message={generate.error.message} />
          ) : null}

          {stream.error ? (
            <div className="space-y-3">
              <ErrorBanner message={stream.error} />
              <button
                type="button"
                onClick={handleReset}
                className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm hover:border-slate-400"
              >
                Try again
              </button>
            </div>
          ) : null}

          <button
            type="submit"
            disabled={generate.isPending}
            className="scenario-generate-submit rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {generate.isPending ? "Starting..." : "Generate"}
          </button>
        </form>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            Generating your scenario. This usually takes 30-90 seconds.
          </p>
          <GenerationStatus currentStage={stream.stage} isDone={stream.isDone} />
        </div>
      )}
    </section>
  );
}
