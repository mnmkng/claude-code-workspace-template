#!/usr/bin/env bash
# PreToolUse hook: blocks edits/writes to security-critical files and blocks
# Bash attempts to bypass the sandbox or clobber those same files via shell
# redirection.
#
# Exit 0: allow the tool call.
# Exit 2: block the tool call with a message to Claude (shown in transcript).
#
# Claude Code passes the tool payload on stdin as JSON:
#   { "tool_name": "...", "tool_input": { ... } }

set -euo pipefail

INPUT="$(cat)"

tool_name="$(printf '%s' "$INPUT" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_name",""))' 2>/dev/null || true)"

block() {
  >&2 printf 'blocked by protect-config hook: %s\n' "$1"
  exit 2
}

field() {
  printf '%s' "$INPUT" | /usr/bin/python3 -c "
import json, sys
d = json.load(sys.stdin).get('tool_input', {})
print(d.get('$1', ''))
" 2>/dev/null || true
}

# Matches every file path whose contents let you weaken the security posture.
# Add new protected paths here; the Bash-redirection guard below picks up the
# same list via pattern shape.
is_protected_path() {
  case "$1" in
    # Configuration
    */.claude/settings.json|*/.claude/settings.local.json|*/.mcp.json) return 0 ;;
    # Personal/team context file: gitignored, loaded as instructions (the
    # committed CLAUDE.md @imports it), regenerated each session in cloud.
    */CLAUDE.local.md) return 0 ;;
    # Security enforcement
    */.claude/hooks/*.sh) return 0 ;;
    */.claude/rules/security-check.md) return 0 ;;
    */scripts/claude.sh|*/scripts/install.sh) return 0 ;;
    */.githooks/post-checkout) return 0 ;;
    */.github/workflows/security-lint.yml) return 0 ;;
    # Cloud bootstrap state: reset consumes the manifest + copied-files index,
    # so tampering with them turns reset into an arbitrary-delete primitive.
    */.claude/.bootstrap-*) return 0 ;;
  esac
  return 1
}

case "$tool_name" in
  Write|Edit|MultiEdit)
    path="$(field file_path)"
    if is_protected_path "$path"; then
      block "editing $path is restricted. Propose the diff in chat and let the user apply it."
    fi
    ;;

    Bash)
    cmd="$(field command)"

    # Block attempts to disable sandbox or skip permissions per-call.
    case "$cmd" in
      *dangerouslyDisableSandbox*|*--dangerously-skip-permissions*|*bypassPermissions*)
        block "Bash call attempts to disable sandbox or skip permissions: $cmd"
        ;;
    esac

    # ---- Denied-command guard ----------------------------------
    # The permissions.deny / sandbox excludedCommands matchers in settings.json
    # only see the PREFIX of the command string, so a denied command wrapped in
    # a multi-statement script (e.g. `X=1; git clone ...`) or hidden behind a
    # leading VAR=... assignment slips past them. This hook sees the full
    # command, so we re-derive the leading verb of every statement and block
    # anything sensitive the settings matcher could not have seen.
    #
    #   HARD verbs (curl, wget, ssh, sudo, chmod 777, gh auth token/login,
    #   credential.helper) mirror permissions.deny: blocked in any position.
    #   ASK verbs (git clone/fetch/pull, force-push) are allowed to run, but
    #   only at the literal start of a single, unprefixed statement so the
    #   "ask" matcher can prompt; wrapped or hidden forms are blocked and must
    #   be re-issued as a standalone command. One carve-out:
    #   git fetch from a trusted remote is exempt from the visible-position
    #   rule, because it reaches no new host and writes nothing outside .git.
    #   See is_safe_fetch below.
    denied_hit="$(printf '%s' "$cmd" | /usr/bin/python3 -c '
import re, sys, shlex
cmd = sys.stdin.read()

HARD = {"curl","wget","nc","ncat","netcat","ssh","scp","sftp","telnet","sudo","doas"}

ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SKIP = {"env","command","exec","time","nohup","stdbuf","nice","ionice","setsid","builtin","xargs","then","do","else"}
SEP = re.compile(r"\|\||&&|\||;|\n|`|\$\(|\(|\)|\{|\}")

