// Login suggested from the full name: "Błażej Kowalski" -> "blazej.kowalski".
// The admin can still change it, e.g. when the login is taken.

const MAX_LOGIN_LENGTH = 50

export function loginFromName(fullName: string): string {
  return (
    fullName
      .toLowerCase()
      // "ł" has no accent to strip, so it needs its own rule
      .replaceAll('ł', 'l')
      // split letters from their accents ("ż" -> "z" + accent) and drop the accents
      .normalize('NFD')
      .replace(/\p{Diacritic}/gu, '')
      .trim()
      .split(/\s+/)
      .map((part) => part.replace(/[^a-z0-9-]/g, ''))
      .filter(Boolean)
      .join('.')
      .slice(0, MAX_LOGIN_LENGTH)
  )
}
