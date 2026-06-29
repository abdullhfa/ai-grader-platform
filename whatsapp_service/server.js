const { Client, LocalAuth } = require("whatsapp-web.js");
const express = require("express");
const qrcode = require("qrcode");

const app = express();
app.use(express.json());

const PORT = process.env.WA_PORT || 3001;
const EXPECTED_PHONE = (process.env.EXPECTED_PHONE || "962786060100").replace(/\D/g, "");

// ─── State ───
let qrDataUrl = null;
let clientReady = false;
let clientInfo = null;
let lastError = null;
let phoneMatch = null;

// ─── WhatsApp Client ───
const client = new Client({
  authStrategy: new LocalAuth({ dataPath: "./wa_session" }),
  puppeteer: {
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
    ],
  },
});

client.on("qr", async (qr) => {
  console.log("📱 QR Code received — scan with WhatsApp");
  try {
    qrDataUrl = await qrcode.toDataURL(qr, { width: 300, margin: 2 });
  } catch (e) {
    console.error("QR generation error:", e);
  }
  clientReady = false;
  clientInfo = null;
});

client.on("ready", () => {
  console.log("✅ WhatsApp client is ready!");
  clientReady = true;
  qrDataUrl = null;
  lastError = null;
  try {
    const connectedPhone = client.info.wid.user;
    phoneMatch = connectedPhone === EXPECTED_PHONE;
    clientInfo = {
      name: client.info.pushname,
      phone: connectedPhone,
      platform: client.info.platform,
      expectedPhone: EXPECTED_PHONE,
    };
    console.log(`   Connected as: ${clientInfo.name} (${clientInfo.phone})`);
    if (!phoneMatch) {
      console.warn(
        `⚠️ Phone mismatch: connected ${connectedPhone}, expected ${EXPECTED_PHONE}`
      );
    }
  } catch (e) {
    clientInfo = {};
    phoneMatch = null;
  }
});

client.on("authenticated", () => {
  console.log("🔐 WhatsApp authenticated");
  qrDataUrl = null;
});

client.on("auth_failure", (msg) => {
  console.error("❌ WhatsApp auth failure:", msg);
  lastError = `auth_failure: ${msg}`;
  clientReady = false;
});

client.on("disconnected", (reason) => {
  console.log("🔌 WhatsApp disconnected:", reason);
  clientReady = false;
  clientInfo = null;
  phoneMatch = null;
  lastError = `disconnected: ${reason}`;
  // Reinitialize after disconnect
  setTimeout(() => {
    console.log("🔄 Reinitializing client...");
    client.initialize().catch((e) => console.error("Reinit error:", e));
  }, 5000);
});

// ─── API Routes ───

// Health check
app.get("/health", (req, res) => {
  res.json({ status: "ok", ready: clientReady });
});

// Get status
app.get("/status", (req, res) => {
  res.json({
    ready: clientReady,
    hasQR: !!qrDataUrl,
    info: clientInfo,
    error: lastError,
    expectedPhone: EXPECTED_PHONE,
    phoneMatch: phoneMatch,
  });
});

// Get QR code (as data URL)
app.get("/qr", (req, res) => {
  if (clientReady) {
    return res.json({ status: "connected", message: "Already connected" });
  }
  if (!qrDataUrl) {
    return res.json({
      status: "waiting",
      message: "Waiting for QR code generation...",
    });
  }
  res.json({ status: "qr", qr: qrDataUrl });
});

// Send message
app.post("/send", async (req, res) => {
  if (!clientReady) {
    return res.status(503).json({
      success: false,
      error: "WhatsApp not connected",
    });
  }

  const { phone, message } = req.body;
  if (!phone || !message) {
    return res.status(400).json({
      success: false,
      error: "phone and message are required",
    });
  }

  // Normalize phone: ensure it ends with @c.us
  let chatId = phone.replace(/\D/g, "");
  if (chatId.startsWith("00")) chatId = chatId.substring(2);
  if (chatId.startsWith("0") && chatId.length === 10) {
    chatId = "962" + chatId.substring(1);
  }
  if (chatId.startsWith("7") && chatId.length === 9) {
    chatId = "962" + chatId;
  }
  chatId = chatId + "@c.us";

  const maxRetries = 3;
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const result = await client.sendMessage(chatId, message);
      console.log(`📤 Message sent to ${chatId}`);
      return res.json({
        success: true,
        messageId: result.id._serialized,
        to: chatId,
      });
    } catch (e) {
      const isTransient =
        e.message.includes("getChat") ||
        e.message.includes("getContact") ||
        e.message.includes("Cannot read properties of undefined");

      const isFatal =
        e.message.includes("detached") ||
        e.message.includes("Session closed") ||
        e.message.includes("Target closed");

      if (isFatal) {
        console.error(`❌ Fatal send error to ${chatId}:`, e.message);
        console.log("🔄 Detached frame detected — reinitializing client...");
        clientReady = false;
        clientInfo = null;
        lastError = `send_error: ${e.message}`;
        client.initialize().catch((err) =>
          console.error("Reinit error:", err)
        );
        return res.status(500).json({ success: false, error: e.message });
      }

      if (isTransient && attempt < maxRetries) {
        const delay = attempt * 2000;
        console.log(
          `⚠️ Transient error on attempt ${attempt}/${maxRetries} to ${chatId}: ${e.message} — retrying in ${delay}ms...`
        );
        await new Promise((r) => setTimeout(r, delay));
        continue;
      }

      console.error(`❌ Send error to ${chatId} (attempt ${attempt}/${maxRetries}):`, e.message);
      return res.status(500).json({ success: false, error: e.message });
    }
  }
});

// Logout (disconnect WhatsApp)
app.post("/logout", async (req, res) => {
  try {
    await client.logout();
    clientReady = false;
    clientInfo = null;
    qrDataUrl = null;
    res.json({ success: true, message: "Logged out" });
  } catch (e) {
    res.status(500).json({ success: false, error: e.message });
  }
});

// ─── Start ───
app.listen(PORT, () => {
  console.log(`🚀 WhatsApp service running on port ${PORT}`);
  console.log("⏳ Initializing WhatsApp client...");
  client.initialize().catch((e) => {
    console.error("❌ Client init error:", e);
    lastError = `init_error: ${e.message}`;
  });
});
