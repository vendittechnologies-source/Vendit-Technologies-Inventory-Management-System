/* Shared logic between the Issuance and Returns pages -- both are views
   onto the same captain_runs data, split for a clearer daily workflow:
   Issuance = morning stock-out to filling captains, Returns = evening
   stock-in + closing the run. Consumption/write-off logging lives here
   too since both pages offer it as a quick action. */

let products = [], captains = [], teams = [];

async function initRunsData() {
  try {
    [products, captains, teams] = await Promise.all([
      api("/products"), api("/captains"), api("/teams"),
    ]);
  } catch (err) { toast(err.message); }
}

function productOptions() {
  return products.map((p) => `<option value="${p.id}">${escapeHtml(p.name)} (${escapeHtml(p.sku)}) — ${p.quantity_on_hand} on hand</option>`).join("");
}

function lineItemRow(idx) {
  return `
    <div class="field-row line-item-row" data-idx="${idx}" style="align-items:flex-end;">
      <div class="field" style="flex:2;"><label>${idx === 0 ? 'Product' : ''}</label><select class="li-product">${productOptions()}</select></div>
      <div class="field" style="flex:1;"><label>${idx === 0 ? 'Qty' : ''}</label><input class="li-qty" type="number" min="1" value="1"></div>
      <div class="field" style="flex:0 0 auto;"><button type="button" class="secondary small remove-row">✕</button></div>
    </div>
  `;
}

function attachRemoveHandlers(scope) {
  scope.querySelectorAll(".remove-row").forEach((btn) => {
    btn.onclick = () => {
      const rows = scope.querySelectorAll(".line-item-row");
      if (rows.length > 1) btn.closest(".line-item-row").remove();
    };
  });
}

/* Barcode scan box: a USB/Bluetooth scanner just types the barcode
   (like a fast keyboard) followed by Enter, into whatever input has
   focus. This wires a dedicated box to look the product up and select
   it in the given line-item row automatically. */
function attachBarcodeScanning(scope) {
  const box = scope.querySelector(".barcode-scan-box");
  if (!box) return;
  box.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const code = box.value.trim();
    box.value = "";
    if (!code) return;
    try {
      const product = await api(`/products/barcode/${encodeURIComponent(code)}`);
      const rows = scope.querySelectorAll(".line-item-row");
      let targetRow = [...rows].find((r) => !r.dataset.filled);
      if (!targetRow) {
        const wrap = document.createElement("div");
        wrap.innerHTML = lineItemRow(rows.length);
        targetRow = wrap.firstElementChild;
        scope.querySelector("#line-items").appendChild(targetRow);
        attachRemoveHandlers(scope);
      }
      targetRow.querySelector(".li-product").value = String(product.id);
      targetRow.dataset.filled = "1";
      targetRow.querySelector(".li-qty").focus();
      targetRow.querySelector(".li-qty").select();
      box.focus();
    } catch (err) {
      toast(`No product found for barcode "${code}".`);
      box.focus();
    }
  });
}

