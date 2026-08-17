#!/usr/bin/env node
/**
 * Smoke test for skill-asset CLI.
 *
 * Run from anywhere:
 *   node scripts/test.js
 *
 * Exit code: 0 if all pass, 1 if any fail.
 *
 * Tests cover:
 *   - --help works and lists all commands + new flags
 *   - Each command runs successfully on the project itself
 *   - --top N limits output
 *   - --json produces valid parseable JSON
 *   - Missing args exit with code 2
 *   - Frontmatter is correctly skipped (using a temporary fixture)
 */

'use strict';

const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const CLI = path.join(__dirname, 'skill-asset');

let pass = 0;
let fail = 0;
const failures = [];

function run(args, opts = {}) {
  const cwd = opts.cwd || ROOT;
  try {
    const out = execFileSync('node', [CLI, ...args], {
      cwd,
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    return { ok: true, stdout: out, stderr: '', code: 0 };
  } catch (e) {
    return {
      ok: false,
      stdout: (e.stdout || '').toString(),
      stderr: (e.stderr || '').toString(),
      code: typeof e.status === 'number' ? e.status : -1,
    };
  }
}

function check(label, condition, detail) {
  if (condition) {
    console.log(`  ✓ ${label}`);
    pass++;
  } else {
    console.log(`  ✗ ${label}`);
    if (detail) console.log(`    ${detail.split('\n').slice(0, 5).join('\n    ')}`);
    failures.push(label);
    fail++;
  }
}

console.log('=== skill-asset smoke test ===\n');

// --- Test 1: --help ---
console.log('[1] --help');
{
  const r = run(['--help']);
  check('exits 0', r.ok);
  check('mentions where', /\bwhere\b/.test(r.stdout));
  check('mentions related', /\brelated\b/.test(r.stdout));
  check('mentions group', /\bgroup\b/.test(r.stdout));
  check('mentions --top', r.stdout.includes('--top'));
  check('mentions --json', r.stdout.includes('--json'));
}

// --- Test 2: where command works ---
console.log('\n[2] where command');
{
  const r = run(['where', 'Task', 'Closure']);
  check('exits 0', r.ok, r.stderr);
  check('finds Task Closure section', r.stdout.includes('Task Closure'));
}

// --- Test 3: related works ---
console.log('\n[3] related');
{
  const r = run(['related', 'thin shell']);
  check('exits 0', r.ok, r.stderr);
  check('reports Found / No', /Found \d+ related|No related sections/.test(r.stdout));
}

// --- Test 4: group works ---
console.log('\n[4] group');
{
  const r = run(['group']);
  check('exits 0', r.ok, r.stderr);
  check('produces output', r.stdout.length > 0);
}

// --- Test 5: --top N limits output ---
console.log('\n[5] --top limits output');
{
  const r = run(['where', 'Task', '--top', '1']);
  check('exits 0', r.ok, r.stderr);
  const matches = (r.stdout.match(/-> merge into|-> alternative/g) || []).length;
  check(`--top 1 returns ≤1 result (got ${matches})`, matches <= 1);
}

// --- Test 6: --json produces valid JSON ---
console.log('\n[6] --json output');
{
  const r = run(['where', 'Task', '--json', '--top', '2']);
  check('exits 0', r.ok, r.stderr);
  let parsed;
  try {
    parsed = JSON.parse(r.stdout);
    check('output is valid JSON', true);
  } catch (e) {
    check('output is valid JSON', false, e.message);
  }
  if (parsed) {
    check('JSON has command field', parsed.command === 'where');
    check('JSON has results array', Array.isArray(parsed.results));
    check('JSON respects --top', parsed.results.length <= 2);
  }
}

// --- Test 7: missing args → exit 2 ---
console.log('\n[7] argument errors');
{
  const r = run(['where']);  // no keywords
  check('missing keywords exits 2', !r.ok && r.code === 2);

  const r2 = run(['unknown-command']);
  check('unknown command exits 2', !r2.ok && r2.code === 2);

  const r3 = run(['where', 'foo', '--top', 'abc']);
  check('invalid --top exits 2', !r3.ok && r3.code === 2);
}

// --- Test 8: frontmatter is skipped ---
console.log('\n[8] frontmatter handling');
{
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'skill-asset-test-'));
  try {
    const rulesDir = path.join(tmpDir, 'rules');
    fs.mkdirSync(rulesDir);
    fs.writeFileSync(path.join(rulesDir, 'fm.md'), '---\nstatus: active\nlast_validated: 2026-05-08\n---\n\n## RealHeadingXyz\n\nContent about UniqueKeyword42.\n');

    const r = run(['where', 'UniqueKeyword42'], { cwd: tmpDir });
    check('exits 0 with frontmatter file', r.ok, r.stderr);
    check('finds heading after frontmatter', r.stdout.includes('RealHeadingXyz'));
    check('reports correct line number (≥5, after frontmatter)', /\(L([5-9]|\d{2,})\)/.test(r.stdout));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
}

// --- Test 10: CJK tokenization (group works on Chinese headings) ---
console.log('\n[10] CJK tokenization');
{
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'skill-asset-test-cjk-'));
  try {
    const refsDir = path.join(tmpDir, 'references');
    fs.mkdirSync(refsDir);
    // Two files share "事件" and "管理" after segmenter splits them.
    // Without segmenter, each whole Chinese heading would be one token.
    fs.writeFileSync(path.join(refsDir, 'a.md'), '## 事件管理系统\n\nContent.\n');
    fs.writeFileSync(path.join(refsDir, 'b.md'), '## 事件管理工具\n\nContent.\n');
    fs.writeFileSync(path.join(refsDir, 'c.md'), '## 完全不相关的标题\n\nUnrelated.\n');

    const r = run(['group'], { cwd: tmpDir });
    check('CJK group exits 0', r.ok, r.stderr);
    check('CJK group finds 事件/管理 cluster (proves segmenter works)', r.stdout.includes('事件') && r.stdout.includes('管理'));
    check('CJK group reports finding', /Found \d+ potential/.test(r.stdout));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
}

