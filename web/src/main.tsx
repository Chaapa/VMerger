import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowUp,
  BarChart3,
  Check,
  ChevronRight,
  Film,
  FolderOpen,
  LoaderCircle,
  LogOut,
  MessageCircle,
  Moon,
  Plus,
  Sparkles,
  Sun,
  Upload,
  X,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Project, Snapshot } from "./types";
import { percentile, summarize } from "./metrics";
import "./style.css";

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-VMerger-Request": "1",
      ...options.headers,
    },
  });
  if (response.status === 401)
    window.dispatchEvent(new Event("session-expired"));
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string" ? data.detail : "Please check your input",
    );
  return data;
}
const seconds = (us: number) => {
  const n = Math.round(us / 1e6);
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
};
const labels: Record<string, string> = {
  imported: "Awaiting analysis",
  ready: "Ready",
  processing: "Analyzing",
  planning: "Planning",
  rendering: "Rendering",
  queued: "Queued",
  running: "Running",
  succeeded: "Ready",
  failed: "Failed",
  cancelled: "Cancelled",
};
const operations: Record<string, string> = {
  analyze_asset: "Analyzing video",
  apply_message: "Developing story",
  render_version: "Rendering video",
  reindex_embeddings: "Updating semantic search",
};
const aiRoles: Record<string, string> = {
  analyst: "Video analyst",
  director: "Director",
  music: "Music agent",
  editor: "Editor",
  reviewer: "Reviewer",
  embedding: "Semantic search",
};

