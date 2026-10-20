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
      typeof data.detail === "string"
        ? data.detail
        : "Проверьте введённые данные",
    );
  return data;
}
const seconds = (us: number) => {
  const n = Math.round(us / 1e6);
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
};
const labels: Record<string, string> = {
  imported: "Ждёт анализа",
  ready: "Готово",
  processing: "Анализ",
  planning: "Сценарий",
  rendering: "Сборка",
  queued: "В очереди",
  running: "В работе",
  succeeded: "Готово",
  failed: "Ошибка",
  cancelled: "Отменено",
};
const operations: Record<string, string> = {
  analyze_asset: "Анализ видео",
  apply_message: "Работа над историей",
  render_version: "Сборка видео",
};

function App() {
  const [signedIn, setSignedIn] = useState(false);
  const [checking, setChecking] = useState(true);
  const [token, setToken] = useState("");
  const [config, setConfig] = useState({
    ai_available: false,
    max_upload_mb: 500,
    max_asset_seconds: 600,
    model: "",
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
    await execute("Загружаю и проверяю файлы…", async () => {
      for (const file of Array.from(files)) {
        if (file.size > config.max_upload_mb * 1024 * 1024)
          throw new Error(`${file.name}: максимум ${config.max_upload_mb} МБ`);
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
    execute("Отправляю…", async () => {
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
            execute("Вхожу…", async () => {
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
          <p className="eyebrow">ВАШИ ВИДЕО. ВАШИ ИСТОРИИ.</p>
          <h1>
            У каждого путешествия
            <br />
            есть своя история.
          </h1>
          <p className="muted">
            Войдите в своё пространство, чтобы собрать её.
          </p>
          <label>
            Ключ пространства
            <input
              autoComplete="current-password"
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              required
            />
          </label>
          <button className="primary" disabled={!!busy}>
            Открыть пространство <ChevronRight size={18} />
          </button>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <small>
            Для локального запуска ключ находится в APP_TOKEN файла .env.
          </small>
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
        <p className="sidebar-label">ПРОСТРАНСТВО</p>
        <button
          className={`nav-item ${!selected ? "active" : ""}`}
          onClick={() => {
            setSelected(null);
            setSnapshot(null);
          }}
        >
          <FolderOpen size={19} /> Мои проекты <span>{projects.length}</span>
        </button>
        <div className="sidebar-label row">
          ПРОЕКТЫ
          <button
            className="icon-button"
            aria-label="Новый проект"
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
              Личное хранилище<small>Медиа на вашем сервере</small>
            </div>
          </div>
          <div className="row">
            <span className="avatar">Y</span>
            <span>Моё пространство</span>
            <button
              className="icon-button"
              aria-label="Сменить тему"
              onClick={() => setDark(!dark)}
            >
              {dark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <button
              className="icon-button"
              aria-label="Выйти"
              onClick={() =>
                execute("Выхожу…", async () => {
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
            Моё пространство{" "}
            {selected && (
              <>
                <ChevronRight size={14} /> {snapshot?.title || "Загрузка…"}
              </>
            )}
          </span>
          <span className="private-label">
            <span className="online-dot" /> Приватное медиа
          </span>
        </header>
        {error && (
          <div role="alert" className="error-banner">
            {error}
            <button
              className="icon-button"
              onClick={() => setError("")}
              aria-label="Закрыть ошибку"
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
                <p className="eyebrow">МЕНЬШЕ МОНТАЖА. БОЛЬШЕ ВОСПОМИНАНИЙ.</p>
                <h1>Ваши истории</h1>
                <p className="muted">
                  Загрузите видео. Расскажите, что хотите сохранить.
                </p>
              </div>
              <button className="primary" onClick={() => setCreating(true)}>
                <Plus size={18} /> Новый проект
              </button>
            </div>
            <div className="intro-card">
              <div className="intro-symbol">
                <Sparkles size={34} />
              </div>
              <div>
                <h2>Из отдельных моментов — в цельную историю</h2>
                <p>
                  Система разберётся в событиях, предложит сценарий и соберёт
                  видео.
                  <br />
                  Чтобы что-то изменить, просто напишите в чат.
                </p>
                <div className="steps">
                  <span>
                    01 <b>Добавьте видео</b>
                  </span>
                  <i />
                  <span>
                    02 <b>Опишите идею</b>
                  </span>
                  <i />
                  <span>
                    03 <b>Смотрите историю</b>
                  </span>
                </div>
              </div>
            </div>
            <div className="section-heading">
              <h2>
                Все проекты <span className="count">{projects.length}</span>
              </h2>
              <span className="muted">Последние изменения</span>
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
                    <span>Личный проект</span>
                  </div>
                  <div className="card-body">
                    <h3>{p.title}</h3>
                    <p>{p.brief || "Ваша следующая история"}</p>
                    <footer>
                      {new Date(p.created_at).toLocaleDateString("ru-RU")}
                      <ChevronRight size={17} />
                    </footer>
                  </div>
                </button>
              ))}
              <button className="new-card" onClick={() => setCreating(true)}>
                <span>
                  <Plus size={24} />
                </span>
                <b>Начните новую историю</b>
                <small>Поездка, выходные или просто жизнь</small>
              </button>
            </div>
          </section>
        ) : !snapshot ? (
          <div className="empty">
            <LoaderCircle className="spin" />
            Загружаю проект…
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
                  <ArrowLeft size={14} /> Все проекты
                </button>
                <h1>{snapshot.title}</h1>
                <p className="muted">
                  {snapshot.brief || "Всё начинается с ваших видео."}
                </p>
              </div>
              <button
                className="primary"
                disabled={!!busy}
                onClick={() => uploadInput.current?.click()}
              >
                <Upload size={17} /> Добавить видео
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
                  <b>AI пока не подключён</b>
                  <span>
                    Загрузка и хранение работают. Анализ и сборка из чата станут
                    доступны после настройки Gemini.
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
                Истории <span>{snapshot.stories.length}</span>
              </button>
              <button
                className={tab === "sources" ? "chosen" : ""}
                onClick={() => setTab("sources")}
              >
                <FolderOpen size={16} />
                Материалы <span>{snapshot.assets.length}</span>
              </button>
              <button
                className={tab === "metrics" ? "chosen" : ""}
                onClick={() => setTab("metrics")}
              >
                <BarChart3 size={16} />
                Качество и работа агентов
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
                        execute("Отменяю…", async () => {
                          await api(
                            `/projects/${selected}/jobs/${j.id}/cancel`,
                            { method: "POST" },
                          );
                          await refresh();
                        })
                      }
                    >
                      Отменить
                    </button>
                  </div>
                ))}
              </div>
            )}
            {tab === "metrics" ? (
              <Metrics data={snapshot} />
            ) : tab === "sources" ? (
              <div className="sources">
                <div className="section-heading">
                  <h2>Исходные материалы</h2>
                  <div className="row">
                    <button
                      className="secondary"
                      disabled={!config.ai_available || !!activeJobs.length}
                      onClick={() =>
                        execute("Запускаю анализ…", async () => {
                          await api(`/projects/${selected}/analyze`, {
                            method: "POST",
                          });
                          await refresh();
                        })
                      }
                    >
                      Проанализировать
                    </button>
                    <button
                      className="secondary"
                      onClick={() => setShowMusic(!showMusic)}
                    >
                      Добавить музыку
                    </button>
                  </div>
                </div>
                {showMusic && (
                  <div className="music-form">
                    <label>
                      Источник и право использования
                      <input
                        value={licenseNote}
                        onChange={(e) => setLicenseNote(e.target.value)}
                        placeholder="Например: мой трек, все права принадлежат мне"
                      />
                    </label>
                    <button
                      className="primary"
                      disabled={!licenseNote.trim() || !!busy}
                      onClick={() => musicInput.current?.click()}
                    >
                      Выбрать аудио
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
                          {a.kind === "audio"
                            ? "Музыкальная библиотека"
                            : "Видео"}{" "}
                          · {seconds(a.duration_us)}
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
                        <ArrowLeft size={14} /> Все истории
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
                            <p>Видео появится после сборки</p>
                          </div>
                        )}
                      </div>
                      <div className="version-bar">
                        <label>
                          Версия
                          <select
                            aria-label="Версия истории"
                            value={playingVersion || ""}
                            onChange={(e) => setVersionId(e.target.value)}
                          >
                            {versions.map((v) => (
                              <option value={v.id} key={v.id}>
                                {v.revision}
                                {v.id === story.current_version_id
                                  ? " · текущая"
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
                            Скачать
                          </a>
                        )}
                      </div>
                      <p className="muted">{story.description}</p>
                      {versionId && versionId !== story.current_version_id && (
                        <p className="notice">
                          Вы смотрите предыдущую версию. Новые правки
                          применяются к текущей.
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
                              Открыть историю <ChevronRight size={15} />
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
                          ? `${snapshot.assets.length} материалов загружено. Напишите идею в чат.`
                          : `До ${config.max_upload_mb} МБ и ${config.max_asset_seconds / 60} минут на видео`}
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
                        {story ? "Работаем над историей" : "Режиссёр проекта"}
                      </b>
                      <small>
                        {config.ai_available
                          ? "Сценарий · музыка · монтаж"
                          : "Ожидает подключения AI"}
                      </small>
                    </div>
                    <MessageCircle size={17} />
                  </header>
                  <div className="chat-messages">
                    {messages.length ? (
                      messages.map((m) => (
                        <div className={`message ${m.role}`} key={m.id}>
                          <small>{m.role === "user" ? "Вы" : "VMerger"}</small>
                          <p>{m.text}</p>
                        </div>
                      ))
                    ) : (
                      <div className="chat-welcome">
                        <Sparkles size={28} />
                        <h3>Какую историю расскажем?</h3>
                        <p>
                          Можно описать настроение, длительность и то, что
                          особенно хочется сохранить.
                        </p>
                        <button
                          disabled={!config.ai_available}
                          onClick={() =>
                            setPrompt(
                              "Собери короткую историю поездки с тёплым настроением",
                            )
                          }
                        >
                          Тёплая история поездки <ArrowUp size={14} />
                        </button>
                        <button
                          disabled={!config.ai_available}
                          onClick={() =>
                            setPrompt(
                              "Раздели события на несколько коротких историй",
                            )
                          }
                        >
                          Несколько отдельных историй <ArrowUp size={14} />
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
                      aria-label="Пожелание к видео"
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      placeholder="Опишите идею или попросите изменить видео…"
                      disabled={!config.ai_available}
                      maxLength={4000}
                    />
                    <footer>
                      <small>
                        {activeJobs.length
                          ? "Обрабатываем предыдущий запрос"
                          : "Монтаж — через разговор"}
                      </small>
                      <button
                        aria-label="Отправить"
                        className="send"
                        disabled={
                          !config.ai_available ||
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
              execute("Создаю…", async () => {
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
              <h2>Новая история начинается здесь</h2>
              <button
                type="button"
                className="icon-button"
                aria-label="Закрыть"
                onClick={() => setCreating(false)}
              >
                <X size={20} />
              </button>
            </div>
            <label>
              Название проекта
              <input
                autoFocus
                required
                maxLength={140}
                placeholder="Например, выходные у моря"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <label>
              О чём ваши видео?
              <textarea
                maxLength={4000}
                placeholder="Необязательно. Можно рассказать позже в чате."
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
              />
            </label>
            <button className="primary" disabled={!title.trim() || !!busy}>
              Создать проект <ChevronRight size={18} />
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
      <h2>Добавьте моменты вашей истории</h2>
      <p>Перетащите видео сюда или выберите файлы</p>
      <span className="secondary">
        Выбрать видео <Plus size={16} />
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
          <h2>Проверяем результат, а не обещания</h2>
          <p className="muted">
            Фактические наблюдения этого проекта. N — число измерений, не
            независимых проектов.
          </p>
        </div>
        <span className="badge">{data.eval_results.length} наблюдений</span>
      </div>
      <div className="metric-grid">
        <Metric
          name="Валидность планов"
          value={
            plan.value === null ? "—" : `${(plan.value * 100).toFixed(0)}%`
          }
          note={`N=${plan.n} · правила и границы исходников`}
        />
        <Metric
          name="Полное декодирование"
          value={
            decode.value === null ? "—" : `${(decode.value * 100).toFixed(0)}%`
          }
          note={`N=${decode.n} · проверка готового файла`}
        />
        <Metric
          name="Задержка AI, p95"
          value={
            percentile(times, 0.95) === null
              ? "—"
              : `${percentile(times, 0.95)!.toFixed(1)} с`
          }
          note={`N=${times.length} · вызовы, включая ошибки`}
        />
        <Metric
          name="Стоимость"
          value="—"
          note="Нет проверенного прайсинга · не считается нулём"
        />
      </div>
      <div className="chart-grid">
        <div className="chart-card">
          <h3>Время вызова агента</h3>
          <p>Секунды · каждый вызов</p>
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
                  name="Секунды"
                  stroke="#3e8c70"
                  strokeWidth={2}
                  dot
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="chart-empty">
              Вызовов ещё не было.
              <br />
              График появится после работы агентов.
            </div>
          )}
        </div>
        <div className="chart-card">
          <h3>Отклонение длительности рендера</h3>
          <p>|Фактическая − плановая| · секунды</p>
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
                  name="Отклонение, с"
                  stroke="#b98a45"
                  strokeWidth={2}
                  dot
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="chart-empty">
              Рендеров ещё не было.
              <br />
              Здесь будут измерения FFmpeg.
            </div>
          )}
        </div>
      </div>
      <div className="quality-note">
        <Check size={19} />
        <div>
          <b>
            Автоматические проверки и творческое качество — отдельные оценки
          </b>
          <p>
            Валидный план не доказывает, что фильм хороший. Сюжет, уместность
            музыки и точность ревью требуют размеченных примеров и человеческих
            оценок. Для них пока нет результатов и доверительных интервалов.
          </p>
        </div>
      </div>
      <h3>История обработки</h3>
      {data.jobs.length ? (
        <div className="job-table">
          {data.jobs.map((j) => (
            <div key={j.id}>
              <b>{operations[j.kind] || j.kind}</b>
              <span>Попытка {j.attempt}</span>
              <span className={`badge ${j.status}`}>{labels[j.status]}</span>
              {j.error && <small>{j.error.type}</small>}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">Обработка ещё не запускалась.</p>
      )}
      {failed.length > 0 && (
        <p className="error">
          Неудачных заданий: {failed.length}. Они сохранены в истории и не
          скрыты из статистики.
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
