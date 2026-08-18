/* Shared helpers used by every page of the Vendit Inventory app. */

const AUTH_KEY = "vendit_token";
const USER_KEY = "vendit_user";

function getToken() { return localStorage.getItem(AUTH_KEY); }
function getUser() {
  try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch { return null; }
}
function setSession(token, user) {
  localStorage.setItem(AUTH_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}
function clearSession() {
  localStorage.removeItem(AUTH_KEY);
  localStorage.removeItem(USER_KEY);
}
function isAdmin() {
  const u = getUser();
  return !!u && u.role === "admin";
}

async function api(path, options = {}) {
  const token = getToken();
  const headers = Object.assign(
    { "Content-Type": "application/json" },
    options.headers || {}
  );
  if (token) headers["Authorization"] = "Bearer " + token;

  const res = await fetch("/api" + path, Object.assign({}, options, { headers }));

  if (res.status === 401) {
    clearSession();
    window.location.href = "/login.html";
    throw new Error("Session expired");
  }

  let body = null;
  const text = await res.text();
  if (text) {
    try { body = JSON.parse(text); } catch { body = null; }
  }

  if (!res.ok) {
    const message = (body && body.error) || `Request failed (${res.status})`;
    throw new Error(message);
  }
  return body;
}

function requireAuth() {
  if (!getToken()) {
    window.location.href = "/login.html";
    return false;
  }
  return true;
}

function requireAdmin() {
  if (!requireAuth()) return false;
  if (!isAdmin()) {
    document.body.innerHTML = '<div class="empty-state" style="margin-top:60px;">You need admin access to view this page.</div>';
    return false;
  }
  return true;
}

function logout() {
  clearSession();
  window.location.href = "/login.html";
}

function money(n) {
  n = Number(n) || 0;
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function dt(s) {
  if (!s) return "";
  const d = new Date(s.replace(" ", "T") + "Z");
  if (isNaN(d.getTime())) return s;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function dateOnly(s) {
  if (!s) return "";
  return s.split("T")[0].split(" ")[0];
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const REASON_LABELS = {
  purchase: "Purchase",
  return: "Captain Return",
  issuance: "Issuance",
  consumption: "Consumption",
  damage: "Damage",
  expiry: "Expiry",
  adjustment: "Adjustment",
};

function reasonBadge(reason) {
  const cls = { purchase: "teal", return: "teal", issuance: "amber", consumption: "gray", damage: "red", expiry: "red", adjustment: "gray" }[reason] || "gray";
  return `<span class="badge ${cls}">${REASON_LABELS[reason] || reason}</span>`;
}

const NAV_ITEMS = [
  { href: "/dashboard.html", label: "Dashboard" },
  { href: "/products.html", label: "Products" },
  { href: "/captain_runs.html", label: "Captain Runs" },
  { href: "/purchase_orders.html", label: "Purchase Orders" },
  { href: "/suppliers.html", label: "Suppliers" },
  { href: "/captains.html", label: "Filling Captains" },
  { href: "/teams.html", label: "Teams" },
  { href: "/reports.html", label: "Reports" },
  { href: "/users.html", label: "Users", adminOnly: true },
];

function renderShell(activeHref) {
  const user = getUser();
  const shell = document.getElementById("app-shell");
  if (!shell) return;

  const navHtml = NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin())
    .map(
      (item) =>
        `<a href="${item.href}" class="${item.href === activeHref ? "active" : ""}">${item.label}</a>`
    )
    .join("");

  shell.innerHTML = `
    <div class="sidebar">
      <div class="brand">Vendit Technologies<span>Inventory Management</span></div>
      <nav>${navHtml}</nav>
      <div class="user-box">
        Signed in as<br><strong>${escapeHtml(user ? user.full_name : "")}</strong> (${escapeHtml(user ? user.role : "")})
        <button class="secondary small" id="logout-btn" type="button">Log out</button>
      </div>
    </div>
    <div class="main" id="main-content"></div>
  `;
  document.getElementById("logout-btn").addEventListener("click", logout);
}

function toast(msg, type = "error") {
  const el = document.getElementById("toast-area");
  if (!el) { alert(msg); return; }
  el.innerHTML = `<div class="alert ${type === "error" ? "error" : "success"}">${escapeHtml(msg)}</div>`;
  if (type !== "error") setTimeout(() => { el.innerHTML = ""; }, 3500);
}
