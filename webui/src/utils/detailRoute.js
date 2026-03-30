export function buildDetailLocation(detailQuery = {}) {
  const normalizedQuery = {}

  Object.entries(detailQuery).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return
    }
    normalizedQuery[key] = String(value)
  })

  return {
    path: '/detail',
    query: normalizedQuery
  }
}
