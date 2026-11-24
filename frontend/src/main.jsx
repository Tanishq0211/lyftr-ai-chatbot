import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowDownLeft, ArrowRight, ArrowUp, AudioWaveform, CircleAlert, Plus, SlidersHorizontal } from 'lucide-react';
import '@fontsource-variable/dm-sans/wght.css';
import '@fontsource/instrument-serif/400.css';
import './styles.css';

const api = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');
const prompts = ['What is the capital of France?', 'Explain how a solar eclipse works.'];

function Metadata({ metadata }) {
  return (
    <dl className="metadata" aria-label="Reply details">
      <div className={metadata.resolution_source === 'LLM_CACHE' ? 'cached' : 'live'}>
        <dt>Source</dt><dd data-testid="meta-source">{metadata.resolution_source}</dd>
      </div>
      <div><dt>Model</dt><dd data-testid="meta-model">{metadata.model}</dd></div>
      <div><dt>Latency</dt><dd data-testid="meta-latency">{metadata.latency_ms} ms</dd></div>
      <div><dt>Input tokens</dt><dd data-testid="meta-input-tokens">{metadata.input_tokens}</dd></div>
      <div><dt>Output tokens</dt><dd data-testid="meta-output-tokens">{metadata.output_tokens}</dd></div>
    </dl>
  );
}

function Welcome({ onPrompt }) {
  return (
    <section className="welcome" data-enter>
      <div className="signal" aria-hidden="true">
        <span /><span /><span />
        <AudioWaveform size={34} strokeWidth={1.45} />
      </div>
      <h1>Start a conversation.</h1>
      <p>See the model, response time, and token usage for each reply.</p>
      <div className="suggestions" aria-label="Suggested questions">
        {prompts.map((prompt) => (
          <button type="button" key={prompt} onClick={() => onPrompt(prompt)}>
            <ArrowDownLeft size={16} aria-hidden="true" />{prompt}
          </button>
        ))}
      </div>
    </section>
  );
}

function App() {
  const [session, setSession] = useState(() => crypto.randomUUID());
  const [draft, setDraft] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [entries, setEntries] = useState([]);
  const [pending, setPending] = useState(false);
  const [health, setHealth] = useState('checking');
  const input = useRef(null);
  const end = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${api}/health`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]) })
      .then((response) => setHealth(response.ok ? 'ready' : 'unavailable'))
      .catch(() => { if (!controller.signal.aborted) setHealth('unavailable'); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' });
  }, [entries, pending]);

  function newChat() {
    setSession(crypto.randomUUID());
    setEntries([]);
    setDraft('');
    setSystemPrompt('');
    input.current?.focus();
  }

  function choosePrompt(prompt) {
    setDraft(prompt);
    input.current?.focus();
  }

  async function send(event) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || pending) return;
    setEntries((previous) => [...previous, { role: 'user', content: message }]);
    setDraft('');
    setPending(true);
    try {
      const response = await fetch(`${api}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: session, message, system_prompt: systemPrompt }),
        signal: AbortSignal.timeout(120000),
      });
      if (response.status === 422) throw new Error('Enter a message between 1 and 4,000 characters and try again.');
      if (response.status === 503) throw new Error('All model providers are unavailable right now. Try sending again in a moment.');
      if (!response.ok) throw new Error('The server could not send a reply. Please try again.');
      const result = await response.json();
      setHealth('ready');
      setEntries((previous) => [...previous, { role: 'assistant', content: result.reply, metadata: result.metadata }]);
    } catch (error) {
      const content = error instanceof TypeError || error.name === 'TimeoutError'
        ? 'The chat server could not be reached. Check your connection and try again.'
        : error.message;
      setEntries((previous) => [...previous, { role: 'error', content }]);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand"><span className="brand-icon"><AudioWaveform size={22} aria-hidden="true" /></span>Relay</div>
        <p className={`connection ${health}`} role="status">
          <span />{{ checking: 'Checking API', ready: 'API ready', unavailable: 'API unavailable' }[health]}
        </p>
      </header>

      <main className="workspace">
        <aside className="sidebar" aria-label="Session controls">
          <button className="new-chat" type="button" onClick={newChat} disabled={pending}>
            <Plus size={17} aria-hidden="true" />New chat<ArrowRight size={15} className="new-arrow" aria-hidden="true" />
          </button>
          <div className="session">
            <span>Current session</span>
            <code title={session}>{session}</code>
          </div>
          <details className="settings">
            <summary><SlidersHorizontal size={16} aria-hidden="true" />System prompt</summary>
            <textarea data-testid="system-prompt-input" aria-label="System prompt" placeholder="Optional instructions for the assistant" value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} rows={4} />
          </details>
        </aside>

        <section className="chat" aria-label="Chat">
          {entries.length === 0 ? <Welcome onPrompt={choosePrompt} /> : (
            <div className="conversation" role="log" aria-label="Conversation">
              {entries.map((entry, index) => (
                <article key={index} className={`entry ${entry.role}`} data-testid={entry.role === 'assistant' ? 'assistant-message' : undefined}>
                  {entry.role === 'assistant' && <h2><AudioWaveform size={17} aria-hidden="true" />Relay</h2>}
                  {entry.role === 'error' && <CircleAlert size={18} aria-hidden="true" />}
                  <p>{entry.content}</p>
                  {entry.metadata && <Metadata metadata={entry.metadata} />}
                </article>
              ))}
              {pending && <p className="pending" role="status"><span />Waiting for a reply</p>}
              <div ref={end} />
            </div>
          )}
          <form className="composer" onSubmit={send}>
            <div className="input-frame">
              <textarea
                ref={input}
                data-testid="chat-input"
                aria-label="Message"
                placeholder="Message Relay…"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                    event.preventDefault();
                    event.currentTarget.form.requestSubmit();
                  }
                }}
                rows={2}
                maxLength={4000}
              />
              <button className="send" type="submit" data-testid="send-button" aria-label="Send message" disabled={!draft.trim() || pending}>
                <ArrowUp size={21} aria-hidden="true" />
              </button>
            </div>
            <p className="composer-hint">Enter to send <span>·</span> Shift + Enter for a new line</p>
          </form>
        </section>
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
