const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const messagesElement = document.querySelector("#messages");
const statusElement = document.querySelector("#status");
const sendButton = document.querySelector("#send-button");
const clearButton = document.querySelector("#clear-button");

const conversation = [];
const configuredUrl = window.APP_CONFIG?.apiBaseUrl ?? "";
const apiBaseUrl = configuredUrl.replace(/\/+$/, "");

function appendMessage(role, content) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

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

  const response = await fetch(`${apiBaseUrl}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: conversation }),
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
  appendMessage("assistant", "Hello! How can I help you today?");
  statusElement.textContent = "";
  input.focus();
});

