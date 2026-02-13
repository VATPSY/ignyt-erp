(async function () {
  const body = document.body;
  const moduleKey = body?.dataset?.moduleKey;
  if (!moduleKey) return;

  const response = await fetch("/api/me");
  if (!response.ok) {
    window.location.href = "/login";
    return;
  }
  const me = await response.json();
  const permissions = me.permissions || [];

  let mode = "none";
  if (permissions.includes("*")) {
    mode = "write";
  } else if (permissions.includes(`${moduleKey}:write`)) {
    mode = "write";
  } else if (permissions.includes(`${moduleKey}:read`)) {
    mode = "read";
  }

  if (mode === "none") {
    window.location.href = "/";
    return;
  }

  if (mode === "read") {
    body.classList.add("read-only");
    const elements = body.querySelectorAll("button, input, select, textarea");
    elements.forEach((el) => {
      if (el.dataset.readonlyAllow === "true") return;
      if (el.type === "search") return;
      if (el.tagName === "INPUT" && el.readOnly) return;
      if (el.tagName === "INPUT" && el.type === "hidden") return;
      if (el.tagName === "BUTTON") {
        el.disabled = true;
        el.classList.add("disabled");
      } else {
        el.disabled = true;
      }
    });
  }
})();
