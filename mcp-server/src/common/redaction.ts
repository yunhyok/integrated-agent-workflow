const SECRET_PATTERNS: RegExp[] = [
  /\b(sk-[A-Za-z0-9_-]{4,})\b/g,
  /\b([A-Za-z0-9_]*TOKEN[A-Za-z0-9_]*\s*=\s*)([^\s]+)/gi,
  /\b([A-Za-z0-9_]*KEY[A-Za-z0-9_]*\s*=\s*)([^\s]+)/gi,
  /\b(password\s*[:=]\s*)([^\s]+)/gi
];

export function redactSecrets(value: string): string {
  let output = value;
  output = output.replace(SECRET_PATTERNS[0], "[REDACTED]");
  for (const pattern of SECRET_PATTERNS.slice(1)) {
    output = output.replace(pattern, "$1[REDACTED]");
  }
  return output;
}
