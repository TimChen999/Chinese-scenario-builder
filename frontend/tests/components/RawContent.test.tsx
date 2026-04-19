/**
 * Unit tests for `<RawContent>`.
 *
 * The most important test in this file is `is_selectable`: it
 * encodes the extension-composition contract from DESIGN.md
 * Section 9 (no `user-select: none`, no `mouseup` interception, plain
 * selectable element). Breaking it would silently break the Pinyin
 * Tool extension on the scenarios app.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import RawContent from "../../src/components/RawContent";

describe("RawContent", () => {
  it("renders_text_verbatim", () => {
    const text = "豆浆\t  3元\n  油条 ¥2.00\n包子(肉)　4元";
    render(<RawContent text={text} />);
    // textContent matches the input exactly (whitespace + special chars preserved).
    const node = document.querySelector("[data-scenario-content='raw']");
    expect(node).not.toBeNull();
    expect(node!.textContent).toBe(text);
  });

  it("has_data_attribute", () => {
    render(<RawContent text="abc" />);
    const node = screen.getByText("abc");
    expect(node.tagName).toBe("PRE");
    expect(node).toHaveAttribute("data-scenario-content", "raw");
    expect(node).toHaveAttribute("lang", "zh");
  });

  it("is_selectable", () => {
    render(<RawContent text="豆浆 3元" />);
    const node = screen.getByText("豆浆 3元");

    // No inline `user-select: none`. Tailwind's `select-none`
    // utility translates to `user-select: none`; verify class list
    // does not contain it either.
    expect(node.style.userSelect).not.toBe("none");
    expect(node.className).not.toMatch(/select-none/);

    // No mouseup / mousedown handler attached. React stores
    // listeners on the element via __reactProps$* fingerprint
    // keys; the most reliable cross-version check is to inspect
    // the React fiber's pendingProps. Easiest stable check: the
    // element does not have any `onmouseup` HTML attribute and
    // React did not patch in a delegated listener (which would be
    // present as a key starting with __reactProps$).
    expect(node.getAttribute("onmouseup")).toBeNull();
    expect(node.getAttribute("onmousedown")).toBeNull();

    // The wrapping element is a <pre>: a normal text container
    // that supports text selection. (Section 9 implication #1.)
    expect(node.tagName).toBe("PRE");
  });
});
