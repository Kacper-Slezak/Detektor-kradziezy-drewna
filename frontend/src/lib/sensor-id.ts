// Sensor ID = DevEUI: 16 hex characters. Labels often print it with spaces, dashes or colons.

export function normalizeSensorId(input: string): string {
  return input.replace(/[\s:-]/g, '').toUpperCase()
}

export function isValidSensorId(id: string): boolean {
  return /^[0-9A-F]{16}$/.test(id)
}
