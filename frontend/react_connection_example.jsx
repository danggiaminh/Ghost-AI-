import { useState } from "react";

export default function GhostConnectionExample() {
  const [output, setOutput] = useState("");

  async function streamGhost(message) {
    const response = await fetch("/chat/stream", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    if (!response.ok || !response.body) {
      throw new Error("stream failed");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const eventBlock of events) {
        const lines = eventBlock.split("\n");
        let eventName = "message";
        let dataJson = "{}";

        for (const line of lines) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          if (line.startsWith("data:")) dataJson = line.slice(5).trim();
        }

        const payload = JSON.parse(dataJson);
        if (eventName === "chunk") {
          setOutput((prev) => prev + (payload.text || ""));
        }
      }
    }
  }

  return (
    <div>
      <button onClick={() => streamGhost("Analyze this stack trace")}>Stream</button>
      <pre>{output}</pre>
    </div>
  );
}
