// Temporary password for a new account, e.g. "Kx7p-Qm2r-Zt9w".
// The admin passes it on to the user, who must set their own at first sign-in.

// No look-alike characters (0/O, 1/l/I), so it is easy to read out or copy by hand
const ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
const GROUPS = 3
const GROUP_LENGTH = 4

export function generateTempPassword(): string {
  const bytes = crypto.getRandomValues(new Uint32Array(GROUPS * GROUP_LENGTH))
  const chars = Array.from(bytes, (n) => ALPHABET[n % ALPHABET.length])
  const groups = []
  for (let i = 0; i < chars.length; i += GROUP_LENGTH) {
    groups.push(chars.slice(i, i + GROUP_LENGTH).join(''))
  }
  return groups.join('-')
}
