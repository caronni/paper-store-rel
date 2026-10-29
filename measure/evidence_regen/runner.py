"""Run the family table: one detached worktree per commit, fresh outputs, sha verdicts.

Every family runs in ``<work>/wt-<sha8>`` (``git worktree add --detach``),
with ``<work>/out/<family>`` as its output dir; the worktree is removed when
the last family on that commit is done (``keep_worktrees`` keeps them).  An
expected sha comes from the hash TSV (``--hashes``, columns sha256, bytes,
mtime, path) by archived path, else from the archived file on disk.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .families import EXTRA_TAGS, FAMILIES, Compare, Family

VERDICT_COLUMNS = ("family", "commit", "produced", "archived", "expected_sha256", "expected_from",
                   "got_sha256", "verdict", "note")
STEP_TIMEOUT_S = 1800


@dataclass(frozen=True)
class Verdict:
    family: str
    commit: str
    produced: str
    archived: str
    expected_sha256: str
    expected_from: str
    got_sha256: str
    verdict: str        # byte-identical | differs | not-produced | not-runnable | not-regenerable
    note: str

    def row(self) -> str:
        return "\t".join(str(getattr(self, c)).replace("\t", " ").replace("\n", " ")
                         for c in VERDICT_COLUMNS)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def load_hashes(tsv: Path | None) -> dict[str, str]:
    if tsv is None:
        return {}
    table: dict[str, str] = {}
    for line in tsv.read_text().splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 4:
            table[parts[3]] = parts[0]
    return table


GLOB_MAGIC = frozenset("*?[")


def archived_names_on_disk(archived_dir: Path, expect: tuple[str, ...]) -> set[str]:
    """The files under ``archived_dir`` (relative names) that ``expect`` may select.

    A literal expect list (no ``*?[``) is looked up name by name, so a family
    whose archived dir is a large live tree (``scratch/``) stats its few files
    instead of walking the tree; with any glob the dir is walked.  Both give
    the same selection once ``expect`` is applied.
    """
    if not archived_dir.is_dir():
        return set()
    if not any(GLOB_MAGIC & set(g) for g in expect):
        return {g for g in expect if (archived_dir / g).is_file()}
    return {str(p.relative_to(archived_dir)) for p in archived_dir.rglob("*") if p.is_file()}


def json_diff(a: Path, b: Path) -> str:
    """For two JSON files: the top-level keys whose values differ ('' otherwise)."""
    if a.suffix != ".json" or not b.is_file():
        return ""
    try:
        ja, jb = json.loads(a.read_text()), json.loads(b.read_text())
    except (ValueError, UnicodeDecodeError):
        return ""
    if not (isinstance(ja, dict) and isinstance(jb, dict)):
        return "JSON differs"
    keys = sorted(k for k in set(ja) | set(jb) if ja.get(k) != jb.get(k))
    return "JSON keys differ: " + ", ".join(f"{k} ({ja.get(k)!r} vs archived {jb.get(k)!r})"[:160] for k in keys)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def resolve(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")


def tag_name(repo: Path, tag: str, sha: str) -> str:
    day = git(repo, "show", "-s", "--format=%cd", "--date=format:%Y%m%d", sha)
    return f"evidence/{tag}-{day}@{sha[:8]}"


def make_tags(repo: Path, families: tuple[Family, ...] = FAMILIES) -> list[tuple[str, str, str]]:
    """Create (or confirm) the lightweight tags; return (name, sha, what)."""
    wanted: dict[str, tuple[str, str]] = {}
    for fam in families:
        if fam.commit and fam.tag:
            sha = resolve(repo, fam.commit)
            name = tag_name(repo, fam.tag, sha)
            what = wanted.get(name, (sha, ""))[1]
            wanted[name] = (sha, (what + ", " if what else "") + fam.id)
    for tag, ref, what in EXTRA_TAGS:
        sha = resolve(repo, ref)
        wanted[tag_name(repo, tag, sha)] = (sha, what)
    out = []
    for name, (sha, what) in sorted(wanted.items()):
        have = subprocess.run(["git", "-C", str(repo), "rev-parse", "-q", "--verify", f"refs/tags/{name}"],
                              capture_output=True, text=True).stdout.strip()
        if have and have != sha:
            raise SystemExit(f"tag {name} exists at {have}, wanted {sha}")
        if not have:
            git(repo, "tag", name, sha)
        out.append((name, sha, what))
    return out


class Runner:
    def __init__(self, repo: Path, tool: Path, root: Path, work: Path, python: Path,
                 hashes: dict[str, str], keep_worktrees: bool = False) -> None:
        self.repo, self.tool, self.root, self.work = repo, tool, root, work
        self.python, self.hashes, self.keep = python, hashes, keep_worktrees
        self.outs: dict[str, Path] = {}
        self.log = work / "run.log"

    # -- worktrees ----------------------------------------------------------
    def worktree(self, sha: str, patch: str | None) -> Path:
        wt = self.work / f"wt-{sha[:8]}{'-patched' if patch else ''}"
        if not wt.exists():
            git(self.repo, "worktree", "add", "--detach", str(wt), sha)
            if patch:
                subprocess.run(["git", "-C", str(wt), "apply", patch], check=True,
                               capture_output=True, text=True)
        return wt

    def drop_worktree(self, wt: Path) -> None:
        if not self.keep and wt.exists():
            git(self.repo, "worktree", "remove", "--force", str(wt))

    # -- steps ----------------------------------------------------------------
    def _subst(self, arg: str, wt: Path, out: Path) -> str:
        for fid, path in self.outs.items():
            arg = arg.replace(f"{{out:{fid}}}", str(path))
        return (arg.replace("{py}", str(self.python)).replace("{wt}", str(wt)).replace("{out}", str(out))
                .replace("{root}", str(self.root)).replace("{tool}", str(self.tool)))

    def run_steps(self, fam: Family, wt: Path, out: Path) -> str:
        """Run every step; return '' or the failures' tails (the first one stops a family without allow_fail)."""
        failures: list[str] = []
        env = dict(os.environ, PYTHONPATH=f"{wt / 'src'}{os.pathsep}{wt}")
        env.pop("PYTHONHOME", None)
        for step in fam.steps:
            args = [self._subst(a, wt, out) for a in step]
            with self.log.open("a") as log:
                log.write(f"[{fam.id}] $ {' '.join(args)}\n")
            if args[0] == "@counting":
                Path(args[2]).parent.mkdir(parents=True, exist_ok=True)
                Path(args[2]).write_bytes(bytes(i & 0xFF for i in range(int(args[1]))))
                continue
            if args[0] == "@mkdir":
                for d in args[1:]:
                    Path(d).mkdir(parents=True, exist_ok=True)
                continue
            if args[0] == "@copy":
                Path(args[2]).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(args[1], args[2])
                continue
            t0 = time.monotonic()
            proc = subprocess.run(args, cwd=wt, env=env, capture_output=True, text=True,
                                  timeout=STEP_TIMEOUT_S)
            with self.log.open("a") as log:
                log.write(proc.stdout[-4000:] + proc.stderr[-4000:]
                          + f"[{fam.id}] exit {proc.returncode} in {time.monotonic() - t0:.1f} s\n")
            if proc.returncode != 0:
                tail = (proc.stderr.strip() or proc.stdout.strip()).splitlines()[-1:] or ["(no output)"]
                failure = f"step {' '.join(step[:3])}… exit {proc.returncode}: {tail[0][:300]}"
                failures.append(failure)
                if not fam.allow_fail:
                    break
                with self.log.open("a") as log:
                    log.write(f"[{fam.id}] continuing after: {failure}\n")
        return " | ".join(failures)

    # -- verdicts ---------------------------------------------------------------
    def expected(self, archived: str) -> tuple[str, str]:
        if archived in self.hashes:
            return self.hashes[archived], "hash-tsv"
        path = self.root / archived
        if path.is_file():
            return sha256_file(path), "disk"
        return "", "none"

    def compare(self, fam: Family, sha: str, cmp: Compare, wt: Path, out: Path,
                failure: str) -> list[Verdict]:
        produced_dir = wt / cmp.produced[3:] if cmp.produced.startswith("wt:") else out / cmp.produced
        archived_dir = self.root / cmp.archived
        names = archived_names_on_disk(archived_dir, cmp.expect)
        names |= {a[len(cmp.archived) + 1:] for a in self.hashes if a.startswith(cmp.archived + "/")}
        wanted = sorted(n for n in names if any(fnmatch.fnmatch(n, g) and ("/" in g) == ("/" in n)
                                                for g in cmp.expect))
        rows = []
        for rel in wanted:
            archived = f"{cmp.archived}/{rel}"
            exp, src = self.expected(archived)
            got_path = produced_dir / rel
            known = any(rel.startswith(p) for p in fam.expect_fail)
            if not got_path.is_file():
                verdict = "not-runnable" if failure or known else "not-produced"
                note = "; ".join(t for t in (("expected: " + fam.reason) if known else "", failure) if t)
                rows.append(Verdict(fam.id, sha[:8], "", archived, exp, src, "", verdict, note))
                continue
            got = sha256_file(got_path)
            verdict = "byte-identical" if got == exp else "differs"
            note = ""
            if verdict == "differs":
                note = "; ".join([json_diff(got_path, self.root / archived)]
                                 + [t for g, t in fam.notes if fnmatch.fnmatch(rel, g)]).strip("; ")
            rows.append(Verdict(fam.id, sha[:8], str(got_path.relative_to(wt if cmp.produced.startswith("wt:")
                                                                           else out)),
                                archived, exp, src, got, verdict, note))
        return rows

    def run(self, families: tuple[Family, ...]) -> list[Verdict]:
        self.work.mkdir(parents=True, exist_ok=True)
        ids = {f.id for f in families}
        for prior in sorted((self.work / "out").glob("*")):   # an earlier run's outputs satisfy `needs`
            if prior.is_dir() and prior.name not in ids:
                self.outs[prior.name] = prior
        verdicts: list[Verdict] = []
        order = list(families)
        shas = {f.id: resolve(self.repo, f.commit) for f in order if f.commit}
        last_use = {}
        for i, f in enumerate(order):
            if f.commit:
                last_use[(shas[f.id], f.patch)] = i
        for i, fam in enumerate(order):
            if fam.commit is None:
                verdicts.append(Verdict(fam.id, "", "", fam.title, "", "", "", "not-regenerable", fam.reason))
                continue
            sha = shas[fam.id]
            missing = [n for n in fam.needs if n not in self.outs]
            out = self.work / "out" / fam.id
            if out.exists():
                shutil.rmtree(out)
            out.mkdir(parents=True)
            self.outs[fam.id] = out
            t0 = time.monotonic()
            if missing:
                failure = f"needs {', '.join(missing)} run first"
                wt = self.work / "unused"
            else:
                wt = self.worktree(sha, fam.patch)
                run_out = wt / fam.out_in_worktree if fam.out_in_worktree else out
                if fam.out_in_worktree:
                    shutil.rmtree(run_out, ignore_errors=True)
                    run_out.parent.mkdir(parents=True, exist_ok=True)
                try:
                    failure = self.run_steps(fam, wt, run_out)
                except subprocess.TimeoutExpired as exc:
                    failure = f"timeout after {exc.timeout} s"
                if fam.out_in_worktree and run_out.exists():
                    shutil.rmtree(out)
                    shutil.copytree(run_out, out)
            for cmp in fam.compare:
                verdicts.extend(self.compare(fam, sha, cmp, wt, out, failure))
            with self.log.open("a") as log:
                log.write(f"[{fam.id}] done in {time.monotonic() - t0:.1f} s\n")
            if last_use.get((sha, fam.patch)) == i and not missing:
                self.drop_worktree(wt)
        return verdicts


def write_verdicts(path: Path, verdicts: list[Verdict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\t".join(VERDICT_COLUMNS) + "\n" + "".join(v.row() + "\n" for v in verdicts))
