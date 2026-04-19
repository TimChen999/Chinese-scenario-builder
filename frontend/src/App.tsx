/**
 * Top-level router. Owns the route -> page component map.
 *
 * Tests render this component directly inside a MemoryRouter; the
 * production entrypoint (main.tsx) wraps it in a BrowserRouter.
 *
 * See DESIGN.md Section 8 for the route table.
 */

import { Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import GeneratePage from "./pages/GeneratePage";
import HistoryPage from "./pages/HistoryPage";
import LibraryPage from "./pages/LibraryPage";
import ScenarioPage from "./pages/ScenarioPage";

/**
 * Renders the entire route tree. Pages are wrapped in a shared
 * <Layout> (nav + main + footer); the catch-all renders a
 * NotFoundPage instead of redirecting -- see DESIGN.md Step 8 test
 * `App.test.tsx::404_route`.
 */
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<LibraryPage />} />
        <Route path="/generate" element={<GeneratePage />} />
        <Route path="/scenarios/:id" element={<ScenarioPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

/**
 * Inline 404 page. Lives next to <App> because it is wired to the
 * catch-all route and has nothing else to do; promoting to its own
 * file would just add navigation churn for future readers.
 */
function NotFoundPage() {
  return (
    <div className="scenario-not-found py-16 text-center">
      <h1 className="text-2xl font-semibold text-slate-700">Not found</h1>
      <p className="mt-2 text-slate-500">This page doesn't exist.</p>
    </div>
  );
}
