/**
 * Inline error banner. Used by pages to surface fetch failures with
 * an optional retry button. Centralised so the visual treatment is
 * consistent across the app.
 */

interface ErrorBannerProps {
  /** Human-readable message; falls back to "Something went wrong" if empty. */
  message?: string;
  /** Optional retry handler. When set, a "Retry" button is rendered. */
  onRetry?: () => void;
}

/**
 * Renders a red-tinted banner with the message and an optional retry
 * button. Pages mount this conditionally inside their layout; it is
 * intentionally not a portal so it appears in-place.
 */
export default function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className="scenario-error-banner flex items-center justify-between gap-3 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
    >
      <span>{message || "Something went wrong"}</span>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="scenario-error-retry rounded bg-red-100 px-3 py-1 text-red-900 hover:bg-red-200"
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}