// --- Test 11: group output includes false-positive disclaimer ---
console.log('\n[11] group includes heuristic disclaimer');
{
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'skill-asset-test-disclaimer-'));
  try {
    const refsDir = path.join(tmpDir, 'references');
    fs.mkdirSync(refsDir);
    // Need 2+ shared tokens to trigger grouping → triggers disclaimer footer
    fs.writeFileSync(path.join(refsDir, 'a.md'), '## Foo Bar Baz\n\nContent.\n');
    fs.writeFileSync(path.join(refsDir, 'b.md'), '## Foo Bar Qux\n\nContent.\n');

    const r = run(['group'], { cwd: tmpDir });
    check('exits 0', r.ok, r.stderr);
    check('group is reported', /Found \d+ potential/.test(r.stdout));
    check('output mentions heuristic / not confirmed duplicates', /heuristic|not confirmed/i.test(r.stdout));
    check('output mentions intentional clusters', /intentional/i.test(r.stdout));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
}

// --- Test 9: BOM is stripped ---
console.log('\n[9] BOM handling');
{
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'skill-asset-test-bom-'));
  try {
    const rulesDir = path.join(tmpDir, 'rules');
    fs.mkdirSync(rulesDir);
    // Write file with BOM prefix
    fs.writeFileSync(path.join(rulesDir, 'bom.md'), '﻿## BomHeadingZzz\n\nContent about BomKeyword99.\n');

    const r = run(['where', 'BomKeyword99'], { cwd: tmpDir });
    check('exits 0 with BOM file', r.ok, r.stderr);
    check('finds heading despite BOM', r.stdout.includes('BomHeadingZzz'));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
}

// --- Summary ---
console.log('\n=== Results ===');
if (fail === 0) {
  console.log(`✅ All ${pass} tests passed`);
  process.exit(0);
} else {
  console.log(`❌ ${fail} of ${pass + fail} tests failed:`);
  for (const f of failures) console.log(`   - ${f}`);
  process.exit(1);
}
