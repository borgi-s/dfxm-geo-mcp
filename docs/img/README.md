# docs/img

This directory holds images referenced by the top-level README.

## money_shot.png (MANUAL STEP — not yet captured)

`money_shot.png` must be a screenshot of Claude Desktop calling the `run_forward("")`
tool and rendering the resulting DFXM image inline in the conversation.

**How to capture it (Task 9, Step 5):**

1. Start the server: `uvx dfxm-geo-mcp` (or via the Claude Desktop JSON config).
2. In Claude Desktop, send a plain-English request such as:
   "Run a forward simulation with the default config and show me the image."
3. Claude will call `run_forward("")`, the server returns a base64-encoded PNG,
   and Claude Desktop renders it inline.
4. Take a screenshot of the Claude Desktop window showing the rendered DFXM image.
5. Save it here as `docs/img/money_shot.png`.

Until this file exists the image link in README.md will be a broken link — that is
expected and acceptable while the server is pre-published.
