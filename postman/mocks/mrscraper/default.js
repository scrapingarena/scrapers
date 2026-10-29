// Synthetic fixtures from the supplied 20 October 2026 REST reference.
// Local only: this mock never contacts target pages.
const http = require("http");
const KEY = "synthetic-mrscraper-key";
http.createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  const send = (status, body, headers = {}) => {
    res.writeHead(status, { "Content-Type": "application/json", ...headers });
    res.end(JSON.stringify(body));
  };
  if (req.headers.authorization !== `Bearer ${KEY}` ||
      req.headers["x-api-token"] !== KEY) {
    return send(401, { message: "Unauthorized access", errors: "Unauthorized" });
  }
  const body = req.body || {};
  if (req.method === "GET" && url.pathname === "/api/v1/subscription-accounts") {
    return send(200, { message: "Successful operation!", data: {
      tokenLimit: 1000, tokenUsage: 25, stripeStatus: "active",
      endsAt: "2026-12-01T00:00:00.000Z", rateLimit: null, rateTtl: null,
      isEnterprise: false, isAutoRenew: false, billingId: "private-fixture",
      user: { name: "Example User", email: "user@example.com", isVerified: true }
    }});
  }
  if (req.method === "POST" && url.pathname === "/") {
    if (url.searchParams.get("token") !== KEY ||
        body.maxRetries !== 0 || !/^https?:/.test(body.url || "")) {
      return send(400, { message: "Invalid fetch contract" });
    }
    if (url.searchParams.get("screenshot") === "true" &&
        url.searchParams.get("browserRendering") !== "true") {
      return send(400, { message: "Screenshots require browser rendering" });
    }
    const requested = (field, value) =>
      url.searchParams.get(field) === "true" ? value : "";
    return send(200, {
      html: requested("html", "<html><body>Example listings</body></html>"),
      markdown: requested("markdown", "# Example listings"),
      screenshot: requested("screenshot", "/9j/synthetic-jpeg-fixture"),
      runtime: 0.01, token_usage: 2, retry_count: 0, error: null
    }, { "X-Status-Code": "200" });
  }
  if (req.method === "POST" && url.pathname === "/api/google/serp/v2/sync") {
    if (!body.query || body.format !== "json" || body.page < 1 ||
        typeof body.renderJs !== "boolean") {
      return send(400, { success: false, message: "Invalid search contract" });
    }
    return send(200, { success: true, message: "Successfully scraped", data: {
      organic: [{ title: "Example", link: "https://example.com/list",
                  description: "Example listings", rank: 1 }],
      people_also_ask: [{ question: "What is web scraping?" }],
      pagination: { current_page: body.page }
    }, tokenUsage: 1 });
  }
  send(501, { message: "Endpoint not modeled" });
}).listen(process.env.PORT || 4500);
