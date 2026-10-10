import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

/** The retrofit package lives in the URL (?r=a,b&sp=26&pv=3) so studio and finance share it and links are shareable. */
export function useSelection(order?: Record<string, number>) {
  const [sp, setSp] = useSearchParams()
  const raw = sp.get('r')
  const selected = useMemo(() => {
    const ids = (raw ?? '').split(',').filter(Boolean)
    return order ? [...ids].sort((a, b) => (order[a] ?? 99) - (order[b] ?? 99) || a.localeCompare(b)) : ids
  }, [raw, order])
  const setpoint = sp.get('sp') ? Number(sp.get('sp')) : undefined
  const pvKw = sp.get('pv') ? Number(sp.get('pv')) : undefined

  const update = useCallback(
    (fn: (p: URLSearchParams) => void) =>
      setSp((prev) => {
        const p = new URLSearchParams(prev)
        fn(p)
        return p
      }, { replace: true }),
    [setSp],
  )
  const setSelected = useCallback((ids: string[]) => update((p) => (ids.length ? p.set('r', ids.join(',')) : p.delete('r'))), [update])
  const toggle = useCallback((id: string) => setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]), [selected, setSelected])
  const setSetpoint = useCallback((v: number | undefined) => update((p) => (v == null ? p.delete('sp') : p.set('sp', String(v)))), [update])
  const setPvKw = useCallback((v: number | undefined) => update((p) => (v == null ? p.delete('pv') : p.set('pv', String(v)))), [update])

  const params = useMemo(() => {
    const o: Record<string, number> = {}
    if (setpoint != null && selected.includes('ac_setpoint')) o.ac_setpoint_c = setpoint
    if (pvKw != null && selected.includes('rooftop_solar')) o.pv_kw = pvKw
    return o
  }, [setpoint, pvKw, selected])

  const qs = sp.toString()
  return { selected, toggle, setSelected, setpoint, setSetpoint, pvKw, setPvKw, params, qs }
}
