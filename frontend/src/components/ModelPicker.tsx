import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Check, CircleAlert, Cpu, Loader2, RefreshCw, Search, X } from 'lucide-react';
import { api, ApiError } from '@/lib/api';
import { useChat } from '@/lib/chat-store';
import type { ModelCatalog, ModelOption, ProviderInfo } from '@/lib/types';
import { cn } from '@/lib/utils';

/** Rows drawn at once; OpenRouter alone lists hundreds. Search narrows the rest. */
const MAX_ROWS = 120;

function providerStatus(p: ProviderInfo): { text: string; tone: 'ok' | 'warn' | 'off' } {
  if (!p.configured) return { text: p.needs ?? 'Not set up', tone: 'off' };
  if (p.error) return { text: p.error, tone: 'warn' };
  const n = p.models.length;
  return { text: `${n} ${n === 1 ? 'model' : 'models'}`, tone: 'ok' };
}

function matches(m: ModelOption, q: string) {
  if (!q) return true;
  const hay = `${m.id} ${m.label ?? ''}`.toLowerCase();
  return q
    .toLowerCase()
    .split(/\s+/)
    .every((word) => hay.includes(word));
}

export function ModelPicker() {
  const { modelPickerOpen: open, setModelPickerOpen, refreshMeta, toast } = useChat();
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [provider, setProvider] = useState('');
  const [model, setModel] = useState('');
  const [query, setQuery] = useState('');
  const [freeOnly, setFreeOnly] = useState(true);
  const [routerSame, setRouterSame] = useState(true);
  const [routerProvider, setRouterProvider] = useState('');
  const [routerModel, setRouterModel] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const close = () => setModelPickerOpen(false);

  const load = async (refresh = false) => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await api.models(refresh);
      setCatalog(data);
      return data;
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Couldn't load the model list.");
      return null;
    } finally {
      setLoading(false);
    }
  };

  // Start from the current choice each time the picker opens.
  useEffect(() => {
    if (!open) return;
    setSaveError(null);
    setQuery('');
    void load().then((data) => {
      if (!data) return;
      const { main, router } = data.current;
      setProvider(main.provider);
      setModel(main.model);
      const same = router.provider === main.provider && router.model === main.model;
      setRouterSame(same);
      setRouterProvider(router.provider);
      setRouterModel(router.model);
      requestAnimationFrame(() => {
        searchRef.current?.focus();
        // Show the current model even when it's far down a long list.
        document.querySelector('[aria-label="Models"] [aria-selected="true"]')?.scrollIntoView({ block: 'nearest' });
      });
    });
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const providers = catalog?.providers ?? [];
  const current = providers.find((p) => p.id === provider);
  const hasFree = !!current?.models.some((m) => m.free);
  const filtered = useMemo(() => {
    const list = (current?.models ?? []).filter((m) => (!hasFree || !freeOnly || m.free) && matches(m, query.trim()));
    return list;
  }, [current, hasFree, freeOnly, query]);
  const typed = query.trim();
  // Offer the typed text as a model id only when it looks like one (org/name, name:tag) or nothing matches.
  const canUseTyped =
    !!typed && !/\s/.test(typed) && !current?.models.some((m) => m.id === typed) && (/[/:]/.test(typed) || filtered.length === 0);
  const selectedOption = current?.models.find((m) => m.id === model);
  const routerOptions = providers.find((p) => p.id === routerProvider)?.models ?? [];
  const usable = providers.filter((p) => p.configured);

  const pickProvider = (p: ProviderInfo) => {
    if (!p.configured) return;
    setProvider(p.id);
    setQuery('');
    setSaveError(null);
    // Keep the model if it belongs to this provider, else use its default.
    setModel(catalog?.current.main.provider === p.id ? catalog.current.main.model : p.default_model);
  };

  const save = async () => {
    if (!provider || !model.trim()) return;
    setSaving(true);
    setSaveError(null);
    try {
      const routerChoice = routerSame || !routerProvider || !routerModel.trim() ? null : { provider: routerProvider, model: routerModel.trim() };
      const res = await api.setModels({ provider, model: model.trim() }, routerChoice);
      await refreshMeta();
      toast(`Now answering with ${res.main.model}.`, 'success');
      close();
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Couldn't save the model.");
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const res = await api.resetModels();
      await refreshMeta();
      toast(`Back to the model from .env: ${res.main.model}.`, 'success');
      close();
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Couldn't reset the model.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[65] flex items-end justify-center p-0 sm:items-center sm:p-4">
          <motion.div
            className="absolute inset-0 bg-black/40 backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={close}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="model-picker-title"
            onKeyDown={(e) => e.key === 'Escape' && close()}
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 420, damping: 34 }}
            className="relative flex max-h-[92vh] w-full max-w-[680px] flex-col rounded-t-2xl border border-line bg-bg shadow-lift sm:max-h-[86vh] sm:rounded-2xl"
          >
            <header className="flex items-start gap-3 px-5 pb-3 pt-5">
              <Cpu className="mt-1 size-5 shrink-0 text-route-chat" />
              <div className="min-w-0 flex-1">
                <h2 id="model-picker-title" className="text-[19px] font-[780] tracking-[-0.01em] text-ink">
                  Choose a model
                </h2>
                <p className="mt-1 text-[13.5px] leading-relaxed text-muted">
                  Used for every answer. Saved on the server, and it overrides <code className="font-mono text-[12.5px]">LLM_PROVIDER</code> in
                  .env until you reset it.
                </p>
              </div>
              <button
                type="button"
                onClick={() => void load(true)}
                disabled={loading}
                className="rounded-lg p-2 text-muted transition hover:bg-raised hover:text-ink disabled:opacity-50"
                aria-label="Reload model lists"
                title="Reload model lists"
              >
                <RefreshCw className={cn('size-4', loading && 'animate-spin')} />
              </button>
              <button type="button" onClick={close} className="rounded-lg p-2 text-muted transition hover:bg-raised hover:text-ink" aria-label="Close">
                <X className="size-4" />
              </button>
            </header>

            <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto px-5 pb-4">
              {!catalog && loading && (
                <div className="flex items-center gap-2 py-10 text-[14px] text-muted">
                  <Loader2 className="size-4 animate-spin" /> Asking each provider for its models…
                </div>
              )}
              {loadError && (
                <p role="alert" className="rounded-xl border border-danger/40 bg-danger/10 px-3.5 py-2.5 text-[14px] text-ink">
                  {loadError}
                </p>
              )}

              {catalog && (
                <>
                  <h3 className="mb-2 mt-1 text-[12.5px] font-semibold text-faint">Provider</h3>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Provider">
                    {providers.map((p) => {
                      const s = providerStatus(p);
                      const active = p.id === provider;
                      return (
                        <button
                          key={p.id}
                          type="button"
                          role="radio"
                          aria-checked={active}
                          disabled={!p.configured}
                          onClick={() => pickProvider(p)}
                          className={cn(
                            'flex min-h-[56px] items-start gap-2.5 rounded-xl border px-3 py-2.5 text-left transition',
                            active ? 'border-accent bg-accent/10' : 'border-line hover:border-line-strong hover:bg-raised',
                            !p.configured && 'cursor-not-allowed opacity-60 hover:border-line hover:bg-transparent',
                          )}
                        >
                          <span
                            className={cn(
                              'mt-[7px] size-2 shrink-0 rounded-full',
                              s.tone === 'ok' ? 'bg-route-agent' : s.tone === 'warn' ? 'bg-route-docs' : 'bg-line-strong',
                            )}
                            aria-hidden
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block text-[14px] font-semibold text-ink">{p.label}</span>
                            <span className="block truncate text-[12.5px] text-muted" title={s.text}>
                              {s.text}
                            </span>
                          </span>
                          {active && <Check className="mt-1 size-4 shrink-0 text-accent" />}
                        </button>
                      );
                    })}
                  </div>

                  {current && (
                    <>
                      <div className="mb-2 mt-5 flex flex-wrap items-center justify-between gap-2">
                        <h3 className="text-[12.5px] font-semibold text-faint">Model</h3>
                        {hasFree && (
                          <label className="inline-flex cursor-pointer items-center gap-2 text-[13px] text-muted">
                            <input type="checkbox" checked={freeOnly} onChange={(e) => setFreeOnly(e.target.checked)} className="size-4 accent-[var(--accent)]" />
                            Free models only
                          </label>
                        )}
                      </div>
                      <label className="flex items-center gap-2 rounded-xl border border-line bg-raised px-3 focus-within:border-line-strong">
                        <Search className="size-4 text-faint" />
                        <span className="sr-only">Search models, or type a model id</span>
                        <input
                          ref={searchRef}
                          value={query}
                          onChange={(e) => setQuery(e.target.value)}
                          placeholder="Search, or type any model id"
                          className="min-h-[42px] min-w-0 flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-faint"
                        />
                      </label>

                      <ul role="listbox" aria-label="Models" className="scroll-quiet mt-2 max-h-[min(300px,38vh)] overflow-y-auto rounded-xl border border-line">
                        {canUseTyped && (
                          <li>
                            <button
                              type="button"
                              role="option"
                              aria-selected={model === typed}
                              onClick={() => setModel(typed)}
                              className={cn('flex w-full items-center gap-2 px-3 py-2.5 text-left text-[14px] transition hover:bg-raised', model === typed && 'bg-accent/10')}
                            >
                              <span className="text-muted">Use model id</span>
                              <span className="truncate font-mono text-[13px] text-ink">{typed}</span>
                            </button>
                          </li>
                        )}
                        {filtered.slice(0, MAX_ROWS).map((m) => {
                          const active = m.id === model;
                          return (
                            <li key={m.id} className="border-t border-line first:border-t-0">
                              <button
                                type="button"
                                role="option"
                                aria-selected={active}
                                onClick={() => setModel(m.id)}
                                className={cn('flex w-full items-center gap-2 px-3 py-2 text-left transition hover:bg-raised', active && 'bg-accent/10')}
                              >
                                <span className="min-w-0 flex-1">
                                  <span className="block truncate text-[14px] text-ink">{m.label || m.id}</span>
                                  {m.label && m.label !== m.id && <span className="block truncate font-mono text-[12px] text-faint">{m.id}</span>}
                                </span>
                                {m.free && <span className="rounded-full bg-route-agent/15 px-2 py-0.5 text-[11.5px] font-semibold text-route-agent">free</span>}
                                {m.tools === false && (
                                  <span className="rounded-full bg-route-docs/15 px-2 py-0.5 text-[11.5px] font-semibold text-route-docs" title="Can't call tools, so Research can't search">
                                    no tools
                                  </span>
                                )}
                                {active && <Check className="size-4 shrink-0 text-accent" />}
                              </button>
                            </li>
                          );
                        })}
                        {!filtered.length && !canUseTyped && (
                          <li className="px-3 py-4 text-[13.5px] text-muted">
                            {current.models.length ? 'No models match. Type a full model id to use it anyway.' : 'No models listed. Type a model id to use it.'}
                          </li>
                        )}
                        {filtered.length > MAX_ROWS && (
                          <li className="border-t border-line px-3 py-2 text-[12.5px] text-faint">
                            {filtered.length - MAX_ROWS} more. Search to narrow the list.
                          </li>
                        )}
                      </ul>
                      {selectedOption?.tools === false && (
                        <p className="mt-2 flex items-start gap-2 text-[13px] text-route-docs">
                          <CircleAlert className="mt-0.5 size-4 shrink-0" />
                          This model can't call tools, so Research answers won't be able to search the web or use the calculator.
                        </p>
                      )}

                      <h3 className="mb-2 mt-5 text-[12.5px] font-semibold text-faint">Routing</h3>
                      <label className="flex cursor-pointer items-start gap-2.5 text-[14px] text-ink">
                        <input type="checkbox" checked={routerSame} onChange={(e) => setRouterSame(e.target.checked)} className="mt-0.5 size-4 accent-[var(--accent)]" />
                        <span>
                          Use the same model to pick routes, titles and summaries
                          <span className="block text-[12.5px] text-muted">Turn off to use a faster or cheaper model for these small calls.</span>
                        </span>
                      </label>
                      {!routerSame && (
                        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
                          <label className="text-[12.5px] text-muted">
                            Provider
                            <select
                              value={routerProvider}
                              onChange={(e) => {
                                setRouterProvider(e.target.value);
                                setRouterModel(usable.find((p) => p.id === e.target.value)?.default_model ?? '');
                              }}
                              className="mt-1 block min-h-[42px] w-full rounded-xl border border-line bg-raised px-2.5 text-[15px] text-ink outline-none focus:border-line-strong"
                            >
                              {usable.map((p) => (
                                <option key={p.id} value={p.id}>
                                  {p.label}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="text-[12.5px] text-muted">
                            Model
                            <input
                              list="router-models"
                              value={routerModel}
                              onChange={(e) => setRouterModel(e.target.value)}
                              placeholder="Model id"
                              className="mt-1 block min-h-[42px] w-full rounded-xl border border-line bg-raised px-3 text-[15px] text-ink outline-none focus:border-line-strong"
                            />
                            <datalist id="router-models">
                              {routerOptions.slice(0, 300).map((m) => (
                                <option key={m.id} value={m.id}>
                                  {m.label}
                                </option>
                              ))}
                            </datalist>
                          </label>
                        </div>
                      )}
                    </>
                  )}
                </>
              )}
            </div>

            <footer className="flex flex-wrap items-center gap-2 border-t border-line px-5 py-3.5">
              {saveError && (
                <p role="alert" className="w-full text-[13.5px] text-danger">
                  {saveError}
                </p>
              )}
              <p className="min-w-0 flex-1 truncate text-[12.5px] text-faint" title={model}>
                {model ? (
                  <>
                    Selected: <span className="font-mono text-ink">{model}</span>
                  </>
                ) : (
                  'Pick a model'
                )}
              </p>
              {catalog?.current.source === 'ui' && (
                <button
                  type="button"
                  onClick={() => void reset()}
                  disabled={saving}
                  className="min-h-[40px] rounded-xl px-3 text-[14px] text-muted transition hover:bg-raised hover:text-ink disabled:opacity-50"
                >
                  Reset to .env
                </button>
              )}
              <button type="button" onClick={close} className="min-h-[40px] rounded-xl border border-line px-4 text-[14px] text-ink transition hover:border-line-strong">
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void save()}
                disabled={saving || !provider || !model.trim()}
                className="inline-flex min-h-[40px] items-center gap-2 rounded-xl bg-accent px-4 text-[14px] font-semibold text-accent-ink transition active:scale-[0.97] disabled:opacity-40"
              >
                {saving && <Loader2 className="size-4 animate-spin" />}
                Use this model
              </button>
            </footer>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
