import { useEffect, useState } from 'react'
import { CategoryRow } from '../components/CategoryRow'
import { EmptyState } from '../components/EmptyState'
import { useToast } from '../components/ToastContext'
import { useCategories, useCreateCategory } from '../store/categories'
import { usePatchSettings, useSettings } from '../store/settings'
import styles from './Settings.module.css'

export function Settings() {
  const { data: settings, isLoading } = useSettings()
  const patchSettings = usePatchSettings()
  const { data: categories } = useCategories()
  const createCategory = useCreateCategory()
  const { showToast } = useToast()

  const [footageDir, setFootageDir] = useState('')
  const [embeddingsBackend, setEmbeddingsBackend] = useState('gemini')
  const [llmProvider, setLlmProvider] = useState('gemini')
  const [llmModel, setLlmModel] = useState('')
  const [ollamaUrl, setOllamaUrl] = useState('')

  const [newCategoryName, setNewCategoryName] = useState('')
  const [newCategoryQuery, setNewCategoryQuery] = useState('')
  const [newCategoryThreshold, setNewCategoryThreshold] = useState(0.7)

  useEffect(() => {
    if (!settings) return
    setFootageDir(settings.footage_dir ?? '')
    setEmbeddingsBackend(settings.embeddings_backend ?? 'gemini')
    setLlmProvider(settings.llm_provider ?? 'gemini')
    setLlmModel(settings.llm_model ?? '')
    setOllamaUrl(settings.ollama_url ?? '')
  }, [settings])

  function saveSettings() {
    patchSettings.mutate(
      {
        footage_dir: footageDir,
        embeddings_backend: embeddingsBackend,
        llm_provider: llmProvider,
        llm_model: llmModel,
        ollama_url: ollamaUrl,
      },
      {
        onSuccess: () => showToast('Settings saved', { tone: 'success' }),
        onError: (err) => showToast(err instanceof Error ? err.message : 'Save failed', { tone: 'error' }),
      },
    )
  }

  async function addCategory() {
    if (!newCategoryName.trim() || !newCategoryQuery.trim()) {
      showToast('Name and query text are required', { tone: 'error' })
      return
    }
    try {
      await createCategory.mutateAsync({
        name: newCategoryName.trim(),
        query_text: newCategoryQuery.trim(),
        threshold: newCategoryThreshold,
        save_top: 5,
        rerank: false,
        enabled: true,
        is_builtin: false,
      })
      setNewCategoryName('')
      setNewCategoryQuery('')
      setNewCategoryThreshold(0.7)
      showToast('Category added', { tone: 'success' })
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to add category', { tone: 'error' })
    }
  }

  return (
    <div className={styles.page}>
      <h1>Settings</h1>

      <section className={`card ${styles.section}`}>
        <h3>Pipeline configuration</h3>
        {isLoading ? (
          <EmptyState title="Loading settings…" />
        ) : (
          <>
            <div className={styles.formGrid}>
              <div className="field">
                <label className="label" htmlFor="footage-dir">
                  Footage directory
                </label>
                <input
                  id="footage-dir"
                  className="input"
                  value={footageDir}
                  onChange={(e) => setFootageDir(e.target.value)}
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="embeddings-backend">
                  Embeddings backend
                </label>
                <select
                  id="embeddings-backend"
                  className="select"
                  value={embeddingsBackend}
                  onChange={(e) => setEmbeddingsBackend(e.target.value)}
                >
                  <option value="gemini">Gemini</option>
                  <option value="dashscope">DashScope</option>
                  <option value="local">Local (Qwen3-VL)</option>
                </select>
              </div>
              <div className="field">
                <label className="label" htmlFor="llm-provider">
                  Creative LLM provider
                </label>
                <select
                  id="llm-provider"
                  className="select"
                  value={llmProvider}
                  onChange={(e) => setLlmProvider(e.target.value)}
                >
                  <option value="gemini">Gemini</option>
                  <option value="ollama">Ollama</option>
                </select>
              </div>
              <div className="field">
                <label className="label" htmlFor="llm-model">
                  LLM model
                </label>
                <input
                  id="llm-model"
                  className="input"
                  value={llmModel}
                  onChange={(e) => setLlmModel(e.target.value)}
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="ollama-url">
                  Ollama URL
                </label>
                <input
                  id="ollama-url"
                  className="input"
                  placeholder="http://localhost:11434"
                  value={ollamaUrl}
                  onChange={(e) => setOllamaUrl(e.target.value)}
                />
              </div>
            </div>
            <button className="btn btn-primary" onClick={saveSettings} disabled={patchSettings.isPending} style={{ alignSelf: 'flex-start' }}>
              {patchSettings.isPending ? 'Saving…' : 'Save settings'}
            </button>

            <div className={styles.authRow}>
              <span className={`status-dot ${settings?.youtube_authenticated ? 'ok' : 'warn'}`} />
              <span>
                YouTube: {settings?.youtube_authenticated ? 'Authenticated' : 'Not authenticated'}
              </span>
              {!settings?.youtube_authenticated && (
                <span style={{ color: 'var(--text-faint)' }}>
                  — run <code>dashpublish init</code> on the server to authenticate.
                </span>
              )}
            </div>
          </>
        )}
      </section>

      <section className={`card ${styles.section}`}>
        <h3>Categories</h3>
        {categories?.length === 0 ? (
          <EmptyState title="No categories configured" />
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Query</th>
                <th>Threshold</th>
                <th>Save top</th>
                <th>Rerank</th>
                <th>Enabled</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(categories ?? []).map((c) => (
                <CategoryRow key={c.id} category={c} />
              ))}
            </tbody>
          </table>
        )}

        <div className={styles.addRow}>
          <input
            className="input"
            placeholder="Category name"
            value={newCategoryName}
            onChange={(e) => setNewCategoryName(e.target.value)}
          />
          <input
            className="input"
            placeholder="Query text"
            value={newCategoryQuery}
            onChange={(e) => setNewCategoryQuery(e.target.value)}
          />
          <input
            className="input"
            type="number"
            step="0.01"
            min={0}
            max={1}
            style={{ maxWidth: 90 }}
            value={newCategoryThreshold}
            onChange={(e) => setNewCategoryThreshold(Number(e.target.value))}
          />
          <button className="btn btn-primary" onClick={addCategory} disabled={createCategory.isPending}>
            Add category
          </button>
        </div>
      </section>
    </div>
  )
}