function openNewRunModal(onDone) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>New Issuance</h2>
      <div id="modal-toast"></div>
      <form id="form">
        <div class="field">
          <label>Filling Captain</label>
          <select name="captain_id" required>${captains.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join("")}</select>
        </div>
        <div class="field"><label>Run Date</label><input name="run_date" type="date" value="${new Date().toISOString().slice(0,10)}"></div>
        <div class="field">
          <label>Scan Barcode <span class="muted">(adds/selects a product below)</span></label>
          <input class="barcode-scan-box" type="text" placeholder="Click here, then scan..." autocomplete="off">
        </div>
        <h2 style="margin-top:6px;">Products Issued</h2>
        <div id="line-items">${lineItemRow(0)}</div>
        <button type="button" class="secondary small" id="add-row">+ Add Product</button>
        <div class="field mt"><label>Notes</label><input name="notes"></div>
        <div class="modal-actions">
          <button type="button" class="secondary" id="cancel-btn">Cancel</button>
          <button type="submit">Issue Stock</button>
        </div>
      </form>
    </div>
  `;
  document.body.appendChild(backdrop);
  let rowCount = 1;
  backdrop.querySelector("#add-row").addEventListener("click", () => {
    const wrap = document.createElement("div");
    wrap.innerHTML = lineItemRow(rowCount++);
    backdrop.querySelector("#line-items").appendChild(wrap.firstElementChild);
    attachRemoveHandlers(backdrop);
  });
  attachRemoveHandlers(backdrop);
  attachBarcodeScanning(backdrop);
  backdrop.querySelector("#cancel-btn").addEventListener("click", () => backdrop.remove());
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) backdrop.remove(); });

  backdrop.querySelector("#form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const items = [...backdrop.querySelectorAll(".line-item-row")].map((row) => ({
      product_id: parseInt(row.querySelector(".li-product").value, 10),
      quantity_issued: parseInt(row.querySelector(".li-qty").value, 10),
    }));
    const payload = { captain_id: parseInt(fd.get("captain_id"), 10), run_date: fd.get("run_date"), notes: fd.get("notes"), items };
    try {
      await api("/captain-runs", { method: "POST", body: JSON.stringify(payload) });
      backdrop.remove();
      toast("Stock issued to captain.", "success");
      if (onDone) onDone();
    } catch (err) {
      backdrop.querySelector("#modal-toast").innerHTML = `<div class="alert error">${escapeHtml(err.message)}</div>`;
    }
  });
}

async function viewRun(id) {
  try {
    const r = await api(`/captain-runs/${id}`);
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal">
        <h2>Run #${r.id} — ${escapeHtml(r.captain_name)}</h2>
        <p class="muted">${r.run_date} · ${r.status === 'open' ? 'Open' : 'Closed'}${r.notes ? ' · ' + escapeHtml(r.notes) : ''}</p>
        <table>
          <thead><tr><th>Product</th><th class="num">Issued</th><th class="num">Returned</th><th class="num">Filled</th></tr></thead>
          <tbody>
            ${r.items.map((i) => `<tr><td>${escapeHtml(i.product_name)}</td><td class="num">${i.quantity_issued}</td><td class="num">${i.quantity_returned ?? '—'}</td><td class="num">${i.quantity_filled ?? '—'}</td></tr>`).join("")}
          </tbody>
        </table>
        <div class="modal-actions"><button class="secondary" id="close-view">Close</button></div>
      </div>
    `;
    document.body.appendChild(backdrop);
    backdrop.querySelector("#close-view").addEventListener("click", () => backdrop.remove());
    backdrop.addEventListener("click", (e) => { if (e.target === backdrop) backdrop.remove(); });
  } catch (err) { toast(err.message); }
}

async function openCloseModal(id, onDone) {
  const r = await api(`/captain-runs/${id}`);
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>Record Return — ${escapeHtml(r.captain_name)}</h2>
      <p class="muted">Enter how much of each product ${escapeHtml(r.captain_name)} brought back unsold. The rest is counted as filled.</p>
      <div id="modal-toast"></div>
      <form id="form">
        <table>
          <thead><tr><th>Product</th><th class="num">Issued</th><th class="num">Returned</th></tr></thead>
          <tbody>
            ${r.items.map((i) => `
              <tr>
                <td>${escapeHtml(i.product_name)}</td>
                <td class="num">${i.quantity_issued}</td>
                <td class="num"><input class="ret-qty" data-product="${i.product_id}" type="number" min="0" max="${i.quantity_issued}" value="0" style="width:90px;"></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
        <div class="field mt"><label>Notes</label><input name="notes"></div>
        <div class="modal-actions">
          <button type="button" class="secondary" id="cancel-btn">Cancel</button>
          <button type="submit">Record Returns & Close</button>
        </div>
      </form>
    </div>
  `;
  document.body.appendChild(backdrop);
  backdrop.querySelector("#cancel-btn").addEventListener("click", () => backdrop.remove());
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) backdrop.remove(); });
  backdrop.querySelector("#form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const items = [...backdrop.querySelectorAll(".ret-qty")].map((inp) => ({
      product_id: parseInt(inp.dataset.product, 10),
      quantity_returned: parseInt(inp.value || "0", 10),
    }));
    const notes = new FormData(e.target).get("notes");
    try {
      await api(`/captain-runs/${id}/close`, { method: "POST", body: JSON.stringify({ items, notes }) });
      backdrop.remove();
      toast("Run closed and returns recorded.", "success");
      if (onDone) onDone();
    } catch (err) {
      backdrop.querySelector("#modal-toast").innerHTML = `<div class="alert error">${escapeHtml(err.message)}</div>`;
    }
  });
}