def lead(seg):
    try:
        toks = shlex.split(seg, posix=True)
    except ValueError:
        toks = seg.split()
    i = 0
    while i < len(toks) and (ASSIGN.match(toks[i]) or toks[i] in SKIP):
        i += 1
    was_stripped = i > 0
    toks = toks[i:]
    if toks:
        toks[0] = toks[0].split("/")[-1]
    return toks, was_stripped

def hard_match(t, seg):
    if t and t[0] in HARD:
        return t[0]
    if t[:1] == ["chmod"] and any("777" in x for x in t[1:]):
        return "chmod 777"
    if t[:2] == ["gh","auth"] and len(t) >= 3 and t[2] in {"token","login","logout","refresh"}:
        return "gh auth " + t[2]
    if t[:1] == ["git"] and "credential.helper" in seg:
        return "git config credential.helper"
    return ""

# A fetch naming an already-trusted remote reaches no new host and writes
# nothing outside .git, so it does not need the visible-position rule below.
# Kept in lockstep with the Bash(git fetch <name>:*) allow rules in
# settings.json. A hardcoded name list rather than a git remote lookup: no
# subprocess in the hook, and the name-to-URL binding is gated separately by
# the ask rules on git remote add/set-url/rename.
SAFE_FETCH_REMOTES = {"origin"}

# Allowlist, not a denylist: an unvetted flag prompts instead of inheriting
# the carve-out. --recurse-submodules is why - it reads .gitmodules from the
# fetched commit and fetches those URLs, so a trusted remote name would not
# bound where the fetch reaches.
SAFE_FETCH_FLAGS = {
    "--prune","--prune-tags","--tags","--no-tags","--depth","--deepen",
    "--shallow-since","--unshallow","--force","-f","--quiet","-q",
    "--verbose","-v","--progress","--no-progress","--dry-run","-n",
    "--atomic","--no-recurse-submodules",
}

def is_safe_fetch(t):
    if t[:2] != ["git","fetch"]:
        return False
    args = t[2:]
    if not args or args[0] not in SAFE_FETCH_REMOTES:
        return False
    for a in args[1:]:
        if a.startswith("-"):
            if a.split("=", 1)[0] not in SAFE_FETCH_FLAGS:
                return False
            continue
        if "://" in a or a.startswith("git@") or a.startswith("ext::"):
            return False
    return True

def ask_match(t):
    if t[:2] == ["git","push"] and any(x.startswith("--force") or x == "-f" for x in t[2:]):
        return "git push --force"
    for pat in (["git","clone"], ["git","fetch"], ["git","pull"]):
        if t[:len(pat)] == pat:
            return " ".join(pat)
    return ""

segs = [s.strip() for s in SEP.split(cmd) if s.strip()]
multi = len(segs) > 1

hit = ""
for seg in segs:
    t, was_stripped = lead(seg)
    if not t:
        continue
    h = hard_match(t, seg)
    if h:
        hit = h; break
    a = ask_match(t)
    if a:
        if is_safe_fetch(t):
            continue
        visible = (not multi) and (not was_stripped)
        if not visible:
            hit = a + " (wrapped)"
            break
print(hit)
' 2>/dev/null || true)"
    if [ -n "$denied_hit" ]; then
      block "denied/sensitive command '$denied_hit' detected in Bash input (issue #57: matched regardless of position; run sensitive commands as a standalone command so settings.json can gate them): $cmd"
    fi

    # Substring fragments that identify a protected file when they appear
    # anywhere in a Bash command. The sandbox denyWrite is the deterministic
    # backstop; this provides friendlier errors at the hook layer.
    protected_fragments='
