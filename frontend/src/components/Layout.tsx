/**
 * Shared page chrome: nav + main content area + footer.
 *
 * The footer reminds users that pinyin / translation are provided
 * by the Pinyin Tool extension, since the app deliberately renders
 * raw Chinese without annotations (DESIGN.md Section 8).
 */

import { Outlet } from "react-router-dom";

import Nav from "./Nav";

/**
 * Wraps every page. Uses the `scenario-*` class prefix so styles
 * never collide with the Pinyin Tool extension's `hg-*` Shadow-DOM
 * classes (Section 9 implication #3).
 */
export default function Layout() {
  return (
    <div className="scenario-layout flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <Nav />
      <main className="scenario-main mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>
      <footer className="scenario-footer border-t border-slate-200 bg-white py-3 text-center text-sm text-slate-500">
        Pinyin and translations are provided by the Pinyin Tool extension.
        Select any Chinese text to see them.
      </footer>
    </div>
  );
}
