export function shouldShowUpdatedVersion(createdVersion, updatedVersion) {
  const created = String(createdVersion || '').trim()
  const updated = String(updatedVersion || '').trim()
  if (!updated) {
    return false
  }
  if (!created) {
    return true
  }
  return created !== updated
}

export function buildVersionBadges(createdVersion, updatedVersion) {
  const created = String(createdVersion || '').trim()
  const updated = String(updatedVersion || '').trim()
  const badges = []

  if (created) {
    badges.push({
      key: 'created',
      label: `创建 ${created}`
    })
  }

  if (shouldShowUpdatedVersion(created, updated)) {
    badges.push({
      key: 'updated',
      label: `更新 ${updated}`
    })
  }

  return badges
}