function App() {
  const [signedIn, setSignedIn] = useState(false);
  const [checking, setChecking] = useState(true);
  const [token, setToken] = useState("");
  const [config, setConfig] = useState({
    ai_available: false,
    analysis_available: false,
    planning_available: false,
    embedding_available: false,
    analysis_mode: "",
    config_error: false,
    routes: {} as Record<
      string,
      {
        provider: string;
        model: string;
        configured: boolean;
        fallbacks?: { provider: string; model: string; configured: boolean }[];
      }
    >,
    max_upload_mb: 500,
    max_asset_seconds: 600,
  });
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [storyId, setStoryId] = useState<string | null>(null);
  const [versionId, setVersionId] = useState<string | null>(null);
  const [tab, setTab] = useState<"stories" | "metrics" | "sources">("stories");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [prompt, setPrompt] = useState("");
  const [title, setTitle] = useState("");
  const [brief, setBrief] = useState("");
  const [creating, setCreating] = useState(false);
  const [dark, setDark] = useState(localStorage.getItem("theme") === "dark");
  const uploadInput = useRef<HTMLInputElement>(null);
  const musicInput = useRef<HTMLInputElement>(null);
  const [licenseNote, setLicenseNote] = useState("");
  const [showMusic, setShowMusic] = useState(false);

  const refreshList = async () =>
    setProjects(await api<Project[]>("/projects"));
  const refresh = async (id = selected) => {
    if (id) setSnapshot(await api<Snapshot>(`/projects/${id}`));
  };
  const execute = async (label: string, action: () => Promise<void>) => {
    setError("");
    setBusy(label);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  useEffect(() => {
    const expired = () => {
      setSignedIn(false);
      setSnapshot(null);
      setProjects([]);
      setSelected(null);
    };
    window.addEventListener("session-expired", expired);
    api<typeof config>("/config")
      .then((c) => {
        setConfig(c);
        setSignedIn(true);
      })
      .catch(() => {})
      .finally(() => setChecking(false));
    return () => window.removeEventListener("session-expired", expired);
  }, []);
  useEffect(() => {
    if (signedIn) refreshList().catch((e) => setError(e.message));
  }, [signedIn]);
  useEffect(() => {
    if (!selected) return;
    let active = true;
    const load = () =>
      api<Snapshot>(`/projects/${selected}`)
        .then((data) => {
          if (active) setSnapshot(data);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    load();
    const timer = window.setInterval(load, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [selected]);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);
  const openProject = (id: string) => {
    setSelected(id);
    setSnapshot(null);
    setStoryId(null);
    setVersionId(null);
    setTab("stories");
    setError("");
  };
  const upload = async (files: FileList | File[], music = false) => {
    if (!selected) return;
    await execute("Uploading and checking files…", async () => {
      for (const file of Array.from(files)) {
        if (file.size > config.max_upload_mb * 1024 * 1024)
          throw new Error(`${file.name}: max ${config.max_upload_mb} MB`);
        await api(
          `/projects/${selected}/assets?name=${encodeURIComponent(file.name)}&license_note=${encodeURIComponent(music ? licenseNote : "")}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/octet-stream" },
            body: file,
          },
        );
      }
      await refresh();
      setShowMusic(false);
    });
  };
  const story = snapshot?.stories.find((s) => s.id === storyId);
  const versions =
    snapshot?.edit_versions.filter((v) => v.story_id === storyId) || [];
  const playingVersion = versionId || story?.current_version_id;
  const render = snapshot?.renders.find(
    (r) => r.version_id === playingVersion && r.status === "ready",
  );
  const activeJobs =
    snapshot?.jobs.filter((j) => ["running", "queued"].includes(j.status)) ||
    [];
  const messages =
    snapshot?.messages.filter((m) => m.story_id === storyId) || [];
  const send = (text: string) =>
    execute("Sending…", async () => {
      await api(`/projects/${selected}/messages`, {
        method: "POST",
        body: JSON.stringify({
          text,
          request_id: crypto.randomUUID(),
          story_id: storyId,
          context_version_id: story?.current_version_id || null,
        }),
      });
      setPrompt("");
      await refresh();
    });

  if (checking)
    return (
      <main className="login">
        <LoaderCircle className="spin" />
      </main>
    );
  if (!signedIn)
    return (
      <main className="login">
        <form
          className="login-card"
          onSubmit={(e) => {
            e.preventDefault();
            execute("Signing in…", async () => {
              await api("/session", {
                method: "POST",
                body: JSON.stringify({ token }),
              });
              setConfig(await api("/config"));
              setToken("");
              setSignedIn(true);
            });
          }}
        >
          <div className="brand">
            <span className="brand-icon">
              <Film size={22} />
            </span>{" "}
            VMerger
          </div>
          <p className="eyebrow">YOUR FOOTAGE. YOUR STORIES.</p>
          <h1>
            Every journey
            <br />
            has a story.
          </h1>
          <p className="muted">
            Sign in to your workspace to bring it together.
          </p>
          <label>
            Workspace key
            <input
              autoComplete="current-password"
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              required
            />
          </label>
          <button className="primary" disabled={!!busy}>
            Open workspace <ChevronRight size={18} />
          </button>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <small>For local setup, use APP_TOKEN from your .env file.</small>
        </form>
      </main>
    );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button
          className="brand"
          onClick={() => {
            setSelected(null);
            setSnapshot(null);
          }}
        >
          <span className="brand-icon">
            <Film size={21} />
          </span>
          VMerger<span className="beta">ALPHA</span>
        </button>
        <p className="sidebar-label">WORKSPACE</p>
        <button
          className={`nav-item ${!selected ? "active" : ""}`}
          onClick={() => {
            setSelected(null);
            setSnapshot(null);
          }}
        >
          <FolderOpen size={19} /> My projects <span>{projects.length}</span>
        </button>
        <div className="sidebar-label row">
          PROJECTS
          <button
            className="icon-button"
            aria-label="New project"
            onClick={() => setCreating(true)}
          >
            <Plus size={15} />
          </button>
        </div>
        <div className="project-links">
          {projects.map((p) => (
            <button
              key={p.id}
              className={selected === p.id ? "selected" : ""}
              onClick={() => openProject(p.id)}
            >
              <span className="project-dot" />
              {p.title}
            </button>
          ))}
        </div>
        <div className="sidebar-bottom">
          <div className="storage-note">
            <span className="online-dot" />
            <div>
              Private storage<small>Media on your server</small>
            </div>
          </div>
          <div className="row">
            <span className="avatar">Y</span>
            <span>My workspace</span>
            <button
              className="icon-button"
              aria-label="Toggle theme"
              onClick={() => setDark(!dark)}
            >
              {dark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={() =>
                execute("Signing out…", async () => {
                  await api("/session", { method: "DELETE" });
                  setSignedIn(false);
                  setSnapshot(null);
                })
              }
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <span className="breadcrumb">
            My workspace{" "}
            {selected && (
              <>
                <ChevronRight size={14} /> {snapshot?.title || "Loading…"}
              </>
            )}
          </span>
          <span className="private-label">
            <span className="online-dot" /> Private media
          </span>
        </header>
        {error && (
          <div role="alert" className="error-banner">
            {error}
            <button
              className="icon-button"
              onClick={() => setError("")}
              aria-label="Dismiss error"
            >
              <X size={16} />
            </button>
          </div>
        )}
        {busy && (
          <div className="busy-banner" role="status">
            <LoaderCircle className="spin" size={16} />
            {busy}
          </div>
        )}
        {!selected ? (
          <section className="overview">
            <div className="page-heading">
              <div>
                <p className="eyebrow">LESS EDITING. MORE MEMORIES.</p>
                <h1>Your stories</h1>
                <p className="muted">
                  Upload your footage. Tell us what matters to you.
                </p>
              </div>
              <button className="primary" onClick={() => setCreating(true)}>
                <Plus size={18} /> New project
              </button>
            </div>
            <div className="intro-card">
              <div className="intro-symbol">
                <Sparkles size={34} />
              </div>
              <div>
                <h2>Turn individual moments into a story</h2>
                <p>
                  The system finds the events, plans the story and edits your
                  film.
                  <br />
                  To make a change, just ask in chat.
                </p>
                <div className="steps">
                  <span>
                    01 <b>Add footage</b>
                  </span>
                  <i />
                  <span>
                    02 <b>Describe your idea</b>
                  </span>
                  <i />
                  <span>
                    03 <b>Watch your story</b>
                  </span>
                </div>
              </div>
            </div>
            <div className="section-heading">
              <h2>
                All projects <span className="count">{projects.length}</span>
              </h2>
              <span className="muted">Recently updated</span>
            </div>
            <div className="project-grid">
              {projects.map((p, i) => (
                <button
                  className="project-card"
                  key={p.id}
                  onClick={() => openProject(p.id)}
                >
                  <div className={`card-cover cover-${i % 3}`}>
                    <Film size={36} />
                    <span>Personal project</span>
                  </div>
                  <div className="card-body">
                    <h3>{p.title}</h3>
                    <p>{p.brief || "Your next story"}</p>
                    <footer>
                      {new Date(p.created_at).toLocaleDateString("en-US")}
                      <ChevronRight size={17} />
                    </footer>
                  </div>
                </button>
              ))}
              <button className="new-card" onClick={() => setCreating(true)}>
                <span>
                  <Plus size={24} />
                </span>
                <b>Start a new story</b>
                <small>A trip, a weekend, or everyday life</small>
              </button>
            </div>
          </section>
        ) : !snapshot ? (
          <div className="empty">
            <LoaderCircle className="spin" />
            Loading project…
          </div>
        ) : (
          <section className="workspace">
            <div className="page-heading">
              <div>
                <button
                  className="back"
                  onClick={() => {
                    setSelected(null);
                    setSnapshot(null);
                  }}
                >
                  <ArrowLeft size={14} /> All projects
                </button>
                <h1>{snapshot.title}</h1>
                <p className="muted">
                  {snapshot.brief || "It all starts with your footage."}
                </p>
              </div>
              <button
                className="primary"
                disabled={!!busy}
                onClick={() => uploadInput.current?.click()}
              >
                <Upload size={17} /> Add videos
              </button>
            </div>
            <input
              type="file"
              hidden
              multiple
              accept="video/*"
              ref={uploadInput}
              onChange={(e) => {
                if (e.target.files) upload(e.target.files);
                e.target.value = "";
              }}
            />
            {!config.ai_available && (
              <div className="notice">
                <Sparkles size={18} />
                <div>
                  <b>
                    {config.config_error
                      ? "Could not load AI configuration"
                      : config.planning_available || config.analysis_available
                        ? "Some AI roles need configuration"
                        : "AI is not connected yet"}
                  </b>
                  <span>
                    Uploads and storage are available. Analysis and rendering
                    depend on the configured roles shown in the Quality tab.
                  </span>
                </div>
              </div>
            )}
            <div className="tabs">
              <button
                className={tab === "stories" ? "chosen" : ""}
                onClick={() => setTab("stories")}
              >
                <Film size={16} />
                Stories <span>{snapshot.stories.length}</span>
              </button>
              <button
                className={tab === "sources" ? "chosen" : ""}
                onClick={() => setTab("sources")}
              >
                <FolderOpen size={16} />
                Sources <span>{snapshot.assets.length}</span>
              </button>
              <button
                className={tab === "metrics" ? "chosen" : ""}
                onClick={() => setTab("metrics")}
              >
                <BarChart3 size={16} />
                Quality and agents
              </button>
            </div>
            {activeJobs.length > 0 && (
              <div className="job-strip">
                {activeJobs.map((j) => (
                  <div key={j.id}>
                    <LoaderCircle className="spin" size={15} />
                    <span>
                      {operations[j.kind] || j.kind} · {labels[j.status]}
                    </span>
                    <button
                      onClick={() =>
                        execute("Cancelling…", async () => {
                          await api(
                            `/projects/${selected}/jobs/${j.id}/cancel`,
                            { method: "POST" },
                          );
                          await refresh();
                        })
                      }
                    >
                      Cancel
                    </button>
                  </div>
                ))}
              </div>
            )}
            {tab === "metrics" ? (
              <>
                <div className="sources">
                  <h2>AI team</h2>
                  <p className="muted">
                    Current models by role. A configured key does not confirm
                    API availability.
                  </p>
                  <div className="job-table">
                    {Object.entries(config.routes).map(([role, route]) => (
                      <div key={role}>
                        <b>{aiRoles[role] || role}</b>
                        <span>
                          {route.provider} · {route.model}
                          {route.fallbacks?.map((backup, index) => (
                            <small
                              className="muted"
                              key={`${backup.provider}/${backup.model}`}
                            >
                              <br />
                              Backup {index + 1}: {backup.provider} ·{" "}
                              {backup.model}
                              {backup.configured ? "" : " · key required"}
                            </small>
                          ))}
                        </span>
                        <span className="badge">
                          {route.configured ? "Configured" : "Key required"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
                <Metrics data={snapshot} />
              </>
            ) : tab === "sources" ? (
              <div className="sources">
                <div className="section-heading">
                  <h2>Source materials</h2>
                  <div className="row">
                    <button
                      className="secondary"
                      disabled={
                        !config.analysis_available || !!activeJobs.length
                      }
                      onClick={() =>
                        execute("Starting analysis…", async () => {
                          await api(`/projects/${selected}/analyze`, {
                            method: "POST",
                          });
                          await refresh();
                        })
                      }
                    >
                      Analyze
                    </button>
                    <button
                      className="secondary"
                      disabled={
                        !config.embedding_available ||
                        !!activeJobs.length ||
                        !!busy
                      }
                      title="Rebuild embeddings after changing the search model"
                      onClick={() =>
                        execute("Updating search…", async () => {
                          await api(
                            `/projects/${selected}/embeddings/reindex`,
                            { method: "POST" },
                          );
                          await refresh();
                        })
                      }
                    >
                      Rebuild search
                    </button>
                    <button
                      className="secondary"
                      onClick={() => setShowMusic(!showMusic)}
                    >
                      Add music
                    </button>
                  </div>
                </div>
                {config.analysis_mode === "sampled_frames" && (
                  <p className="muted">
                    Analysis uses sampled frames without speech recognition.
                    Brief events may be missed.
                  </p>
                )}
                {showMusic && (
                  <div className="music-form">
                    <label>
                      Source and usage rights
                      <input
                        value={licenseNote}
                        onChange={(e) => setLicenseNote(e.target.value)}
                        placeholder="For example: my own track, I hold all rights"
                      />
                    </label>
                    <button
                      className="primary"
                      disabled={!licenseNote.trim() || !!busy}
                      onClick={() => musicInput.current?.click()}
                    >
                      Choose audio
                    </button>
                    <input
                      hidden
                      ref={musicInput}
                      type="file"
                      accept="audio/*"
                      onChange={(e) => {
                        if (e.target.files) upload(e.target.files, true);
                        e.target.value = "";
                      }}
                    />
                  </div>
                )}
                {snapshot.assets.length ? (
                  snapshot.assets.map((a) => (
                    <div className="asset-row" key={a.id}>
                      <span className="file-icon">
                        <Film size={20} />
                      </span>
                      <div>
                        <b>{a.original_name}</b>
                        <small>
                          {a.kind === "audio" ? "Music library" : "Video"} ·{" "}
                          {seconds(a.duration_us)}
                        </small>
                      </div>
                      <span className={`badge ${a.status}`}>
                        {labels[a.status]}
                      </span>
                    </div>
                  ))
                ) : (
                  <EmptyUpload onClick={() => uploadInput.current?.click()} />
                )}
              </div>
            ) : (
              <div className="story-layout">
                <div className="story-area">
                  {story ? (
                    <>
                      <button
                        className="back"
                        onClick={() => {
                          setStoryId(null);
                          setVersionId(null);
                        }}
                      >
                        <ArrowLeft size={14} /> All stories
                      </button>
                      <h2>{story.title}</h2>
                      <div className="player">
                        {render ? (
                          <video
                            controls
                            key={render.id}
                            src={`/api/projects/${selected}/objects/${render.storage_object_id}`}
                          />
                        ) : (
                          <div className="empty">
                            <Film size={40} />
                            <p>Your video will appear after rendering</p>
                          </div>
                        )}
                      </div>
                      <div className="version-bar">
                        <label>
                          Version
                          <select
                            aria-label="Story version"
                            value={playingVersion || ""}
                            onChange={(e) => setVersionId(e.target.value)}
                          >
                            {versions.map((v) => (
                              <option value={v.id} key={v.id}>
                                {v.revision}
                                {v.id === story.current_version_id
                                  ? " · current"
                                  : ""}
                              </option>
                            ))}
                          </select>
                        </label>
                        {render && (
                          <a
                            className="secondary"
                            download
                            href={`/api/projects/${selected}/objects/${render.storage_object_id}`}
                          >
                            <ArrowDownToLine size={16} />
                            Download
                          </a>
                        )}
                      </div>
                      <p className="muted">{story.description}</p>
                      {versionId && versionId !== story.current_version_id && (
                        <p className="notice">
                          You are viewing an earlier version. New edits apply to
                          the current version.
                        </p>
                      )}
                    </>
                  ) : snapshot.stories.length ? (
                    <div className="stories-grid">
                      {snapshot.stories.map((s, i) => (
                        <button
                          className="story-card"
                          key={s.id}
                          onClick={() => {
                            setStoryId(s.id);
                            setVersionId(null);
                          }}
                        >
                          <div className={`card-cover cover-${i % 3}`}>
                            <Film size={35} />
                            <span className="badge">{labels[s.status]}</span>
                          </div>
                          <div className="card-body">
                            <h3>{s.title}</h3>
                            <p>{s.description}</p>
                            <span className="watch">
                              Open story <ChevronRight size={15} />
                            </span>
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div
                      className="start-story"
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        e.preventDefault();
                        if (!busy) upload(e.dataTransfer.files);
                      }}
                    >
                      <EmptyUpload
                        onClick={() => uploadInput.current?.click()}
                      />
                      <p className="muted">
                        {snapshot.assets.length
                          ? `${snapshot.assets.length} sources uploaded. Describe your idea in chat.`
                          : `Up to ${config.max_upload_mb} MB and ${config.max_asset_seconds / 60} minutes per video`}
                      </p>
                    </div>
                  )}
                </div>
                <aside className="chat">
                  <header>
                    <span className="agent-symbol">
                      <Sparkles size={19} />
                    </span>
                    <div>
                      <b>
                        {story ? "Developing your story" : "Project director"}
                      </b>
                      <small>
                        {config.planning_available
                          ? "Story · music · editing"
                          : "Waiting for AI connection"}
                      </small>
                    </div>
                    <MessageCircle size={17} />
                  </header>
                  <div className="chat-messages">
                    {messages.length ? (
                      messages.map((m) => (
                        <div className={`message ${m.role}`} key={m.id}>
                          <small>{m.role === "user" ? "You" : "VMerger"}</small>
                          <p>{m.text}</p>
                        </div>
                      ))
                    ) : (
                      <div className="chat-welcome">
                        <Sparkles size={28} />
                        <h3>What story shall we tell?</h3>
                        <p>
                          Describe the mood, length and moments you want to
                          keep.
                        </p>
                        <button
                          disabled={!config.planning_available}
                          onClick={() =>
                            setPrompt("Create a short, warm story of this trip")
                          }
                        >
                          A warm travel story <ArrowUp size={14} />
                        </button>
                        <button
                          disabled={!config.planning_available}
                          onClick={() =>
                            setPrompt(
                              "Split the events into several short stories",
                            )
                          }
                        >
                          Several separate stories <ArrowUp size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                  <form
                    className="composer"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (prompt.trim()) send(prompt);
                    }}
                  >
                    <textarea
                      aria-label="Video request"
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      placeholder="Describe an idea or ask for a change…"
                      disabled={!config.planning_available}
                      maxLength={4000}
                    />
                    <footer>
                      <small>
                        {activeJobs.length
                          ? "Working on your previous request"
                          : "Edit through conversation"}
                      </small>
                      <button
                        aria-label="Send"
                        className="send"
                        disabled={
                          !config.planning_available ||
                          !prompt.trim() ||
                          !!busy ||
                          !!activeJobs.length
                        }
                      >
                        <ArrowUp size={18} />
                      </button>
                    </footer>
                  </form>
                </aside>
              </div>
            )}
          </section>
        )}
      </main>
      {creating && (
        <div className="modal-backdrop">
          <form
            className="modal"
            onSubmit={(e) => {
              e.preventDefault();
              execute("Creating…", async () => {
                const p = await api<Project>("/projects", {
                  method: "POST",
                  body: JSON.stringify({ title, brief }),
                });
                await refreshList();
                setCreating(false);
                setTitle("");
                setBrief("");
                openProject(p.id);
              });
            }}
          >
            <div className="row">
              <h2>Your next story starts here</h2>
              <button
                type="button"
                className="icon-button"
                aria-label="Close"
                onClick={() => setCreating(false)}
              >
                <X size={20} />
              </button>
            </div>
            <label>
              Project title
              <input
                autoFocus
                required
                maxLength={140}
                placeholder="For example, a weekend by the sea"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <label>
              What is your footage about?
              <textarea
                maxLength={4000}
                placeholder="Optional. You can tell us later in chat."
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
              />
            </label>
            <button className="primary" disabled={!title.trim() || !!busy}>
              Create project <ChevronRight size={18} />
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

function EmptyUpload({ onClick }: { onClick: () => void }) {
  return (
    <button className="upload-zone" onClick={onClick}>
      <span className="upload-symbol">
        <Upload size={27} />
      </span>
      <h2>Add the moments of your story</h2>
      <p>Drop videos here or choose files</p>
      <span className="secondary">
        Choose videos <Plus size={16} />
      </span>
    </button>
  );
}

function Metrics({ data }: { data: Snapshot }) {
  const plan = summarize(data.eval_results, "plan_valid");
  const decode = summarize(data.eval_results, "decode_pass");
  const times = data.ai_calls
    .filter((c) => c.duration_ms !== null)
    .map((c) => c.duration_ms! / 1000);
  const failed = data.jobs.filter((j) => j.status === "failed");
  const series = data.eval_results
    .filter((r) => r.metric === "duration_error_seconds")
    .map((r, i) => ({ run: i + 1, seconds: r.value, time: r.created_at }));
  const latency = data.ai_calls
    .filter((c) => c.duration_ms !== null)
    .map((c, i) => ({
      call: i + 1,
      seconds: c.duration_ms! / 1000,
      role: c.purpose,
      status: c.status,
    }));
  return (
    <div className="metrics">
      <div className="section-heading">
        <div>
          <h2>Measured results</h2>
          <p className="muted">
            Actual observations for this project. N counts measurements, not
            independent projects.
          </p>
        </div>
        <span className="badge">{data.eval_results.length} observations</span>
      </div>
      <div className="metric-grid">
        <Metric
          name="Plan validity"
          value={
            plan.value === null ? "—" : `${(plan.value * 100).toFixed(0)}%`
          }
          note={`N=${plan.n} · rules and source bounds`}
        />
        <Metric
          name="Full decoding"
          value={
            decode.value === null ? "—" : `${(decode.value * 100).toFixed(0)}%`
          }
          note={`N=${decode.n} · output file verification`}
        />
        <Metric
          name="AI latency, p95"
          value={
            percentile(times, 0.95) === null
              ? "—"
              : `${percentile(times, 0.95)!.toFixed(1)} s`
          }
          note={`N=${times.length} · calls, including failures`}
        />
        <Metric
          name="Cost"
          value="—"
          note="Pricing unverified · not counted as zero"
        />
      </div>
      <div className="chart-grid">
        <div className="chart-card">
          <h3>Agent call latency</h3>
          <p>Seconds · per call</p>
          {latency.length ? (
            <ResponsiveContainer width="100%" height={230}>
              <LineChart data={latency}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="call" />
                <YAxis />
                <Tooltip />
                <Line
                  type="linear"
                  dataKey="seconds"
                  name="Seconds"
                  stroke="#3e8c70"
                  strokeWidth={2}
                  dot
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="chart-empty">
              No calls yet.
              <br />
              The chart appears after agents run.
            </div>
          )}
        </div>
        <div className="chart-card">
          <h3>Render duration error</h3>
          <p>|Actual − planned| · seconds</p>
          {series.length ? (
            <ResponsiveContainer width="100%" height={230}>
              <LineChart data={series}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="run" />
                <YAxis />
                <Tooltip />
                <Line
                  type="linear"
                  dataKey="seconds"
                  name="Error, s"
                  stroke="#b98a45"
                  strokeWidth={2}
                  dot
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="chart-empty">
              No renders yet.
              <br />
              FFmpeg measurements will appear here.
            </div>
          )}
        </div>
      </div>
      <div className="quality-note">
        <Check size={19} />
        <div>
          <b>Technical checks and creative quality are measured separately</b>
          <p>
            A valid plan does not establish film quality. Storytelling, music
            fit and review accuracy need labeled examples and human ratings. No
            results or confidence intervals are available yet.
          </p>
        </div>
      </div>
      <h3>Processing history</h3>
      {data.jobs.length ? (
        <div className="job-table">
          {data.jobs.map((j) => (
            <div key={j.id}>
              <b>{operations[j.kind] || j.kind}</b>
              <span>Attempt {j.attempt}</span>
              <span className={`badge ${j.status}`}>{labels[j.status]}</span>
              {j.error && <small>{j.error.type}</small>}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">Processing has not started yet.</p>
      )}
      {failed.length > 0 && (
        <p className="error">
          Failed jobs: {failed.length}. They remain in the history and are
          included in statistics.
        </p>
      )}
    </div>
  );
}
function Metric({
  name,
  value,
  note,
}: {
  name: string;
  value: string;
  note: string;
}) {
  return (
    <div className="metric-card">
      <span>{name}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
