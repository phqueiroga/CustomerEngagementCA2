const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const messagesElement = document.querySelector("#messages");
const statusElement = document.querySelector("#status");
const sendButton = document.querySelector("#send-button");
const clearButton = document.querySelector("#clear-button");

const conversation = [];
const configuredUrl = window.APP_CONFIG?.apiBaseUrl ?? "";
const apiBaseUrl = configuredUrl.replace(/\/+$/, "");
const welcomeMessage =
  "Welcome to Emerald Pantry. I can help with general shopping questions, " +
  "food ideas, and customer support. What can I help you with today?";

// Task 1 establishes the business context while keeping live catalogue claims
// out of scope until the Google Sheet is connected in Task 2.
const businessContext = [
  {
    role: "user",
    content:
      "Act as the customer-support assistant for Emerald Pantry, an Irish " +
      "online grocery and specialty-food business. Be warm, concise, and " +
      "helpful. You may answer general shopping, food, and support questions " +
      "using your language ability. The live product catalogue is not connected " +
      "yet, so never invent or confirm current prices, stock, barcodes, special " +
      "offers, delivery availability, or product-specific facts. Explain that " +
      "live catalogue details are not available and invite the customer to ask " +
      "a general question instead. For unrelated or absurd questions, respond " +
      "naturally and briefly, then gently offer relevant Emerald Pantry help. " +
      "Do not claim to be human.",
  },
  {
    role: "assistant",
    content:
      "Understood. I will support Emerald Pantry customers without inventing " +
      "live catalogue information.",
  },
];

function appendMessage(role, content) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = "EP";
    article.append(avatar);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content;

  article.append(bubble);
  messagesElement.append(article);
  messagesElement.scrollTop = messagesElement.scrollHeight;
}

function setBusy(busy) {
  input.disabled = busy;
  sendButton.disabled = busy;
  clearButton.disabled = busy;
  statusElement.textContent = busy ? "The assistant is thinking…" : "";
}

function isConfigured() {
  return (
    apiBaseUrl.startsWith("https://") &&
    !apiBaseUrl.includes("YOUR_VERCEL_PROJECT")
  );
}

async function sendMessage(content) {
  if (!isConfigured()) {
    throw new Error(
      "The backend URL has not been configured yet. Update frontend/config.js."
    );
  }

  const response = await fetch(`${apiBaseUrl}/api`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: [...businessContext, ...conversation] }),
  });

  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("The server returned an invalid response.");
  }

  if (!response.ok) {
    throw new Error(payload.error || "The request failed. Please try again.");
  }

  return payload.reply;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = input.value.trim();
  if (!content) return;

  conversation.push({ role: "user", content });
  appendMessage("user", content);
  input.value = "";
  setBusy(true);

  try {
    const reply = await sendMessage(content);
    conversation.push({ role: "assistant", content: reply });
    appendMessage("assistant", reply);
  } catch (error) {
    statusElement.textContent =
      error instanceof Error ? error.message : "Something went wrong.";
  } finally {
    input.disabled = false;
    sendButton.disabled = false;
    clearButton.disabled = false;
    if (statusElement.textContent === "The assistant is thinking…") {
      statusElement.textContent = "";
    }
    input.focus();
  }
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

clearButton.addEventListener("click", () => {
  conversation.length = 0;
  messagesElement.replaceChildren();
  appendMessage("assistant", welcomeMessage);
  statusElement.textContent = "";
  input.focus();
});
