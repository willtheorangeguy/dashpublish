import { useState } from 'react'
import type { CategoryOut } from '../api/types'
import { usePatchCategory, useDeleteCategory } from '../store/categories'

export function CategoryRow({ category }: { category: CategoryOut }) {
  const patchCategory = usePatchCategory()
  const deleteCategory = useDeleteCategory()
  const [queryText, setQueryText] = useState(category.query_text)
  const [threshold, setThreshold] = useState(category.threshold)
  const [saveTop, setSaveTop] = useState(category.save_top)

  function commitIfChanged() {
    const patch: Record<string, unknown> = {}
    if (queryText !== category.query_text) patch.query_text = queryText
    if (threshold !== category.threshold) patch.threshold = threshold
    if (saveTop !== category.save_top) patch.save_top = saveTop
    if (Object.keys(patch).length > 0) {
      patchCategory.mutate({ id: category.id, patch })
    }
  }

  return (
    <tr>
      <td>
        {category.name} {category.is_builtin && <span className="chip">builtin</span>}
      </td>
      <td>
        <input
          type="text"
          className="input"
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          onBlur={commitIfChanged}
        />
      </td>
      <td>
        <input
          type="number"
          step="0.01"
          min={0}
          max={1}
          className="input"
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          onBlur={commitIfChanged}
        />
      </td>
      <td>
        <input
          type="number"
          min={0}
          className="input"
          value={saveTop}
          onChange={(e) => setSaveTop(Number(e.target.value))}
          onBlur={commitIfChanged}
        />
      </td>
      <td>
        <input
          type="checkbox"
          checked={category.rerank}
          onChange={(e) => patchCategory.mutate({ id: category.id, patch: { rerank: e.target.checked } })}
        />
      </td>
      <td>
        <input
          type="checkbox"
          checked={category.enabled}
          onChange={(e) => patchCategory.mutate({ id: category.id, patch: { enabled: e.target.checked } })}
        />
      </td>
      <td>
        <button
          className="btn btn-sm btn-danger"
          disabled={category.is_builtin || deleteCategory.isPending}
          title={category.is_builtin ? 'Built-in categories cannot be deleted' : 'Delete category'}
          onClick={() => deleteCategory.mutate(category.id)}
        >
          Delete
        </button>
      </td>
    </tr>
  )
}
