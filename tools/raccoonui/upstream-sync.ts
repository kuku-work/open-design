#!/usr/bin/env node
/**
 * RaccoonUI — Daily upstream AUTO-SYNC orchestrator
 *
 * Schedule: cron `0 6 * * *` (Asia/Taipei) via slack-bot/jobs.json shellPipeline.
 * Run with: `node --experimental-strip-types tools/raccoonui/upstream-sync.ts`
 *   (Node 24 native TS stripping — no tsx needed; TS-first per AGENTS.md.)
 *
 * What it does, in order:
 *   1. Preflight — refuse to run unless on `dev`, working tree clean, daemon not running.
 *   2. git fetch upstream; compute commits ahead.
 *   3. Analyze the delta: auto-flag surfaces, suspicious diff content, MAJOR dep bumps,
 *      and a merge-tree dry-run for textual conflict scope.
 *   4. GATE — auto-merge is eligible ONLY when ALL hold:
 *        - zero textual conflicts
 *        - no BLOCKING diff content in fork-executed source (embedded secret / private key /
 *          fetch to an un-allowlisted host). child_process/spawn is only SURFACED for a human
 *          spot-check, never blocked — it is normal monorepo code; docs/CI yaml/.github are
 *          not scanned at all (they were a 100% false-positive farm).
 *        - no major web-framework / native dep bump (express, path-to-regexp, next,
 *          react, electron, better-sqlite3) — the express-4→5 class of landmine that
 *          passes typecheck but breaks at runtime.
 *      Otherwise: write a sync log, post a 🚨 "needs human decision" line, do NOT merge.
 *   5. Merge (--no-commit) → caller-graph health check on fork patches (the silent-breakage
 *      guard: upstream rewrites a region, git takes upstream's copy, a fork callsite vanishes
 *      with no conflict). If a fork invariant is gone → abort + escalate.
 *   6. Commit merge → normalize line endings to LF (defensive) → pnpm install.
 *   7. TDD: pnpm typecheck + pnpm guard.   BDD: raccoonui protocol e2e (live daemon).
 *   8. All green → ff `main` to the merge commit, push `dev` + `main`.
 *      Any failure → hard-reset `dev` to the pre-merge SHA (rollback) + escalate.
 *
 * Escalation channel: stdout. The cron `delivery.to` is #design-engineering (C0AN3U2G49J),
 * so every status line — success or 🚨 — lands there. ALWAYS exits 0; status is the icon,
 * never a crashed cron job. The single exception (preflight dirty/wrong-branch) also exits 0.
 *
 * Zero external deps: node built-ins + git + pnpm only (matches upstream-audit.mjs).
 */

