"""Offline dependency bootstrap for the sandboxed environment.

PyPI.org direct access is blocked and pip's own download-save step is denied by
the sandbox, but the Tsinghua mirror is reachable from plain Python. This
script downloads wheels with urllib into ./wheels and lets pip install purely
offline (--no-index --find-links) into backend/pylib. Missing transitive
dependencies are resolved iteratively from pip's error output.

Usage:
    python tools/bootstrap_deps.py [package ...]
If no packages are given, backend/requirements.txt is used.
"""

import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent
WHEELS = ROOT / "wheels"
TARGET = ROOT / "backend" / "pylib"
MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
REQ_FILE = ROOT / "backend" / "requirements.txt"

# Tag 优先级：第 0 组与 cp313 兼容（等优先，组内取最新版本），低版本 tag 仅作回退。
# abi3 轮子向后兼容（如 cp36-abi3 可装于 3.13），归入第 0 组；
# py3-none-win_amd64 等平台轮子（如 pypdfium2）同样归入第 0 组。
_TAG_GROUPS = [
    [
        re.compile(r"cp313-cp313-win_amd64"),
        re.compile(r"cp313-abi3-win_amd64"),
        re.compile(r"cp3\d+-abi3-win_amd64"),
        re.compile(r"py3-none-win_amd64"),
        re.compile(r"py2\.py3-none-win_amd64"),
        re.compile(r"py3-none-any"),
        re.compile(r"py2\.py3-none-any"),
    ],
    [re.compile(r"cp312-cp312-win_amd64")],
    [re.compile(r"cp311-cp311-win_amd64")],
    [re.compile(r"cp310-cp310-win_amd64")],
    [re.compile(r"cp39-cp39-win_amd64")],
]


def _group(name: str) -> int:
    for i, patterns in enumerate(_TAG_GROUPS):
        for pat in patterns:
            if pat.search(name):
                return i
    return len(_TAG_GROUPS)  # sdist 等最低优先级


def _is_wheel(link: str) -> int:
    return 1 if link.rsplit("/", 1)[-1].endswith(".whl") else 0


def _is_win(link: str) -> int:
    return 1 if "win_amd64" in link else 0


# 已知需要锁定的版本（兼容性原因，不允许解析到最新）
_VERSION_PINS = {
    # bcrypt 使用原生 API（不依赖 passlib），版本需与 requirements.txt 一致
    "bcrypt": "5.0.0",
    "httpx": "0.28.1",  # langchain-core 要求 httpx<1.0，镜像最新是 1.0.dev1
}


