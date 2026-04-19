/**
 * Top navigation bar.
 *
 * Links use React Router's <NavLink> so the active route gets a
 * distinguishing class without us tracking location manually.
 */

import { NavLink } from "react-router-dom";

const linkClass = ({ isActive }: { isActive: boolean }): string =>
  [
    "scenario-nav-link rounded px-3 py-1 text-sm transition-colors",
    isActive
      ? "bg-slate-900 text-white"
      : "text-slate-600 hover:bg-slate-200 hover:text-slate-900",
  ].join(" ");

/** App-wide top nav. Renders three links: Library, Generate, History. */
export default function Nav() {
  return (
    <nav className="scenario-nav border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <div className="scenario-nav-brand text-lg font-semibold text-slate-900">
          Scenarios App
        </div>
        <ul className="scenario-nav-links flex items-center gap-2">
          <li>
            <NavLink to="/" end className={linkClass}>
              Library
            </NavLink>
          </li>
          <li>
            <NavLink to="/generate" className={linkClass}>
              Generate
            </NavLink>
          </li>
          <li>
            <NavLink to="/history" className={linkClass}>
              History
            </NavLink>
          </li>
        </ul>
      </div>
    </nav>
  );
}
