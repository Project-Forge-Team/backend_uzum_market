const BACKEND = (
  process.env.BACKEND_URL ?? "https://backend-uzum-market.onrender.com"
)
  .replace(/\/+$/, "")
  .replace(/\/api$/, "");
const API = `${BACKEND}/api`;

async function main() {
  console.log(`🔗 Backend: ${BACKEND}\n`);

  // 1. Get CSRF
  console.log("📋 Step 1: Getting CSRF token...");
  const csrfRes = await fetch(`${API}/auth/csrf/`, { credentials: "include" });
  const csrfCookies = csrfRes.headers.getSetCookie?.() ?? [];
  let csrfToken = "";
  let allCookies = [];
  for (const c of csrfCookies) {
    allCookies.push(c.split(";")[0]);
    if (c.startsWith("uzum_csrf=")) {
      csrfToken = c.split(";")[0].split("=")[1];
    }
  }
  console.log(`  CSRF: ${csrfToken ? "✓" : "✗"}`);

  // 2. Login
  console.log("\n📋 Step 2: Logging in...");
  const res = await fetch(`${API}/auth/login/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
      Cookie: allCookies.join("; "),
    },
    body: JSON.stringify({ email: "seller@uzum.uz", password: "Password123" }),
  });
  if (!res.ok) {
    const text = await res.text();
    console.error(`  ✗ Login failed: ${res.status} ${text}`);
    process.exit(1);
  }
  const loginCookies = res.headers.getSetCookie?.() ?? [];
  for (const c of loginCookies) {
    allCookies.push(c.split(";")[0]);
    if (c.startsWith("uzum_csrf=")) {
      csrfToken = c.split(";")[0].split("=")[1];
    }
  }
  const user = await res.json();
  console.log(`  ✓ Logged in as ${user.first_name} (seller_id=${user.seller_id})`);

  // 3. Reset demo data
  console.log("\n📋 Step 3: Resetting demo data via /api/demo/reset/...");
  const resetRes = await fetch(`${API}/demo/reset/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
      Cookie: allCookies.join("; "),
    },
  });
  const resetText = await resetRes.text();
  console.log(`  Status: ${resetRes.status}`);
  console.log(`  Response: ${resetText}`);

  if (resetRes.ok || resetRes.status === 200) {
    console.log("\n✅ Demo data reset successful!");
    console.log("   Products are now populated via Django seed command.\n");
  } else if (resetRes.status === 403) {
    console.log("\n⚠ Demo reset is locked on this server.");
    console.log("   You need to deploy with UZUM_LOCK_DEMO=False or use the admin panel.\n");
  } else {
    console.error("\n✗ Demo reset failed:", resetText);
    process.exit(1);
  }
}

main().catch((e) => {
  console.error("Fatal error:", e);
  process.exit(1);
});
