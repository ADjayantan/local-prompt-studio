'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  Check,
  Clock3,
  Download,
  Eye,
  FileText,
  Film,
  FolderOpen,
  HardDrive,
  Image as ImageIcon,
  Laptop,
  LoaderCircle,
  Presentation,
  Plus,
  Sparkles,
  Volume2,
  WandSparkles,
  Wifi,
  WifiOff,
  Zap,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Textarea } from '@/components/ui/textarea';

type CreatorMode = 'image' | 'audio' | 'video' | 'ppt' | 'markdown';
type JobStatus = 'queued' | 'running' | 'complete' | 'error';

type Job = {
  id: string;
  type: CreatorMode;
  prompt: string;
  status: JobStatus;
  progress: number;
  message: string;
  outputName?: string;
  outputPath?: string;
  fileUrl?: string;
  previewUrl?: string;
  error?: string;
};

type Capability = { ready: boolean; engine: string };
type SystemStatus = {
  offline: boolean;
  outputRoot: string;
  freeGb: number;
  capabilities: Record<CreatorMode, Capability>;
};

type WebMcpContext = {
  registerTool: (tool: Record<string, unknown>, options?: { signal?: AbortSignal }) => void | Promise<void>;
};

const DEFAULT_API = 'http://localhost:8765';

type LocalRequestInit = RequestInit & { targetAddressSpace?: 'loopback' };

function localFetch(input: RequestInfo | URL, init: LocalRequestInit = {}) {
  // A public HTTPS page needs to declare that this request deliberately targets
  // the local machine. Chrome then presents its Local Network Access prompt.
  const request = new Request(input, {
    ...init,
    mode: 'cors',
    targetAddressSpace: 'loopback',
  } as RequestInit);
  return fetch(request);
}

const modes = [
  { id: 'image' as const, label: 'Image', icon: ImageIcon, time: '40–90 sec', engine: 'ComfyUI + RTX GPU' },
  { id: 'audio' as const, label: 'Audio', icon: Volume2, time: '10–30 sec', engine: 'Windows TTS + Audacity' },
  { id: 'video' as const, label: 'Video', icon: Film, time: '3–10 min', engine: 'ComfyUI + FFmpeg + Shotcut' },
  { id: 'ppt' as const, label: 'PowerPoint', icon: Presentation, time: '20–90 sec', engine: 'LibreOffice Impress' },
  { id: 'markdown' as const, label: 'Markdown', icon: FileText, time: '< 5 sec', engine: 'Local template' },
];

const examples: Record<CreatorMode, string[]> = {
  image: ['Life cycle of a butterfly', 'Seven stages of human life', 'Solar system classroom poster'],
  audio: ['Welcome to VSB College. Create a clear 30-second introduction.', 'Read this announcement in a calm voice.'],
  video: ['Create a 30-second nature awareness video', 'Make a cinematic college event promo'],
  ppt: ['Natural disasters — 6 slide classroom lesson', 'Introduction to artificial intelligence'],
  markdown: ['Project report on rainwater harvesting', 'Meeting notes for our college event'],
};

const modeLabels: Record<CreatorMode, string> = {
  image: 'Image', audio: 'Audio', video: 'Video', ppt: 'PowerPoint', markdown: 'Markdown',
};

async function readJson<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data as T;
}

