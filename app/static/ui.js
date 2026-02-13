(() => {
  const createToastContainer = () => {
    let container = document.querySelector(".toast-container");
    if (container) return container;
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
    return container;
  };

  const showToast = (message, type = "info") => {
    if (!message) return;
    const container = createToastContainer();
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("visible"));
    setTimeout(() => {
      toast.classList.remove("visible");
      setTimeout(() => toast.remove(), 300);
    }, 2400);
  };

  window.showToast = showToast;

  const observeStatusToasts = () => {
    const statusEls = document.querySelectorAll(".status");
    if (!statusEls.length) return;
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        const el = mutation.target;
        if (!el.classList.contains("status")) return;
        const msg = el.textContent.trim();
        if (!msg) return;
        const type = el.dataset.type || "info";
        showToast(msg, type);
      });
    });
    statusEls.forEach((el) => observer.observe(el, { childList: true, characterData: true, subtree: true }));
  };

  const exportToCsv = (rows, filename) => {
    const csv = rows
      .map((row) =>
        row
          .map((cell) => {
            const value = cell == null ? "" : String(cell);
            const escaped = value.replace(/"/g, '""');
            return `"${escaped}"`;
          })
          .join(",")
      )
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const extractTableRows = () => {
    const htmlTable = document.querySelector("table.table");
    if (htmlTable) {
      const rows = [];
      const headers = Array.from(htmlTable.querySelectorAll("thead th")).map((th) =>
        th.textContent.trim()
      );
      if (headers.length) rows.push(headers);
      htmlTable.querySelectorAll("tbody tr").forEach((tr) => {
        rows.push(
          Array.from(tr.children).map((td) => td.textContent.trim())
        );
      });
      return rows;
    }

    const gridTable = document.querySelector(".table");
    if (!gridTable) return [];
    const rows = [];
    const head = gridTable.querySelector(".table-head");
    if (head) {
      rows.push(Array.from(head.children).map((span) => span.textContent.trim()));
    }
    gridTable.querySelectorAll(".table-row").forEach((row) => {
      if (row.classList.contains("table-head")) return;
      const cells = Array.from(row.children).map((cell) => cell.textContent.trim());
      rows.push(cells);
    });
    return rows;
  };

  const wireQuickActions = () => {
    document.querySelectorAll(".quick-actions").forEach((bar) => {
      bar.querySelectorAll("button[data-action]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const action = btn.dataset.action;
          if (action === "refresh") {
            window.location.reload();
            return;
          }
          if (action === "help") {
            showToast("Tip: Use Search, click any row to edit, and use Export for CSV.");
            return;
          }
          if (action === "add") {
            const form = document.querySelector(".add-form");
            if (form) {
              const submit = form.querySelector('button[type="submit"], .primary');
              if (submit) submit.click();
              return;
            }
            showToast("No add form found on this page.", "error");
            return;
          }
          if (action === "export") {
            const rows = extractTableRows();
            if (!rows.length) {
              showToast("No table data to export.", "error");
              return;
            }
            exportToCsv(rows, "export.csv");
            showToast("CSV exported.", "success");
          }
        });
      });
    });
  };

  observeStatusToasts();
  wireQuickActions();
})();