function openConsumptionModal(onDone) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>Log Team Consumption</h2>
      <div id="modal-toast"></div>
      <form id="form">
        <div class="field"><label>Product</label><select name="product_id" required>${productOptions()}</select></div>
        <div class="field">
          <label>Team <span class="muted">(optional)</span></label>
          <select name="team_id"><option value="">— general / unspecified —</option>${teams.map((t) => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join("")}</select>
          <a href="/teams.html" target="_blank" class="muted" style="font-size:12px;">Manage teams</a>
        </div>
        <div class="field"><label>Quantity</label><input name="quantity" type="number" min="1" value="1" required></div>
        <div class="field"><label>Notes</label><input name="notes"></div>
        <div class="modal-actions">
          <button type="button" class="secondary" id="cancel-btn">Cancel</button>
          <button type="submit">Log Consumption</button>
        </div>
      </form>
    </div>
  `;
  document.body.appendChild(backdrop);
  backdrop.querySelector("#cancel-btn").addEventListener("click", () => backdrop.remove());
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) backdrop.remove(); });
  backdrop.querySelector("#form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const payload = { product_id: parseInt(fd.get("product_id"), 10), team_id: fd.get("team_id") ? parseInt(fd.get("team_id"), 10) : null, quantity: parseInt(fd.get("quantity"), 10), notes: fd.get("notes") };
    try {
      await api("/stock/consumption", { method: "POST", body: JSON.stringify(payload) });
      backdrop.remove();
      toast("Consumption logged.", "success");
      if (onDone) onDone();
    } catch (err) {
      backdrop.querySelector("#modal-toast").innerHTML = `<div class="alert error">${escapeHtml(err.message)}</div>`;
    }
  });
}

function openWriteoffModal(onDone) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>Log Damage / Expiry</h2>
      <div id="modal-toast"></div>
      <form id="form">
        <div class="field"><label>Product</label><select name="product_id" required>${productOptions()}</select></div>
        <div class="field"><label>Reason</label><select name="reason"><option value="damage">Damage</option><option value="expiry">Expiry</option></select></div>
        <div class="field"><label>Quantity</label><input name="quantity" type="number" min="1" value="1" required></div>
        <div class="field"><label>Attributed to Captain (optional)</label><select name="captain_id"><option value="">— none —</option>${captains.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join("")}</select></div>
        <div class="field"><label>Notes</label><input name="notes"></div>
        <div class="modal-actions">
          <button type="button" class="secondary" id="cancel-btn">Cancel</button>
          <button type="submit">Log Write-off</button>
        </div>
      </form>
    </div>
  `;
  document.body.appendChild(backdrop);
  backdrop.querySelector("#cancel-btn").addEventListener("click", () => backdrop.remove());
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) backdrop.remove(); });
  backdrop.querySelector("#form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const payload = {
      product_id: parseInt(fd.get("product_id"), 10),
      reason: fd.get("reason"),
      quantity: parseInt(fd.get("quantity"), 10),
      captain_id: fd.get("captain_id") ? parseInt(fd.get("captain_id"), 10) : null,
      notes: fd.get("notes"),
    };
    try {
      await api("/stock/writeoff", { method: "POST", body: JSON.stringify(payload) });
      backdrop.remove();
      toast("Write-off logged.", "success");
      if (onDone) onDone();
    } catch (err) {
      backdrop.querySelector("#modal-toast").innerHTML = `<div class="alert error">${escapeHtml(err.message)}</div>`;
    }
  });
}