.claude/settings.json
.claude/settings.local.json
.mcp.json
.claude/rules/security-check.md
.claude/hooks/
scripts/claude.sh
scripts/install.sh
.githooks/post-checkout
.github/workflows/security-lint.yml
.claude/.bootstrap-
CLAUDE.local.md
'

    # Helper: block if any protected fragment is mentioned in the command,
    # tagged with the write-pattern that triggered the check.
    check_protected() {
      local label="$1"
      while IFS= read -r frag; do
        [ -z "$frag" ] && continue
        case "$cmd" in
          *"$frag"*) block "$label targets protected path ($frag): $cmd" ;;
        esac
      done <<EOF
$protected_fragments
EOF
    }

    # ---- Shell redirection into a protected file ---------------------------
    # Quote-aware: only actual redirect TARGETS are checked, so commands that
    # merely mention a protected path while redirecting elsewhere pass (e.g.
    # `ls CLAUDE.local.md 2>&1`, `grep x .claude/rules/security-check.md
    # 2>/dev/null`). Never weaker than the old whole-command scan: when a
    # target cannot be resolved statically ($VAR, $(...), backticks, unclosed
    # quotes) or a `>` hides inside a quoted string (eval / sh -c payloads),
    # it falls back to matching fragments against the whole command.
    case "$cmd" in
      *'>'*)
        redirect_hit="$(printf '%s' "$cmd" | /usr/bin/python3 -c '
import sys

cmd = sys.stdin.read()
frags = [f.strip() for f in sys.argv[1].splitlines() if f.strip()]
SQ = "\x27"
WORD_END = " \t\n;|&<>()`"

def frag_in(s):
    for f in frags:
        if f in s:
            return f
    return ""

targets = []
fallback = False

i, n = 0, len(cmd)
while i < n:
    c = cmd[i]
    if c == "\\":
        i += 2
        continue
    if c == SQ:
        j = cmd.find(SQ, i + 1)
        if j == -1:
            fallback = True
            break
        if ">" in cmd[i:j]:
            fallback = True
        i = j + 1
        continue
    if c == "\"":
        j = i + 1
        while j < n and cmd[j] != "\"":
            if cmd[j] == "\\":
                j += 1
            j += 1
        if j >= n:
            fallback = True
            break
        if ">" in cmd[i:j]:
            fallback = True
        i = j + 1
        continue
    if c == "<" and cmd[i:i + 2] != "<>":
        i += 1
        continue
    if c == ">" or cmd[i:i + 2] == "<>":
        # Consume the operator: >, >>, >|, &>/&>> (the & was consumed as a
        # plain char on the previous iteration), and the rare read-write <>.
        if cmd[i:i + 2] == "<>":
            i += 2
        else:
            i += 1
            while i < n and cmd[i] in ">|":
                i += 1
        # >&N and >&- are fd duplications, not file writes; >&word IS a file.
        if i < n and cmd[i] == "&":
            i += 1
            j = i
            while j < n and cmd[j].isdigit():
                j += 1
            if (j > i and (j >= n or cmd[j] in WORD_END)) or (i < n and cmd[i] == "-"):
                i = j if j > i else i + 1
                continue
        while i < n and cmd[i] in " \t":
            i += 1
        # Read the target word, honoring quotes so quote-splitting evasion
        # (> CLAUDE."local".md) still resolves to the real filename.
        word = ""
        bad = False
        while i < n and cmd[i] not in WORD_END:
            ch = cmd[i]
            if ch == "\\" and i + 1 < n:
                word += cmd[i + 1]
                i += 2
                continue
            if ch == SQ:
                j = cmd.find(SQ, i + 1)
                if j == -1:
                    bad = True
                    i = n
                    break
                word += cmd[i + 1:j]
                i = j + 1
                continue
            if ch == "\"":
                j = i + 1
                buf = ""
                while j < n and cmd[j] != "\"":
                    if cmd[j] == "\\" and j + 1 < n:
                        buf += cmd[j + 1]
                        j += 2
                        continue
                    buf += cmd[j]
                    j += 1
                if j >= n:
                    bad = True
                    i = n
                    break
                word += buf
                i = j + 1
                continue
            word += ch
            i += 1
        if bad or "$" in word or "`" in word or not word.strip():
            fallback = True
        else:
            targets.append(word)
        continue
    i += 1