import { spawnSync } from 'node:child_process';
import { connect } from 'node:net';
import { mkdirSync, writeFileSync, readFileSync, readdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const FORK_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const AUDIT_DIR = resolve(FORK_ROOT, 'audit-logs');
// Runtime bookkeeping (gitignored, fork rule #2: .raccoonui/ holds runtime data).
const RUNTIME_DIR = resolve(FORK_ROOT, '.raccoonui');
const SKIP_STREAK_FILE = resolve(RUNTIME_DIR, 'sync-skip-streak');
// One skip is correct. A skip EVERY day is an outage wearing a skip's clothes: the
// 2026-08-30 sync found 5 consecutive daemon-running skips and 67 unsynced commits,
// every run exit 0 and nothing louder than a shrug. Escalate on the streak.
const SKIP_STREAK_ALERT = 3;

// Local-date label (toISOString is UTC and can drift the day at 06:00 TPE).
const TODAY = (() => {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
})();

const WORK_BRANCH = 'dev';
const RELEASE_BRANCH = 'main';
const DAEMON_PORT = 17456; // raccoonui daemon; if listening, the tool is in use → skip.

// --dry-run: preflight + fetch + analyze + gate decision, then stop before ANY mutation.
// Lets a human (or this validation) see what the daily run would do without merging/pushing.
const DRY_RUN = process.argv.includes('--dry-run');

// Major deps whose version bump = manual-review red flag (runtime-breaking class that
// typecheck cannot see: routers, web framework, native bindings).
const MAJOR_DEPS = [
  'express',
  'path-to-regexp',
  'next',
  'react',
  'react-dom',
  'electron',
  'better-sqlite3',
];

// Per-file fork invariants. Each MUST still match after the merge, else a fork patch was
// silently dropped by an upstream rewrite. Anchored on the live caller-graph, not markers.
const FORK_INVARIANTS: Array<{ file: string; rx: RegExp; desc: string }> = [
  { file: 'apps/web/src/App.tsx', rx: /pickDefaultDesignSystemId/, desc: 'picker default = raccoonai' },
  { file: 'apps/daemon/src/server.ts', rx: /\/api\/raccoonui\//, desc: 'raccoonui daemon namespace' },
  { file: 'apps/daemon/src/server.ts', rx: /\*splat\/retag-anchors/, desc: 'retag-anchors express5-safe splat route' },
  { file: 'apps/daemon/src/routes/project/index.ts', rx: /writeProjectMetadata/, desc: 'project metadata sidecar hook' },
  { file: 'apps/web/src/components/FileViewer.tsx', rx: /handleRetagAnchors/, desc: 'FileViewer retag handler' },
  { file: 'apps/web/src/runtime/srcdoc.ts', rx: /annotateDeckSlideDivs/, desc: 'deck deep-div annotate' },
  { file: 'scripts/guard.ts', rx: /raccoonui/, desc: 'guard raccoonui allowlist' },
  { file: 'apps/web/src/index.css', rx: /raccoonui\.css/, desc: 'fork CSS import' },
];

// Suspicious diff content, two tiers, scanned ONLY on fork-executed source files
// (SCAN_SOURCE_RX minus SCAN_EXCLUDE_RX). Never on docs, CI yaml, or `.github/**` — this
// fork executes none of those, and the word "spawn"/"exec" in prose or shell config was a
// 100%-false-positive farm that wedged the daily auto-merge for 9 days (2026-06-25).
//
// BLOCK_RX = hard blockers (withhold auto-merge, escalate): an upstream commit that embeds a
// secret or phones home to an un-allowlisted host is a real supply-chain signal.
const BLOCK_RX: RegExp[] = [
  /^\+.*\b(fetch|axios|got|undici)\s*\(\s*['"`]https?:\/\/(?!localhost|127\.0\.0\.1|api\.anthropic\.com|api\.openai\.com|generativelanguage\.googleapis\.com)/im,
  /^\+.*[A-Za-z_]*[Aa][Pp][Ii][_-]?[Kk][Ee][Yy]\s*[:=]\s*['"`][A-Za-z0-9_\-]{16,}/m,
  /^\+.*BEGIN (RSA |OPENSSH )?PRIVATE KEY/m,
];

// FLAG_RX = non-blocking surface (logged for a human spot-check, never blocks alone):
// child_process is normal in a Node monorepo — postinstall builds local workspace targets,
// the daemon launches Chrome. A bare spawn/exec is not a reliable malice signal; the real
// exfil signals (BLOCK_RX) + caller-graph health + TDD + BDD are the safety net.
const FLAG_RX: RegExp[] = [
  /^\+.*\b(child_process|execSync|spawnSync|spawn|exec)\b/m,
];

// Only files this fork actually runs (at install or runtime) are worth scanning…
const SCAN_SOURCE_RX = /\.(ts|tsx|js|jsx|mjs|cjs|py|sh|ps1)$/;
// …and never CI/release machinery the fork does not execute, nor test fixtures (fake keys).
const SCAN_EXCLUDE_RX = /(^\.github\/|\.test\.|\.spec\.|(^|\/)tests?\/)/;

const AUTO_FLAG_PATH = [
  /^package\.json$/,
  /\/package\.json$/,
  /^pnpm-lock\.yaml$/,
  /^\.github\/workflows\//,
  /\.(pre|post)install\.(js|mjs|cjs|sh|ps1)$/i,
  /^\.npmrc$/,
  /^\.yarnrc/,
  /\.env(\..+)?$/,
];

// ── git / shell helpers ──────────────────────────────────────────

// Pin autocrlf=input on every git call: this is an LF repo, and on Windows a default
// autocrlf=true smudges checked-out files to CRLF, which then fails LF-only guard checks
// and CRLF-sensitive tests. input = commit normalizes to LF, checkout writes blob bytes.
function git(args: string[], opts: { timeout?: number; allowFail?: boolean } = {}): string {
  const r = spawnSync('git', ['-c', 'core.autocrlf=input', ...args], {
    cwd: FORK_ROOT,
    encoding: 'utf8',
    timeout: opts.timeout ?? 60_000,
    maxBuffer: 64 * 1024 * 1024,
  });
  if (r.error) {
    if (opts.allowFail) return '';
    throw new Error(`git ${args.join(' ')} error: ${r.error.message}`);
  }
  if (r.status !== 0) {
    if (opts.allowFail) return '';
    throw new Error(`git ${args.join(' ')} exit ${r.status}: ${(r.stderr || '').trim()}`);
  }
  return (r.stdout || '').trim();
}

// Run a pnpm/long command through a shell (Windows corepack shim + cron PATH parity).
function sh(cmd: string, timeoutMs: number): { ok: boolean; tail: string } {
  const r = spawnSync(cmd, {
    cwd: FORK_ROOT,
    encoding: 'utf8',
    timeout: timeoutMs,
    shell: true,
    maxBuffer: 64 * 1024 * 1024,
    env: { ...process.env, PYTHONUTF8: '1' },
  });
  const out = (r.stdout || '') + (r.stderr || '');
  const ok = !r.error && r.status === 0;
  return { ok, tail: out.split('\n').slice(-40).join('\n') };
}

function portOpen(port: number): Promise<boolean> {
  return new Promise((res) => {
    const s = connect({ host: '127.0.0.1', port });
    const done = (v: boolean) => { s.destroy(); res(v); };
    s.setTimeout(800);
    s.once('connect', () => done(true));
    s.once('timeout', () => done(false));
    s.once('error', () => done(false));
  });
}

// ── analysis ─────────────────────────────────────────────────────

function detectMajorDepBump(range: string): string[] {
  const lockDiff = git(['diff', range, '--', 'pnpm-lock.yaml'], { allowFail: true });
  if (!lockDiff) return [];
  const hits = new Set<string>();
  for (const dep of MAJOR_DEPS) {
    // pnpm lock entries look like `  express@5.0.0:` or `/express@4.18.2`. A removed (-) AND
    // added (+) major-different version for the same dep = a bump worth a human eye.
    const added = [...lockDiff.matchAll(new RegExp(`^\\+.*[\\/@]${dep}@(\\d+)\\.`, 'gm'))].map((m) => m[1]);
    const removed = [...lockDiff.matchAll(new RegExp(`^-.*[\\/@]${dep}@(\\d+)\\.`, 'gm'))].map((m) => m[1]);
    if (added.length && removed.length && added.some((a) => !removed.includes(a))) {
      hits.add(`${dep} (major ${[...new Set(removed)].join('/')} → ${[...new Set(added)].join('/')})`);
    }
  }
  return [...hits];
}

function scanSuspiciousContent(files: string[], range: string): { blocking: string[]; surfaced: string[] } {
  const blocking: string[] = [];
  const surfaced: string[] = [];
  for (const f of files) {
    if (!SCAN_SOURCE_RX.test(f) || SCAN_EXCLUDE_RX.test(f)) continue;
    const diff = git(['diff', range, '--', f], { allowFail: true });
    if (!diff) continue;
    if (BLOCK_RX.some((rx) => rx.test(diff))) blocking.push(f);
    else if (FLAG_RX.some((rx) => rx.test(diff))) surfaced.push(f);
  }
  return { blocking, surfaced };
}

// merge-tree --write-tree: exit 0 = clean auto-merge; non-zero = conflicts (lists files).
function mergeTreeConflicts(mergeBase: string): { clean: boolean; files: string[] } {
  const r = spawnSync(
    'git',
    ['-c', 'core.autocrlf=input', 'merge-tree', '--write-tree', `--merge-base=${mergeBase}`, WORK_BRANCH, `upstream/${RELEASE_BRANCH}`],
    { cwd: FORK_ROOT, encoding: 'utf8', timeout: 120_000, maxBuffer: 64 * 1024 * 1024 },
  );
  if (r.status === 0) return { clean: true, files: [] };
  const out = (r.stdout || '') + (r.stderr || '');
  // `--write-tree` conflict output: line 1 is the toplevel tree OID, then one
  // "<mode> <oid> <stage>\t<path>" row per conflicted index entry (stages 1/2/3).
  // (The old message-style regex never matched this format → "conflicts (0)" with no names.)
  const files = [...out.matchAll(/^[0-7]{6} [0-9a-f]{40} [123]\t(.+)$/gm)]
    .map((m) => m[1])
    .filter((v, i, a) => a.indexOf(v) === i);
  return { clean: false, files };
}

function callerGraphHealth(): string[] {
  const problems: string[] = [];
  for (const inv of FORK_INVARIANTS) {
    const body = git(['show', `HEAD:${inv.file}`], { allowFail: true });
    if (!body) { problems.push(`${inv.file}: file missing`); continue; }
    if (!inv.rx.test(body)) problems.push(`${inv.file}: lost "${inv.desc}"`);
  }
  // Express 5 safety: no bare `*` wildcard route may exist (path-to-regexp v8 rejects it).
  const server = git(['show', `HEAD:apps/daemon/src/server.ts`], { allowFail: true });
  if (server && /app\.(get|post|put|delete|patch)\(\s*['"`][^'"`]*\/\*['"`/]/.test(server) &&
      !/\*splat/.test(server.match(/app\.\w+\(\s*['"`][^'"`]*\/\*['"`/][^\n]*/)?.[0] ?? '')) {
    problems.push('server.ts: bare "*" route reintroduced (express5 path-to-regexp v8 will throw)');
  }
  return problems;
}

// Defensive LF normalization: if any tracked file landed CRLF in the working tree (Windows
// autocrlf), guard/e2e on LF-only assertions will fail spuriously. Rewrite them to LF.
function normalizeLineEndings(): number {
  const eol = git(['ls-files', '--eol'], { allowFail: true });
  const crlf = eol.split('\n').filter((l) => l.includes('w/crlf')).map((l) => l.split('\t').pop()!).filter(Boolean);
  if (!crlf.length) return 0;
  // Rewrite in place. The previous `git rm -f` + `git checkout -- .` dance did NOT restore
  // the files: `git rm` drops the index entry too, so the checkout had nothing left to
  // re-materialize from and stranded them staged-deleted (hit for real, 2026-08-30 sync).
  for (const f of crlf) {
    const abs = resolve(FORK_ROOT, f);
    try {
      writeFileSync(abs, readFileSync(abs, 'utf8').replace(/\\r\\n/g, '\\n'), 'utf8');
    } catch {
      // File vanished mid-merge; the status checks downstream will surface it.
    }
  }
  return crlf.length;
}

// Upstream occasionally extracts an app OUT of the monorepo (e.g. #5565 removed
// apps/telemetry-worker). git drops the tracked files, but a stale node_modules/
// left in the working tree keeps the directory alive — and guard's
// check-cross-app-imports does readdirSync(apps/) then demands every dir carry a
// package.json, so the orphan residue throws ENOENT and reds an otherwise-clean
// merge. Any apps/<name> with zero tracked files is residue (a real app always
// has a tracked package.json); clean it before install/guard run.
function orphanAppDirs(): string[] {
  let names: string[];
  try {
    names = readdirSync(resolve(FORK_ROOT, 'apps'), { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => d.name);
  } catch {
    return [];
  }
  return names.filter((n) => !git(['ls-files', '--', `apps/${n}/`], { allowFail: true }));
}

function pruneOrphanAppDirs(orphans: string[]): void {
  for (const n of orphans) git(['clean', '-ffdx', '--', `apps/${n}/`], { allowFail: true });
}

// ── reporting ────────────────────────────────────────────────────

function writeLog(name: string, body: string): void {
  mkdirSync(AUDIT_DIR, { recursive: true });
  writeFileSync(resolve(AUDIT_DIR, name), body);
}

function emit(line: string): void {
  // Each console.log line is streamed to Slack #design-engineering by the cron runner.
  console.log(line);
}

function readSkipStreak(): number {
  try {
    return Number(readFileSync(SKIP_STREAK_FILE, 'utf8').trim()) || 0;
  } catch {
    return 0;
  }
}

function writeSkipStreak(n: number): void {
  try {
    mkdirSync(RUNTIME_DIR, { recursive: true });
    writeFileSync(SKIP_STREAK_FILE, String(n), 'utf8');
  } catch {
    // Bookkeeping must never be the thing that fails a sync run.
  }
}

// Every preflight bail routes through here, so a precondition stuck for days stops
// reading like a routine skip and starts reading like the outage it actually is.
function skip(reason: string): void {
  const streak = readSkipStreak() + 1;
  writeSkipStreak(streak);
  if (streak >= SKIP_STREAK_ALERT) {
    emit(
      `🚨 *Upstream Sync ${TODAY}* — skipped ${streak} runs in a row: ${reason} Sync is effectively OFF.` +
        ' Clear the precondition, or run the sync by hand: node --experimental-strip-types tools/raccoonui/upstream-sync.ts',
    );
    return;
  }
  emit(`⏭️ *Upstream Sync ${TODAY}* — skipped: ${reason}`);
}

// The tool is normally open at 06:00, and skipping on that is exactly what let
// the fork drift 67 commits behind (five consecutive daemon-running skips,
// 2026-08-30). Operator's call: shut it down and sync anyway -- they relaunch by
// hand when they next need it. Shut down through `tools-dev stop`, the same path
// start.ps1's own finally block uses, so the supervisor tears down daemon + web
// + desktop together and start.ps1's watchdog exits cleanly instead of leaving
// the orphan chain a bare port-kill would.
async function stopRunningDaemon(): Promise<boolean> {
  emit(`🛑 *Upstream Sync ${TODAY}* — RaccoonUI 開著，先關掉它再同步（需要時請自己重開）。`);
  sh('pnpm tools-dev stop', 60_000);
  // Trust the port, not the command's exit code: `stop` reports success for
  // apps it did not start, and the only thing that matters is the port going
  // quiet before git touches the working tree.
  let released = false;
  for (let i = 0; i < 20; i++) {
    if (!(await portOpen(DAEMON_PORT))) { released = true; break; }
    await new Promise((r) => setTimeout(r, 1_000));
  }
  if (!released) return false;

  const pruned = pruneLauncherRemnants();
  if (pruned) emit(`   cleaned up ${pruned} orphaned launcher process(es).`);
  return true;
}

// Shutting the tool down leaves two kinds of debris, both measured on
// 2026-08-30 and both harmless once but not once per day, which is what this
// becomes now that the sync closes the tool every morning:
//
//   1. the `tools-dev run` supervisor. `tools-dev stop` frees the ports but
//      not the supervisor, and start.ps1 has the same hole -- it kills the
//      pnpm.cmd wrapper it spawned, two links up the chain from the node
//      supervisor.
//   2. the `cmd /c start.cmd` shell. start.cmd ends in `pause`, so once pwsh
//      exits the shell sits forever on "Press any key to close". The box had
//      one of these dated 2026-08-25 still waiting.
//
// Every match requires this fork's path, so another checkout is never touched.
// Case 2 additionally requires the shell to have no live pwsh child: that is
// the launcher's actual work, and while it runs the shell must be left alone.
// Testing for "no children at all" does not work -- every console owns a
// conhost.exe, so that test never fires (measured, 2026-08-30).
function pruneLauncherRemnants(): number {
  if (process.platform !== 'win32') return 0;
  // Single-quoted in PowerShell on purpose: PowerShell does not treat a
  // backslash as an escape, so JSON.stringify's doubled separators would turn
  // the path into a pattern that matches nothing at all.
  const psRoot = `'${FORK_ROOT.replace(/'/g, "''")}'`;
  const ps = [
    `$root = ${psRoot};`,
    // Name + entrypoint filename + this fork's path, all three. A looser
    // match on the string 'tools-dev' alone is actively dangerous: measured
    // 2026-08-30, it also selected three bash.exe and one powershell.exe that
    // merely MENTIONED tools-dev on their command line -- the very shells
    // driving this repo. A daily Stop-Process over that set would kill the
    // operator's own tooling every morning.
    "$sup = @(Get-CimInstance Win32_Process -Filter \"Name = 'node.exe'\" | Where-Object {",
    "  $_.CommandLine -like '*tools-dev.mjs*' -and $_.CommandLine -like ('*' + $root + '*')",
    '});',
    '$all = Get-CimInstance Win32_Process;',
    // $c captures the outer pipeline item: a nested Where-Object rebinds $_,
    // so the childless test has to compare against $c, not $_.
    "$sh = @($all | Where-Object { $c = $_;",
    "  $c.Name -eq 'cmd.exe' -and $c.CommandLine -like '*start.cmd*'",
    "  -and $c.CommandLine -like ('*' + $root + '*')",
    "  -and -not ($all | Where-Object { $_.ParentProcessId -eq $c.ProcessId -and $_.Name -eq 'pwsh.exe' })",
    '});',
    '$p = @($sup) + @($sh);',
    'foreach ($x in $p) { Stop-Process -Id $x.ProcessId -Force -ErrorAction SilentlyContinue };',
    '$p.Count',
  ].join(' ');
  const r = sh(`powershell -NoProfile -Command "${ps.replace(/"/g, '\\"')}"`, 30_000);
  // Last line only: Stop-Process noise lands on the same merged tail.
  const n = Number((r.tail.trim().split('\n').pop() ?? '').trim());
  return Number.isFinite(n) ? n : 0;
}

// ── main ─────────────────────────────────────────────────────────

async function main(): Promise<void> {
  // 1) Preflight — never clobber a human mid-work.
  const branch = git(['rev-parse', '--abbrev-ref', 'HEAD'], { allowFail: true });
  if (branch !== WORK_BRANCH) {
    skip(`on \`${branch || '?'}\`, not \`${WORK_BRANCH}\`. No action.`);
    return;
  }
  // Only TRACKED modifications block: a merge/checkout can clobber WIP edits, but stray
  // untracked files (logs, scratch, an uncommitted tool) are not the cron's concern.
  const dirty = git(['status', '--porcelain', '--untracked-files=no'], { allowFail: true });
  if (dirty) {
    skip(`${dirty.split('\n').length} tracked file(s) modified. Manual state, leaving untouched.`);
    return;
  }
  if (await portOpen(DAEMON_PORT)) {
    if (!(await stopRunningDaemon())) {
      skip(`daemon still listening on :${DAEMON_PORT} 20s after \`tools-dev stop\`. Not forcing it.`);
      return;
    }
  }

  // Preflight passed: this run does real work, so the skip streak is over.
  writeSkipStreak(0);

  // 2) Fetch + delta.
  if (!git(['remote'], { allowFail: true }).split('\n').includes('upstream')) {
    emit(`🚨 *Upstream Sync ${TODAY}* — 'upstream' remote not configured. Manual fix required.`);
    return;
  }
  // Fetch ONLY the release branch we actually merge from. The default refspec pulls all
  // ~2.2k upstream branches, and a concurrent fetch racing on any one of them fails the
  // whole command ("incorrect old value provided") -- aborting a sync that had nothing
  // wrong with it. RACCOONUI-PATCH: narrow upstream fetch to the merge source -- 2026-09-01
  git(['fetch', 'upstream', `+refs/heads/${RELEASE_BRANCH}:refs/remotes/upstream/${RELEASE_BRANCH}`, '--quiet'], {
    timeout: 180_000,
  });
  const mergeBase = git(['merge-base', WORK_BRANCH, `upstream/${RELEASE_BRANCH}`]);
  const tip = git(['rev-parse', `upstream/${RELEASE_BRANCH}`]);
  const range = `${mergeBase}..upstream/${RELEASE_BRANCH}`;
  const ahead = Number(git(['rev-list', '--count', range]) || '0');
  if (ahead === 0) {
    emit(`🟢 *Upstream Sync ${TODAY}* — 0 commits ahead. Already current.`);
    return;
  }

  // 3) Analyze.
  const files = git(['diff', '--name-only', range], { allowFail: true }).split('\n').filter(Boolean);
  const flagged = files.filter((f) => AUTO_FLAG_PATH.some((rx) => rx.test(f)));
  // Scan only fork-executed source (the function re-filters defensively); cap git-diff calls.
  const sourceForScan = files.filter((f) => SCAN_SOURCE_RX.test(f) && !SCAN_EXCLUDE_RX.test(f));
  const { blocking: suspiciousBlocking, surfaced: childProcSurfaced } = scanSuspiciousContent(sourceForScan.slice(0, 1200), range);
  const depBumps = detectMajorDepBump(range);
  const conflicts = mergeTreeConflicts(mergeBase);
  const forkTouched = [...new Set(FORK_INVARIANTS.map((i) => i.file))].filter((f) => files.includes(f));

  const blockers: string[] = [];
  if (!conflicts.clean) blockers.push(`textual conflicts (${conflicts.files.length}): ${conflicts.files.slice(0, 6).join(', ')}`);
  if (depBumps.length) blockers.push(`major dep bump: ${depBumps.join('; ')}`);
  if (suspiciousBlocking.length) blockers.push(`suspicious diff content: ${suspiciousBlocking.slice(0, 6).join(', ')}`);

  const shortBase = mergeBase.slice(0, 9);
  const shortTip = tip.slice(0, 9);

  if (DRY_RUN) {
    const verdict = blockers.length
      ? `🚨 would ESCALATE (no merge):\n${blockers.map((b) => `  • ${b}`).join('\n')}`
      : `✅ would AUTO-MERGE → caller-graph health → TDD (typecheck+guard) → BDD (protocol e2e) → ff main + push`;
    const dryOrphans = orphanAppDirs();
    emit([
      `🔎 *Upstream Sync ${TODAY}* — DRY RUN — ${ahead} commits ahead (\`${shortBase}..${shortTip}\`)`,
      `auto-flagged: ${flagged.length} | suspicious(block): ${suspiciousBlocking.length} | child_proc(flag): ${childProcSurfaced.length} | dep-bumps: ${depBumps.length} | conflicts: ${conflicts.clean ? 0 : conflicts.files.length}`,
      childProcSurfaced.length ? `child_process surfaces (non-blocking spot-check): ${childProcSurfaced.slice(0, 8).join(', ')}` : 'child_process surfaces: (none)',
      forkTouched.length ? `fork-patch files in delta: ${forkTouched.join(', ')}` : 'fork-patch files in delta: (none)',
      dryOrphans.length ? `orphan app dirs to prune: ${dryOrphans.join(', ')}` : 'orphan app dirs: (none)',
      verdict,
    ].join('\n'));
    return;
  }

  // 4) GATE.
  if (blockers.length) {
    const log = [
      `# Upstream Sync — ${TODAY} (BLOCKED, needs human decision)`,
      ``,
      `Range: \`${shortBase}..${shortTip}\` (${ahead} commits)`,
      ``,
      `## Why auto-merge was withheld`,
      ...blockers.map((b) => `- ${b}`),
      ``,
      `## Surfaces`,
      `- auto-flagged paths: ${flagged.length ? flagged.join(', ') : '(none)'}`,
      `- fork-patch files touched: ${forkTouched.length ? forkTouched.join(', ') : '(none)'}`,
      ``,
      `## Next step (manual)`,
      '```bash',
      `cd ${FORK_ROOT}`,
      `git fetch upstream && git merge upstream/${RELEASE_BRANCH}   # resolve, then TDD/BDD before ff main`,
      '```',
      ``,
    ].join('\n');
    writeLog(`sync-${TODAY}.md`, log);
    const lines = [
      `🚨 *Upstream Sync ${TODAY}* — ${ahead} commits ahead, **needs human decision** (not merged)`,
      ...blockers.map((b) => `  • ${b}`),
    ];
    if (forkTouched.length) lines.push(`  • fork-patch files in delta: ${forkTouched.join(', ')}`);
    lines.push(`📄 \`audit-logs/sync-${TODAY}.md\` — resolve, then merge + TDD/BDD manually.`);
    emit(lines.join('\n'));
    return;
  }

  // 5) Merge (no-commit) + caller-graph health.
  const preMerge = git(['rev-parse', 'HEAD']);
  const mergeRun = spawnSync('git', ['-c', 'core.autocrlf=input', 'merge', '--no-commit', '--no-ff', `upstream/${RELEASE_BRANCH}`], {
    cwd: FORK_ROOT, encoding: 'utf8', timeout: 120_000, maxBuffer: 64 * 1024 * 1024,
  });
  const unmerged = git(['diff', '--name-only', '--diff-filter=U'], { allowFail: true });
  if (mergeRun.status !== 0 || unmerged) {
    git(['merge', '--abort'], { allowFail: true });
    emit(`🚨 *Upstream Sync ${TODAY}* — merge-tree said clean but \`git merge\` conflicted (${unmerged.split('\n').filter(Boolean).length} files). Aborted. Manual review.`);
    return;
  }
  const health = callerGraphHealth();
  if (health.length) {
    git(['merge', '--abort'], { allowFail: true });
    const lines = [
      `🚨 *Upstream Sync ${TODAY}* — fork-patch caller-graph regression, merge aborted (not committed):`,
      ...health.map((p) => `  • ${p}`),
      `These survived a *clean* merge but lost their callsite — needs manual re-injection.`,
    ];
    writeLog(`sync-${TODAY}.md`, `# Upstream Sync — ${TODAY} (ABORTED: fork patch regression)\n\n${health.map((p) => `- ${p}`).join('\n')}\n`);
    emit(lines.join('\n'));
    return;
  }

  // 6) Commit + normalize + install.
  git(['commit', '-m', `[raccoonui] chore(merge): sync upstream/${RELEASE_BRANCH} ${shortBase}..${shortTip} (${ahead} commits)`]);
  const mergeCommit = git(['rev-parse', 'HEAD']);
  const normalized = normalizeLineEndings();
  const orphans = orphanAppDirs();
  if (orphans.length) {
    pruneOrphanAppDirs(orphans);
    emit(`🧹 *Upstream Sync ${TODAY}* — pruned ${orphans.length} orphan app dir(s) (stale residue after upstream extraction, no longer tracked): ${orphans.join(', ')}`);
  }

  const rollback = (why: string, detail: string) => {
    git(['checkout', WORK_BRANCH], { allowFail: true });
    git(['reset', '--hard', preMerge], { allowFail: true });
    writeLog(`sync-${TODAY}.md`, `# Upstream Sync — ${TODAY} (ROLLED BACK)\n\nRange: \`${shortBase}..${shortTip}\` (${ahead} commits)\nFailed at: ${why}\n\n\`\`\`\n${detail}\n\`\`\`\n`);
    emit([
      `🚨 *Upstream Sync ${TODAY}* — merged ${ahead} commits but **${why} failed**, rolled \`dev\` back to \`${preMerge.slice(0, 9)}\` (not pushed).`,
      `Last output:`,
      '```',
      detail,
      '```',
      `📄 \`audit-logs/sync-${TODAY}.md\` — fix locally, then re-run.`,
    ].join('\n'));
  };

  // On Windows a plain `pnpm install` fails in ways that are all cured by rebuilding the
  // tree, and none of which are worth telling apart: an existing node_modules entry that
  // cannot be replaced ("UNKNOWN: unknown error, open ...package.json"), or a postinstall
  // script running against a half-linked tree left by the previous failed install
  // (MODULE_NOT_FOUND). Retry once with --force rather than branching on the message.
  // RACCOONUI-PATCH: retry install with --force before rolling back — 2026-09-07
  let install = sh('pnpm install', 8 * 60_000);
  if (!install.ok) {
    emit(`⚠️ *Upstream Sync ${TODAY}* — pnpm install failed, retrying once with --force.`);
    install = sh('pnpm install --force', 15 * 60_000);
    if (!install.ok) return void rollback('pnpm install (retried with --force)', install.tail);
  }

  // 7) TDD + BDD.
  const typecheck = sh('pnpm typecheck', 8 * 60_000);
  if (!typecheck.ok) return void rollback('typecheck', typecheck.tail);
  const guard = sh('pnpm guard', 5 * 60_000);
  if (!guard.ok) return void rollback('guard', guard.tail);
  const e2e = sh('pnpm -C e2e run test:e2e:raccoonui-protocol', 8 * 60_000);
  if (!e2e.ok) return void rollback('protocol e2e (BDD)', e2e.tail);

  // 8) ff main + push.
  git(['checkout', RELEASE_BRANCH]);
  const ff = spawnSync('git', ['-c', 'core.autocrlf=input', 'merge', '--ff-only', WORK_BRANCH], {
    cwd: FORK_ROOT, encoding: 'utf8', timeout: 60_000,
  });
  if (ff.status !== 0) {
    git(['checkout', WORK_BRANCH], { allowFail: true });
    return void rollback('ff main (main diverged?)', (ff.stderr || ff.stdout || '').trim());
  }
  const pushDev = git(['push', 'origin', WORK_BRANCH], { allowFail: true, timeout: 120_000 });
  const pushMain = git(['push', 'origin', RELEASE_BRANCH], { allowFail: true, timeout: 120_000 });
  git(['checkout', WORK_BRANCH], { allowFail: true });

  // Push uses the ambient credential helper / GITHUB_TOKEN. If it failed, the local merge is
  // sound and on main — surface it loudly but don't roll back a validated build.
  const pushOkDev = git(['rev-parse', `origin/${WORK_BRANCH}`], { allowFail: true }) === mergeCommit;
  const pushOkMain = git(['rev-parse', `origin/${RELEASE_BRANCH}`], { allowFail: true }) === mergeCommit;

  writeLog(`sync-${TODAY}.md`, [
    `# Upstream Sync — ${TODAY} (SUCCESS)`,
    ``,
    `Range: \`${shortBase}..${shortTip}\` (${ahead} commits) → merge \`${mergeCommit.slice(0, 9)}\``,
    `TDD: typecheck ✅ guard ✅   BDD: protocol e2e ✅`,
    `LF-normalized files: ${normalized}`,
    `Pushed: dev=${pushOkDev ? '✅' : '❌'} main=${pushOkMain ? '✅' : '❌'}`,
    forkTouched.length ? `\nFork-patch files in delta (spot-check welcome): ${forkTouched.join(', ')}` : '',
    childProcSurfaced.length ? `child_process surfaces (non-blocking spot-check): ${childProcSurfaced.join(', ')}` : '',
    ``,
  ].join('\n'));

  if (pushOkDev && pushOkMain) {
    const lines = [
      `✅ *Upstream Sync ${TODAY}* — auto-synced **${ahead} commits** (\`${shortBase}..${shortTip}\`), TDD+BDD green, ff \`main\` + pushed.`,
    ];
    if (forkTouched.length) lines.push(`  • fork-patch files touched (spot-check welcome): ${forkTouched.join(', ')}`);
    if (childProcSurfaced.length) lines.push(`  • child_process surfaces (non-blocking spot-check): ${childProcSurfaced.slice(0, 8).join(', ')}`);
    emit(lines.join('\n'));
  } else {
    emit([
      `🚨 *Upstream Sync ${TODAY}* — merged + validated ${ahead} commits and ff \`main\` locally, but **push failed** (dev=${pushOkDev ? 'ok' : 'FAIL'}, main=${pushOkMain ? 'ok' : 'FAIL'}).`,
      `dev push: ${pushDev || '(no output / rejected)'}`,
      `main push: ${pushMain || '(no output / rejected)'}`,
      `Commit \`${mergeCommit.slice(0, 9)}\` is validated locally — just run \`git push origin dev main\`.`,
    ].join('\n'));
  }
}

main().catch((err) => {
  // Never crash the cron loop; convey failure via stdout icon.
  emit(`❌ *Upstream Sync ${TODAY}* — orchestrator error: ${err?.message ?? String(err)}`);
  process.exit(0);
});
