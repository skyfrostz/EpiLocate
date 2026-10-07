export function formatDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(date)
}

export function formatPercent(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? new Intl.NumberFormat('zh-CN', { style: 'percent', maximumFractionDigits: 2 }).format(value)
    : '—'
}