hit = ""
for t in targets:
    f = frag_in(t)
    if f:
        hit = f + " via redirect target: " + t
        break
if not hit and fallback:
    f = frag_in(cmd)
    if f:
        hit = f + " (unresolvable redirect target; whole-command match)"
print(hit)
' "$protected_fragments" 2>/dev/null || true)"
        if [ -n "$redirect_hit" ]; then
          block "shell redirection targets protected path ($redirect_hit): $cmd"
        fi
        ;;
    esac

    # Direct file-writing tools.
    case "$cmd" in
      cp\ *|/bin/cp\ *|/usr/bin/cp\ *|\
      mv\ *|/bin/mv\ *|/usr/bin/mv\ *|\
      install\ *|/usr/bin/install\ *|\
      tee\ *|/usr/bin/tee\ *|\
      dd\ *|/bin/dd\ *|/usr/bin/dd\ *|\
      truncate\ *|/usr/bin/truncate\ *|\
      ln\ *-sf*|ln\ *--force*)
        check_protected "direct write command"
        ;;
    esac

    # In-place editors.
    case "$cmd" in
      sed\ *-i*|sed\ *--in-place*|perl\ *-i*|perl\ *-pi*)
        check_protected "in-place editor"
        ;;
    esac

    # Direct write / in-place edit tools in ANY pipeline position, not just as
    # the leading command (e.g. `echo x | tee FILE`, `a; cp x FILE`,
    # `b && sed -i ... FILE`). The case patterns above only match a leading
    # token, so we re-derive the leading verb of every statement and, if it is
    # a write/edit tool, re-check the whole command for a protected fragment.
    # (check_protected only blocks when a protected fragment is present, so
    # flagging an ordinary `cp a b` here is harmless.)
    writes_protected="$(printf '%s' "$cmd" | /usr/bin/python3 -c '
import re, sys, shlex
cmd = sys.stdin.read()
WRITE = {"cp","mv","tee","dd","install","truncate","rsync","tar","unzip","patch"}
SEP = re.compile(r"\|\||&&|\||;|\n|`|\$\(|\(|\)|\{|\}")
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SKIP = {"env","command","exec","time","nohup","stdbuf","nice","ionice","setsid","builtin","xargs","then","do","else","sudo"}
def lead(seg):
    try:
        toks = shlex.split(seg, posix=True)
    except ValueError:
        toks = seg.split()
    i = 0
    while i < len(toks) and (ASSIGN.match(toks[i]) or toks[i] in SKIP):
        i += 1
    toks = toks[i:]
    if toks:
        toks[0] = toks[0].split("/")[-1]
    return toks
flag = ""
for seg in SEP.split(cmd):
    seg = seg.strip()
    if not seg:
        continue
    t = lead(seg)
    if not t:
        continue
    v = t[0]
    if v in WRITE:
        flag = "1"; break
    if v == "ln" and any(a.startswith("-") and "f" in a for a in t[1:]):
        flag = "1"; break
    if v in ("sed","perl") and any(a.startswith("-i") or a.startswith("-pi") or a == "--in-place" for a in t[1:]):
        flag = "1"; break
print(flag)
' 2>/dev/null || true)"
    if [ "$writes_protected" = "1" ]; then
      check_protected "direct write command (any pipeline position)"
    fi

    # Interpreters used to write files via stdlib. Plain `>` is NOT in this
    # list: real redirects are handled precisely by the redirect guard above,
    # and a `>` inside a quoted -c payload triggers that guard`s conservative
    # fallback, so dropping it here only removes false positives (e.g.
    # `python3 -m json.tool .claude/settings.json > /dev/null`).
    case "$cmd" in
      python\ *|python3\ *|perl\ *|ruby\ *|node\ *|bash\ -c*|sh\ -c*)
        case "$cmd" in
          *open\(*|*write_text*|*writeFileSync*|*appendFileSync*|*createWriteStream*|*File.write*)
            check_protected "interpreter write"
            ;;
        esac
        ;;
    esac
    ;;
esac

exit 0