function OutputPreview({ job }: { job: Job }) {
  const [markdown, setMarkdown] = useState('');

  useEffect(() => {
    if (job.type !== 'markdown' || !job.fileUrl) return;
    let active = true;
    fetch(job.fileUrl)
      .then((response) => response.text())
      .then((value) => { if (active) setMarkdown(value); })
      .catch(() => { if (active) setMarkdown('Preview could not be loaded.'); });
    return () => { active = false; };
  }, [job.fileUrl, job.type]);

  if (!job.fileUrl) return null;

  return (
    <div id="output-preview" className="mt-4 overflow-hidden rounded-xl border border-primary/20 bg-black/20">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/8 px-4 py-3">
        <div><p className="text-sm font-semibold">Output preview</p><p className="max-w-[34rem] truncate text-xs text-muted-foreground">{job.outputName}</p></div>
        <Button asChild size="sm" variant="outline" className="border-white/10 bg-white/5"><a href={job.fileUrl} target="_blank" rel="noreferrer"><Download /> Open original</a></Button>
      </div>
      {job.type === 'image' && <img src={job.fileUrl} alt={job.prompt} className="max-h-[34rem] w-full bg-[#05080a] object-contain" />}
      {job.type === 'audio' && <div className="p-5"><audio controls preload="metadata" src={job.fileUrl} className="w-full" /></div>}
      {job.type === 'video' && <video controls preload="metadata" src={job.fileUrl} className="max-h-[34rem] w-full bg-black" />}
      {job.type === 'ppt' && job.previewUrl && <iframe title={`${job.outputName} preview`} src={job.previewUrl} className="h-[34rem] w-full bg-white" />}
      {job.type === 'ppt' && !job.previewUrl && <div className="grid min-h-48 place-items-center p-6 text-center text-sm text-muted-foreground">Older PowerPoint output has no browser preview. Generate it once more to view the slides here.</div>}
      {job.type === 'markdown' && <pre className="max-h-[34rem] overflow-auto whitespace-pre-wrap p-5 font-sans text-sm leading-7 text-foreground">{markdown || 'Loading preview…'}</pre>}
    </div>
  );
}

