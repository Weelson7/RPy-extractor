// ViWo additions to the v1 UI (kept out of app.js, which may only shrink).
// Re-extraction policy "ask every time" (contract doc 4.3): when /api/extract
// answers needsDecision, ask the user and resend with onExisting.
(function () {
  const originalFetch = window.fetch.bind(window);

  function chooseOnExisting() {
    const replace = window.confirm(
      "This workspace already holds an extraction.\n\n" +
        "OK: replace it (trash, history and run records are kept).\n" +
        "Cancel: more options."
    );
    if (replace) return "replace";
    const fresh = window.confirm(
      "Create a new workspace folder next to it instead?\n\n" +
        "OK: new workspace.\nCancel: abort this extraction."
    );
    return fresh ? "new" : "cancel";
  }

  window.fetch = async function (input, init) {
    const response = await originalFetch(input, init);
    const url = typeof input === "string" ? input : input.url;
    if (!url.startsWith("/api/extract") || !init || !init.body) return response;
    const data = await response.clone().json().catch(() => null);
    if (!data || !data.needsDecision) return response;
    const body = JSON.parse(init.body);
    body.onExisting = chooseOnExisting();
    return originalFetch(input, { ...init, body: JSON.stringify(body) });
  };
})();
