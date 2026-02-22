(function () {
  const e = React.createElement;

  const LOGO =
    '<svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg" aria-label="Ghost logo">' +
    '<defs><filter id="g" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="1.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>' +
    '<g fill="none" stroke="#F5F5F7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" filter="url(#g)" opacity="0.92">' +
    '<path d="M64 18C44.1 18 28 34.1 28 54v22c0 10.5 8.5 19 19 19 6.4 0 12.2-3.2 15.8-8.4 0.4-0.6 1.2-0.6 1.6 0C68 91.8 73.8 95 80.2 95 90.5 95 99 86.5 99 76V54C99 34.1 83 18 64 18Z"/>' +
    '<path d="M44 78c4.2 3.8 9.3 5.7 15.2 5.7 1.7 0 3.2-1 4.1-2.4 0.2-0.4 0.8-0.4 1 0 0.8 1.4 2.4 2.4 4.1 2.4 5.9 0 11-1.9 15.2-5.7"/>' +
    '<circle cx="36" cy="49" r="3"/><circle cx="92" cy="49" r="3"/><circle cx="64" cy="12" r="3"/><circle cx="64" cy="108" r="3"/>' +
    '</g></svg>';

  async function api(path, options) {
    const response = await fetch(path, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(options && options.headers ? options.headers : {}) },
      ...options,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(body.detail || "Request failed");
    }
    return response;
  }

  async function ensureAuth(action) {
    try {
      return await action();
    } catch (error) {
      if (!/401|token|Session|session|credentials/i.test(String(error.message || ""))) {
        throw error;
      }
      await fetch("/auth/refresh", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: "{}" });
      return action();
    }
  }

  function App() {
    const [mode, setMode] = React.useState("login");
    const [email, setEmail] = React.useState("");
    const [password, setPassword] = React.useState("");
    const [user, setUser] = React.useState(null);
    const [messages, setMessages] = React.useState([
      { role: "assistant", text: "Ghost is ready. Secure session mode is available after login." },
    ]);
    const [draft, setDraft] = React.useState("");
    const [typing, setTyping] = React.useState(false);
    const [busy, setBusy] = React.useState(false);
    const [imageMeta, setImageMeta] = React.useState(null);
    const [debugMode, setDebugMode] = React.useState(false);
    const [banner, setBanner] = React.useState("");
    const [serverOffline, setServerOffline] = React.useState(false);

    const fileRef = React.useRef(null);
    const messagesRef = React.useRef(null);

    React.useEffect(() => {
      const onOffline = () => {
        setBanner("Internet disconnected");
        setServerOffline(true);
      };
      const onOnline = () => {
        setBanner("Connection restored");
        setTimeout(() => setBanner(""), 1400);
        setServerOffline(false);
      };
      window.addEventListener("offline", onOffline);
      window.addEventListener("online", onOnline);
      return () => {
        window.removeEventListener("offline", onOffline);
        window.removeEventListener("online", onOnline);
      };
    }, []);

    React.useEffect(() => {
      let timer = null;
      if (serverOffline) {
        timer = setInterval(async () => {
          try {
            const check = await fetch("/healthz", { credentials: "include" });
            if (check.ok) {
              setServerOffline(false);
              setBanner("Server reconnected");
              setTimeout(() => setBanner(""), 1400);
            }
          } catch (_err) {
            return;
          }
        }, 2500);
      }
      return () => {
        if (timer) clearInterval(timer);
      };
    }, [serverOffline]);

    React.useEffect(() => {
      (async () => {
        try {
          const response = await api("/auth/me", { method: "GET" });
          const data = await response.json();
          setUser(data.user);
        } catch (_error) {
          return;
        }
      })();
    }, []);

    React.useEffect(() => {
      if (messagesRef.current) {
        messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
      }
    }, [messages]);

    async function onAuthSubmit(event) {
      event.preventDefault();
      setBusy(true);
      try {
        const endpoint = mode === "login" ? "/auth/login" : "/auth/register";
        const response = await api(endpoint, {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        const data = await response.json();
        setUser(data.user);
        setBanner("Session active");
        setTimeout(() => setBanner(""), 1200);
      } catch (error) {
        setBanner(error.message);
      } finally {
        setBusy(false);
      }
    }

    async function onLogout() {
      try {
        await api("/auth/logout", { method: "POST", body: "{}" });
      } catch (_error) {
        return;
      } finally {
        setUser(null);
        setMessages([{ role: "assistant", text: "Session ended." }]);
      }
    }

    async function onUploadImage(event) {
      const file = event.target.files && event.target.files[0];
      if (!file || !user) return;

      const formData = new FormData();
      formData.append("file", file);

      try {
        const response = await ensureAuth(() =>
          fetch("/chat/image", {
            method: "POST",
            credentials: "include",
            body: formData,
          }).then(async (res) => {
            if (!res.ok) {
              const body = await res.json().catch(() => ({ detail: "Upload failed" }));
              throw new Error(body.detail || "Upload failed");
            }
            return res;
          })
        );
        const data = await response.json();
        setImageMeta(data);
        setMessages((prev) => prev.concat([{ role: "assistant", text: data.analysis }]));
      } catch (error) {
        setBanner(error.message || "Image upload failed");
      }
    }

    async function sendMessage(event) {
      if (event) event.preventDefault();
      if (!draft.trim() || !user) return;

      const messageText = draft.trim();
      setDraft("");
      setTyping(true);
      setMessages((prev) => prev.concat([{ role: "user", text: messageText }, { role: "assistant", text: "" }]));

      try {
        await ensureAuth(() => streamChat(messageText));
      } catch (error) {
        setServerOffline(true);
        setBanner(error.message || "Connection error");
      } finally {
        setTyping(false);
      }
    }

    async function streamChat(messageText) {
      const response = await fetch("/chat/stream", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: messageText, image_context: imageMeta }),
      });

      if (!response.ok || !response.body) {
        const body = await response.json().catch(() => ({ detail: "Streaming failed" }));
        throw new Error(body.detail || "Streaming failed");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";

        for (const chunk of chunks) {
          const lines = chunk.split("\n");
          let eventName = "message";
          let data = "{}";
          for (const line of lines) {
            if (line.startsWith("event:")) eventName = line.slice(6).trim();
            if (line.startsWith("data:")) data = line.slice(5).trim();
          }
          const payload = JSON.parse(data || "{}");

          if (eventName === "meta") {
            setDebugMode(Boolean(payload.debug_mode));
          }

          if (eventName === "chunk") {
            setMessages((prev) => {
              const clone = prev.slice();
              const idx = clone.length - 1;
              clone[idx] = { ...clone[idx], text: (clone[idx].text || "") + (payload.text || "") };
              return clone;
            });
          }

          if (eventName === "done" && payload.moderated) {
            setMessages((prev) => {
              const clone = prev.slice();
              const idx = clone.length - 1;
              clone[idx] = {
                ...clone[idx],
                text: payload.masked_text,
                rawText: payload.raw_text,
                reveal: false,
                moderated: true,
              };
              return clone;
            });
          }
        }
      }
    }

    function toggleReveal(index) {
      setMessages((prev) => {
        const clone = prev.slice();
        const item = clone[index];
        clone[index] = { ...item, reveal: !item.reveal };
        return clone;
      });
    }

    function renderAuth() {
      return e(
        "form",
        { className: "auth", onSubmit: onAuthSubmit },
        e("div", { className: "muted" }, "Secure auth required. Session timeout: 60 minutes inactive."),
        e(
          "div",
          { className: "row" },
          e("input", {
            value: email,
            onChange: (evt) => setEmail(evt.target.value),
            placeholder: "email",
            type: "email",
            autoComplete: "email",
            required: true,
          }),
          e("input", {
            value: password,
            onChange: (evt) => setPassword(evt.target.value),
            placeholder: "password",
            type: "password",
            autoComplete: mode === "login" ? "current-password" : "new-password",
            required: true,
          })
        ),
        e(
          "div",
          { className: "row" },
          e("button", { disabled: busy, type: "submit" }, mode === "login" ? "Login" : "Register"),
          e(
            "button",
            {
              className: "ghost-plain",
              type: "button",
              onClick: () => setMode(mode === "login" ? "register" : "login"),
            },
            mode === "login" ? "Need account" : "Have account"
          )
        )
      );
    }

    return e(
      "div",
      { className: "app" },
      e("div", { className: "banner" + (banner ? " show" : "") }, banner || ""),
      e(
        "div",
        { className: "topbar" },
        e(
          "div",
          { className: "brand" },
          e("span", { className: "logo", dangerouslySetInnerHTML: { __html: LOGO } }),
          e("span", null, "Ghost")
        ),
        e(
          "div",
          { className: "status muted" },
          user ? `signed in as ${user.email}` : "awaiting authentication"
        )
      ),
      e(
        "div",
        { className: "container" },
        !user ? renderAuth() : null,
        user
          ? e(
              React.Fragment,
              null,
              e(
                "div",
                { className: "messages", ref: messagesRef },
                messages.map((item, index) =>
                  e(
                    "div",
                    { className: "message " + item.role, key: `${index}-${item.role}` },
                    item.reveal ? item.rawText || item.text : item.text,
                    item.moderated
                      ? e(
                          "div",
                          { className: "reveal" },
                          e(
                            "button",
                            { className: "ghost-plain", onClick: () => toggleReveal(index) },
                            item.reveal ? "Hide" : "Reveal"
                          )
                        )
                      : null
                  )
                )
              ),
              e(
                "div",
                { className: "context" },
                imageMeta
                  ? e(
                      "div",
                      { className: "panel" },
                      e("b", null, "Image Analysis"),
                      e("div", null, `${imageMeta.filename} (${imageMeta.size_bytes} bytes)`),
                      e("div", null, imageMeta.mime)
                    )
                  : null,
                debugMode
                  ? e(
                      "div",
                      { className: "panel" },
                      e("b", null, "Technical Assistant Mode"),
                      e("div", null, "Debug context detected. Provide logs and reproduction steps.")
                    )
                  : null
              ),
              e(
                "div",
                { className: "typing" + (typing ? " show" : "") },
                e("span", { className: "dot" }),
                e("span", null, "Ghost is typing")
              ),
              e(
                "form",
                { className: "composer", onSubmit: sendMessage },
                e("input", {
                  ref: fileRef,
                  type: "file",
                  accept: "image/*",
                  onChange: onUploadImage,
                  style: { display: "none" },
                }),
                e(
                  "button",
                  {
                    type: "button",
                    className: "ghost-plain",
                    onClick: () => fileRef.current && fileRef.current.click(),
                    title: "Upload image",
                  },
                  "+"
                ),
                e("textarea", {
                  value: draft,
                  onChange: (evt) => setDraft(evt.target.value),
                  placeholder: "Message Ghost...",
                  disabled: typing || serverOffline,
                }),
                e("button", { type: "submit", disabled: typing || serverOffline }, "Send"),
                e(
                  "button",
                  { type: "button", className: "ghost-plain", onClick: onLogout },
                  "Logout"
                )
              )
            )
          : null
      )
    );
  }

  ReactDOM.createRoot(document.getElementById("root")).render(e(App));
})();
