import { useMemo, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8080";

async function api(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.error) {
    throw new Error(body.message || "Request failed");
  }
  return body;
}

function parseSSEChunk(chunk) {
  const lines = chunk.split("\n");
  let eventName = "message";
  let dataJson = "{}";
  for (const line of lines) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    if (line.startsWith("data:")) dataJson = line.slice(5).trim();
  }
  return { eventName, payload: JSON.parse(dataJson || "{}") };
}

export default function App() {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [user, setUser] = useState(null);
  const [message, setMessage] = useState("");
  const [imageMeta, setImageMeta] = useState(null);
  const [typing, setTyping] = useState(false);
  const [banner, setBanner] = useState("");
  const [messages, setMessages] = useState([{ role: "assistant", text: "Ghost is ready." }]);

  const canSend = useMemo(() => Boolean(user && message.trim()), [user, message]);

  const onAuthSubmit = async (event) => {
    event.preventDefault();
    try {
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const payload = await api(path, {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setUser(payload.user);
      setBanner("Session active");
    } catch (error) {
      setBanner(error.message);
    }
  };

  const onLogout = async () => {
    try {
      await api("/auth/logout", { method: "POST", body: "{}" });
    } catch (_error) {
      return;
    }
    setUser(null);
    setMessages([{ role: "assistant", text: "Session ended." }]);
  };

  const onImageUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API_URL}/chat/image`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      const body = await response.json();
      if (!response.ok || body.error) throw new Error(body.message || "Upload failed");
      setImageMeta(body);
      setBanner("Image ready for analysis");
    } catch (error) {
      setBanner(error.message);
    }
  };

  const onSend = async (event) => {
    event.preventDefault();
    if (!canSend) return;

    const current = message.trim();
    setMessage("");
    setTyping(true);
    setMessages((prev) => [...prev, { role: "user", text: current }, { role: "assistant", text: "" }]);

    try {
      const response = await fetch(`${API_URL}/chat/stream`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: current, image_context: imageMeta }),
      });

      if (!response.ok || !response.body) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.message || "Chat failed");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const block of events) {
          const { eventName, payload } = parseSSEChunk(block);
          if (eventName === "chunk") {
            setMessages((prev) => {
              const next = [...prev];
              const idx = next.length - 1;
              next[idx] = { ...next[idx], text: (next[idx].text || "") + (payload.text || "") };
              return next;
            });
          }
          if (eventName === "done" && payload.moderated) {
            setMessages((prev) => {
              const next = [...prev];
              const idx = next.length - 1;
              next[idx] = {
                ...next[idx],
                text: payload.masked_text,
                rawText: payload.raw_text,
                moderated: true,
                reveal: false,
              };
              return next;
            });
          }
        }
      }
    } catch (error) {
      setBanner(error.message);
      setMessages((prev) => [...prev, { role: "assistant", text: "Connection issue. Please retry." }]);
    } finally {
      setTyping(false);
    }
  };

  const toggleReveal = (index) => {
    setMessages((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], reveal: !next[index].reveal };
      return next;
    });
  };

  return (
    <main className="app">
      <header className="topbar">
        <h1>Ghost</h1>
        <div className="banner">{banner}</div>
      </header>

      {!user ? (
        <form className="panel" onSubmit={onAuthSubmit}>
          <h2>{mode === "login" ? "Login" : "Register"}</h2>
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" type="email" required />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            type="password"
            required
          />
          <button type="submit" className="primary">{mode === "login" ? "Login" : "Register"}</button>
          <button type="button" className="ghost" onClick={() => setMode(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "Need account" : "Have account"}
          </button>
        </form>
      ) : (
        <section>
          <div className="toolbar">
            <label className="ghost upload">
              + Image
              <input type="file" accept="image/*" onChange={onImageUpload} />
            </label>
            <button className="ghost" onClick={onLogout}>Logout</button>
          </div>

          <div className="messages">
            {messages.map((item, index) => (
              <article key={`${item.role}-${index}`} className={`message ${item.role}`}>
                {item.reveal ? item.rawText || item.text : item.text}
                {item.moderated && (
                  <button className="ghost reveal" onClick={() => toggleReveal(index)}>
                    {item.reveal ? "Hide" : "Reveal"}
                  </button>
                )}
              </article>
            ))}
          </div>

          <form className="composer" onSubmit={onSend}>
            <textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Message Ghost..." />
            <button className="primary" disabled={!canSend || typing} type="submit">{typing ? "..." : "Send"}</button>
          </form>
        </section>
      )}
    </main>
  );
}