def fetch_index(package: str) -> list[str]:
    url = f"{MIRROR}/{package}/"
    req = urllib.request.Request(url, headers={"User-Agent": "dsh-bootstrap/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    links = re.findall(r'href="([^"]+)"', html)
    # 去掉 #sha256 片段，并只保留包文件链接
    clean = [l.split("#")[0] for l in links]
    return [l for l in clean if l.rsplit("/", 1)[-1].endswith((".whl", ".tar.gz", ".zip"))]


def _version_key(name: str):
    """从文件名提取可比版本元组（稳定版优先、版本号降序）。"""
    stem = name.rsplit("/", 1)[-1]
    m = re.search(r"-(\d+(?:\.\d+)*(?:(?:a|b|rc|post|dev)\d*)?(?:\.post\d+)?(?:\.dev\d+)?)-", stem + "-")
    if not m:
        return (1, (0,))
    try:
        from packaging.version import Version
        v = Version(m.group(1))
        return (0 if v.is_prerelease else 1, v.release)
    except Exception:
        parts = re.findall(r"\d+", m.group(1))
        return (1, tuple(int(p) for p in parts))


def _stable_first(link: str):
    # 排序优先级：稳定版 > 预发布；版本新 > 旧；win 平台 > 其他平台；轮子 > 源码包
    return (*_version_key(link), _is_win(link), _is_wheel(link))


def _candidates(package: str, links: list[str], count: int) -> list[str]:
    """挑选候选文件：锁定版本优先；同组内稳定版优先、取最新；再补充次优组。"""
    pin = _VERSION_PINS.get(package)
    if pin:
        pinned = [l for l in links if f"-{pin}-" in l or f"-{pin}." in l]
        if pinned:
            # win 平台优先，其次稳定版/最新
            return sorted(pinned, key=_stable_first, reverse=True)[:4]
    ordered = sorted(links, key=lambda l: (_group(l), *_stable_first(l)))
    picked: list[str] = []
    for group in sorted({_group(l) for l in ordered}):
        in_group = [l for l in ordered if _group(l) == group]
        # 稳定版优先、同优先级取最新版本（降序取前 count 个）
        best_in_group = sorted(in_group, key=_stable_first, reverse=True)[:count]
        picked.extend(best_in_group)
        if len(picked) >= count:
            break
    return picked[:count]


def download(package: str, candidate_count: int = 4) -> bool:
    try:
        links = fetch_index(package)
    except Exception as e:
        print(f"[skip] {package}: index fetch failed: {e}")
        return False
    if not links:
        print(f"[skip] {package}: no files on mirror")
        return False
    ok = False
    for best in _candidates(package, links, candidate_count):
        name = best.rsplit("/", 1)[-1]
        dest = WHEELS / name
        if dest.exists():
            ok = True
            continue
        url = urljoin(f"{MIRROR}/{package}/", best)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dsh-bootstrap/1.0"})
            with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as fh:
                while chunk := resp.read(1 << 16):
                    fh.write(chunk)
            print(f"[ok] {name}")
            ok = True
        except Exception as e:
            print(f"[warn] {package}/{name}: {e}")
            if dest.exists():
                dest.unlink(missing_ok=True)
    return ok


def top_level_packages() -> list[str]:
    pkgs = []
    for line in REQ_FILE.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        m = re.match(r"([A-Za-z0-9_.-]+)", line)
        if m:
            pkgs.append(m.group(1).lower().replace("_", "-"))
    return pkgs


def pip_offline() -> tuple[int, str]:
    env = dict(os.environ)
    env["TMP"] = env["TEMP"] = env["TMPDIR"] = str(ROOT / ".tmp")
    env["PIP_CACHE_DIR"] = str(ROOT / ".pipcache")
    cmd = [
        sys.executable, "-m", "pip", "install", "--no-index",
        "--find-links", str(WHEELS), "--target", str(TARGET),
        "-r", str(REQ_FILE),
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def extract_missing(output: str) -> set[str]:
    missing = set()
    for m in re.finditer(r"No matching distribution found for ([A-Za-z0-9_.-]+)", output):
        missing.add(m.group(1).lower().replace("_", "-"))
    # 版本约束不满足：下载更多候选版本（如 zhipuai 要求 pyjwt<2.9）
    for m in re.finditer(
        r"Could not find a version that satisfies the requirement ([A-Za-z0-9_.-]+)", output
    ):
        missing.add(m.group(1).lower().replace("_", "-"))
    # 版本冲突：只解析 "user requested X" 与 "Y depends on Z" 中的包名
    for m in re.finditer(r"user requested ([a-z][a-z0-9_.-]+)", output.lower()):
        missing.add(m.group(1))
    for m in re.finditer(r"([a-z][a-z0-9_.-]+) depends on ([a-z][a-z0-9_.-]+)", output.lower()):
        missing.add(m.group(1))
        missing.add(m.group(2))
    # "no matching distributions available for your environment:" 后的缩进包名
    m = re.search(
        r"no matching distributions available for your environment:\s*\n((?:\s+[a-z][a-z0-9_.-]+\n?)+)",
        output.lower(),
    )
    if m:
        for token in re.findall(r"[a-z][a-z0-9_.-]+", m.group(1)):
            missing.add(token)
    return missing


def extract_constrained(output: str) -> set[str]:
    """版本约束冲突的包：需要下载大量候选版本才能满足 <x.y 类约束。"""
    constrained = set()
    for m in re.finditer(
        r"Could not find a version that satisfies the requirement ([A-Za-z0-9_.-]+)", output
    ):
        constrained.add(m.group(1).lower().replace("_", "-"))
    return constrained


def main() -> int:
    WHEELS.mkdir(exist_ok=True)
    TARGET.mkdir(exist_ok=True)
    pkgs = [a.lower().replace("_", "-") for a in sys.argv[1:]]
    if not pkgs:
        pkgs = top_level_packages()
    print(f"resolving {len(pkgs)} top-level packages")

    conflict_pkgs: set[str] = set()
    constrained_pkgs: set[str] = set()
    for i in range(80):
        for pkg in pkgs:
            if pkg in constrained_pkgs:
                download(pkg, candidate_count=40)
            elif pkg in conflict_pkgs:
                download(pkg, candidate_count=4)
            else:
                download(pkg, candidate_count=2)
        rc, output = pip_offline()
        missing = extract_missing(output)
        constrained_pkgs |= extract_constrained(output)
        if rc == 0:
            print("INSTALL COMPLETE")
            return 0
        if not missing:
            print("pip failed without resolvable missing packages:")
            print(output[-4000:])
            return rc or 1
        print(f"round {i}: missing {sorted(missing)}")
        conflict_pkgs |= missing
        pkgs = sorted(missing)
    print("too many resolution rounds")
    return 1


if __name__ == "__main__":
    sys.exit(main())
