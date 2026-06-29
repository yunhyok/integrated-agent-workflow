export const serverIdentity = {
  name: "integrated-agent-workflow",
  version: "0.1.0"
} as const;

if (process.argv.includes("--doctor-smoke")) {
  console.log(`${serverIdentity.name} ${serverIdentity.version} doctor smoke ok`);
}
