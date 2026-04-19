/**
 * Node-mode MSW server for Vitest.
 *
 * Imported by `tests/setup.ts`; tests can `import { server }` and
 * call `server.use(...)` to override handlers per case.
 */

import { setupServer } from "msw/node";

import { handlers } from "./handlers";

export const server = setupServer(...handlers);