export default function StudioClient() {
  const [mode, setMode] = useState<CreatorMode>('image');
  const [prompt, setPrompt] = useState('');
  const [job, setJob] = useState<Job | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [serverError, setServerError] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [remoteConnectionRequested, setRemoteConnectionRequested] = useState(false);
  const [apiBase, setApiBase] = useState(DEFAULT_API);
  const [apiDraft, setApiDraft] = useState(DEFAULT_API);
  const active = useMemo(() => modes.find((item) => item.id === mode)!, [mode]);
  const busy = job?.status === 'queued' || job?.status === 'running';

  const refresh = useCallback(async () => {
    setConnecting(true);
    try {
      const [nextSystem, nextJobs] = await Promise.all([
        localFetch(`${apiBase}/api/status`).then((response) => readJson<SystemStatus>(response)),
        localFetch(`${apiBase}/api/jobs`).then((response) => readJson<Job[]>(response)),
      ]);
      setSystem(nextSystem);
      setJobs(nextJobs);
      setServerError('');
      if (window.location.hostname.endsWith('github.io')) {
        window.localStorage.setItem('prompt-studio-local-access', 'connected');
      }
    } catch {
      setSystem(null);
      setServerError('Cannot reach the local backend yet. Click “Connect to laptop” and allow the browser permission prompt. If the local engine is off, run start-local-studio.ps1.');
    } finally {
      setConnecting(false);
    }
  }, [apiBase]);

  useEffect(() => {
    const saved = window.localStorage.getItem('prompt-studio-api');
    if (!saved) return;
    setApiBase(saved);
    setApiDraft(saved);
  }, []);

  useEffect(() => {
    // Chrome requires a user gesture before a public HTTPS page can request
    // loopback-network permission. The Connect button below provides it.
    const hosted = window.location.hostname.endsWith('github.io');
    const remembered = window.localStorage.getItem('prompt-studio-local-access') === 'connected';
    if (hosted && !remoteConnectionRequested && !remembered) return;
    if (!hosted || remembered) void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 5000);
    return () => window.clearInterval(timer);
  }, [refresh, remoteConnectionRequested]);

  useEffect(() => {
    if (!job || !['queued', 'running'].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await localFetch(`${apiBase}/api/jobs/${job.id}`).then((response) => readJson<Job>(response));
        setJob(next);
        if (next.status === 'complete' || next.status === 'error') {
          window.clearInterval(timer);
          void refresh();
        }
      } catch (error) {
        setServerError(error instanceof Error ? error.message : 'Could not read local job');
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [apiBase, job, refresh]);

  const startCreation = useCallback(async (creationType: CreatorMode, creationPrompt: string) => {
    const cleanPrompt = creationPrompt.trim();
    if (cleanPrompt.length < 3) throw new Error('Please enter a prompt with at least 3 characters.');
    const created = await localFetch(`${apiBase}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: creationType, prompt: cleanPrompt }),
    }).then((response) => readJson<Job>(response));
    setMode(creationType);
    setPrompt(cleanPrompt);
    setJob(created);
    setServerError('');
    return { id: created.id, status: created.status, type: created.type };
  }, [apiBase]);

  useEffect(() => {
    const context = (document as Document & { modelContext?: WebMcpContext }).modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    const report = () => undefined;
    void Promise.resolve(context.registerTool({
      name: 'start_local_creation',
      title: 'Start local creation',
      description: 'Start one offline image, audio, video, PowerPoint, or Markdown job and show it in Local Prompt Studio.',
      inputSchema: {
        type: 'object',
        properties: {
          type: { type: 'string', enum: ['image', 'audio', 'video', 'ppt', 'markdown'] },
          prompt: { type: 'string', minLength: 3, maxLength: 4000 },
        },
        required: ['type', 'prompt'],
        additionalProperties: false,
      },
      annotations: { readOnlyHint: false, untrustedContentHint: false },
      execute: async (input: unknown) => {
        const value = input as { type?: CreatorMode; prompt?: string };
        if (!value || !['image', 'audio', 'video', 'ppt', 'markdown'].includes(String(value.type)) || typeof value.prompt !== 'string') {
          throw new Error('A valid creation type and prompt are required.');
        }
        return startCreation(value.type as CreatorMode, value.prompt);
      },
    }, { signal: lifecycle.signal })).catch(report);
    return () => lifecycle.abort();
  }, [startCreation]);

  async function openOutputFolder() {
    try {
      await localFetch(`${apiBase}/api/open-output`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).then((response) => readJson(response));
    } catch (error) {
      setServerError(error instanceof Error ? error.message : 'Could not open output folder');
    }
  }

  function saveApiAddress() {
    const next = apiDraft.trim().replace(/\/$/, '') || DEFAULT_API;
    window.localStorage.setItem('prompt-studio-api', next);
    setApiBase(next);
    setApiDraft(next);
    setServerError('');
  }

  function previewJob(item: Job) {
    setMode(item.type);
    setJob(item);
    window.setTimeout(() => document.getElementById('output-preview')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50);
  }

  function createAnother() {
    setJob(null);
    setPrompt('');
    setServerError('');
    window.setTimeout(() => document.getElementById('prompt')?.focus(), 50);
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-white/8 bg-[#0b1014]/94 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1540px] items-center justify-between px-4 sm:px-7">
          <div className="flex items-center gap-3">
            <div className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground shadow-[0_0_24px_rgba(201,244,90,0.2)]"><WandSparkles className="size-5" /></div>
            <div><p className="text-[0.72rem] font-semibold tracking-[0.18em] text-primary uppercase">Local creator</p><h1 className="text-base font-semibold tracking-tight">Prompt Studio</h1></div>
          </div>
          <Badge className="h-7 border-emerald-400/20 bg-emerald-400/10 px-3 text-emerald-300"><WifiOff data-icon="inline-start" /> Works offline</Badge>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1540px] gap-4 p-4 sm:p-7 lg:grid-cols-[220px_minmax(0,1fr)_300px]">
        <aside className="rounded-2xl border border-white/8 bg-card/70 p-3 shadow-2xl shadow-black/15">
          <p className="px-3 pt-2 pb-3 text-xs font-semibold tracking-[0.16em] text-muted-foreground uppercase">Create</p>
          <nav className="flex gap-2 overflow-x-auto lg:flex-col" aria-label="Creation types">
            {modes.map((item) => {
              const Icon = item.icon;
              const selected = item.id === mode;
              const ready = system?.capabilities[item.id]?.ready ?? true;
              return (
                <Button key={item.id} type="button" variant="ghost" disabled={busy} onClick={() => { setMode(item.id); setJob(null); }} className={`h-auto min-w-[145px] justify-start gap-3 rounded-xl px-3 py-3 lg:w-full ${selected ? 'border-primary/25 bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary' : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'}`}>
                  <span className={`grid size-9 place-items-center rounded-lg ${selected ? 'bg-primary text-primary-foreground' : 'bg-white/6'}`}><Icon className="size-[18px]" /></span>
                  <span className="text-left"><span className="block text-sm font-semibold">{item.label}</span><span className="block text-xs font-normal opacity-60">{ready ? item.time : 'Engine starting…'}</span></span>
                </Button>
              );
            })}
          </nav>
          <div className="mt-5 hidden rounded-xl border border-white/8 bg-black/15 p-3 lg:block">
            <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground"><HardDrive className="size-3.5" /> D: storage</div>
            <Progress value={10.1} className="[&_[data-slot=progress-indicator]]:bg-cyan-400" />
            <p className="mt-2 text-xs text-muted-foreground">{system ? `${system.freeGb} GB available` : 'Checking storage…'}</p>
          </div>
        </aside>

        <section className="min-w-0 space-y-4">
          <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-card p-5 shadow-2xl shadow-black/20 sm:p-7">
            <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/70 to-transparent" />
            <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="mb-2 flex items-center gap-2 text-xs font-medium text-primary"><Zap className="size-3.5 fill-current" /> {system?.capabilities[mode]?.engine ?? active.engine}</div>
                <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Create {active.label}</h2>
                <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">Describe what you need. The job runs on this laptop and saves the result to D:\CLI-Anything\PromptStudio.</p>
              </div>
              <Badge variant="outline" className="h-7 border-white/10 bg-white/4 px-3 text-muted-foreground">Estimated {active.time}</Badge>
            </div>

            <label htmlFor="prompt" className="mb-2 block text-sm font-semibold">Your prompt</label>
            <div className="rounded-2xl border border-white/10 bg-[#0a0f13] p-2 transition focus-within:border-primary/45 focus-within:ring-4 focus-within:ring-primary/5">
              <Textarea id="prompt" value={prompt} disabled={busy} onChange={(event) => setPrompt(event.target.value)} placeholder={`Example: ${examples[mode][0]}`} className="min-h-36 resize-none border-0 bg-transparent p-3 text-base leading-7 shadow-none focus-visible:ring-0" />
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/7 px-2 pt-2">
                <div className="flex flex-wrap gap-2">{examples[mode].slice(0, 2).map((example) => <Button key={example} type="button" variant="ghost" size="sm" disabled={busy} onClick={() => setPrompt(example)} className="rounded-full bg-white/5 px-3 text-xs text-muted-foreground hover:bg-white/10 hover:text-foreground">{example}</Button>)}</div>
                <Button type="button" size="lg" onClick={() => void startCreation(mode, prompt).catch((error) => setServerError(error.message))} disabled={!prompt.trim() || busy} className="h-11 rounded-xl px-5 font-semibold shadow-[0_8px_30px_rgba(201,244,90,0.12)]">
                  {busy ? <LoaderCircle className="animate-spin" /> : <Sparkles />}{busy ? 'Creating…' : `Generate ${active.label}`}
                </Button>
              </div>
            </div>

            {serverError && <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-400/20 bg-red-400/8 p-3 text-sm text-red-200"><span className="flex items-start gap-2"><AlertCircle className="mt-0.5 size-4 shrink-0" />{serverError}</span><Button type="button" size="sm" variant="outline" onClick={() => void refresh()} className="border-red-300/25 bg-red-300/5">Retry connection</Button></div>}
            {job && (
              <div className={`mt-5 rounded-xl border p-4 ${job.status === 'error' ? 'border-red-400/20 bg-red-400/5' : 'border-white/8 bg-white/[0.025]'}`}>
                <div className="mb-3 flex items-center justify-between gap-3 text-sm"><span className="font-medium">{job.status === 'error' ? job.error : job.message} <span className="ml-2 font-mono text-xs text-muted-foreground">Job #{job.id.slice(0, 6)}</span></span><span className="font-mono text-xs text-primary">{job.progress}%</span></div>
                <Progress value={job.progress} className="[&_[data-slot=progress-indicator]]:bg-primary" />
                {job.status === 'complete' && <OutputPreview job={job} />}
                {job.status === 'complete' && <Button type="button" variant="secondary" onClick={createAnother} className="mt-4"><Plus /> Create another</Button>}
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-white/8 bg-card/60 p-5">
            <div className="mb-4 flex items-center justify-between"><h3 className="font-semibold">Recent outputs</h3><Button variant="ghost" size="sm" onClick={() => void openOutputFolder()} className="text-muted-foreground"><FolderOpen /> Open D: folder</Button></div>
            <div className="grid gap-2">
              {jobs.length === 0 ? <p className="rounded-xl border border-dashed border-white/10 p-5 text-center text-sm text-muted-foreground">Your local creations will appear here.</p> : jobs.slice(0, 5).map((item) => (
                <div key={item.id} className="flex items-center gap-3 rounded-xl border border-white/7 bg-black/10 px-3 py-3">
                  <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-cyan-400/10 text-cyan-300"><FileText className="size-4" /></div>
                  <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{item.outputName ?? item.prompt}</p><p className="text-xs text-muted-foreground">{modeLabels[item.type]} · Job #{item.id.slice(0, 6)} · D:\CLI-Anything\PromptStudio</p></div>
                  {item.status === 'complete' && item.fileUrl ? <Button type="button" variant="ghost" size="sm" onClick={() => previewJob(item)} className="text-cyan-200"><Eye /> Preview</Button> : <span className={`flex items-center gap-1 text-xs ${item.status === 'error' ? 'text-red-300' : 'text-emerald-300'}`}>{item.status === 'complete' ? <Check className="size-3.5" /> : item.status === 'error' ? <AlertCircle className="size-3.5" /> : <LoaderCircle className="size-3.5 animate-spin" />}{item.status}</span>}
                </div>
              ))}
            </div>
          </div>
        </section>

        <aside className="space-y-4">
          <div className="rounded-2xl border border-white/8 bg-card/70 p-5">
            <div className="mb-4 flex items-center justify-between"><h3 className="font-semibold">Local system</h3><span className={`relative flex size-2.5 ${serverError ? 'opacity-40' : ''}`}><span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-60" /><span className="relative inline-flex size-2.5 rounded-full bg-emerald-400" /></span></div>
            <div className="space-y-3">
              {modes.map((item) => <div key={item.id} className="flex items-center justify-between gap-3 border-b border-white/6 pb-3 text-sm last:border-0 last:pb-0"><span className="text-muted-foreground">{item.label}</span><span className={`font-medium ${system?.capabilities[item.id]?.ready ? 'text-emerald-300' : 'text-muted-foreground'}`}>{system ? (system.capabilities[item.id].ready ? 'Ready' : 'Offline') : 'Checking'}</span></div>)}
            </div>
            <div className="mt-5 border-t border-white/8 pt-4">
              <label htmlFor="api-address" className="mb-2 block text-xs font-medium text-muted-foreground">Laptop API address</label>
              <div className="flex gap-2">
                <input id="api-address" value={apiDraft} onChange={(event) => setApiDraft(event.target.value)} className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs outline-none focus:border-primary/45" />
                <Button type="button" size="sm" variant="outline" onClick={saveApiAddress}>Save</Button>
              </div>
              <Button type="button" size="sm" onClick={() => { setRemoteConnectionRequested(true); void refresh(); }} disabled={connecting} className={`mt-3 w-full ${system ? 'bg-emerald-500 text-white hover:bg-emerald-500' : 'bg-primary text-primary-foreground hover:bg-primary/80'}`}>
                {connecting ? <LoaderCircle className="animate-spin" /> : system ? <Check /> : <Wifi />} {connecting ? 'Connecting…' : system ? 'Laptop connected' : 'Connect to laptop'}
              </Button>
              {!system && <p className="mt-2 text-xs leading-5 text-amber-200/80">On the GitHub site, Chrome may ask to connect with an app on this laptop. Choose <strong>Allow</strong> once.</p>}
              <p className="mt-2 text-xs leading-5 text-muted-foreground">Saved in this browser. Normally you never need to change it.</p>
            </div>
          </div>
          <div className="overflow-hidden rounded-2xl border border-cyan-300/15 bg-gradient-to-br from-cyan-400/10 to-transparent p-5"><Laptop className="mb-5 size-7 text-cyan-300" /><p className="text-sm font-semibold">Private by default</p><p className="mt-2 text-sm leading-6 text-muted-foreground">Prompts and generated files stay on this laptop. No upload is required.</p></div>
          <div className="rounded-2xl border border-white/8 bg-card/70 p-5"><div className="mb-3 flex items-center gap-2 text-sm font-semibold"><Clock3 className="size-4 text-primary" /> Typical local time</div><p className="text-3xl font-semibold tracking-tight">{active.time}</p><p className="mt-2 text-xs leading-5 text-muted-foreground">Time changes with resolution, video duration and system load.</p></div>
        </aside>
      </div>
    </main>
  );
}
