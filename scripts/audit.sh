#!/usr/bin/env bash
# Deterministic workspace audit for the knowledge workspace.
# Outputs structured markdown findings, data tables, and summary counts.
# Designed to be run by the review-workspace agent.
#
# Usage: bash scripts/audit.sh

set -uo pipefail

# Derive workspace root from script location (1 level up from scripts/)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ ! -f "$REPO_ROOT/CLAUDE.md" ]]; then
    echo "Error: cannot find workspace root (expected CLAUDE.md at $REPO_ROOT)" >&2
    exit 1
fi
cd "$REPO_ROOT"

TODAY_EPOCH=$(date +%s)
ERRORS=0
WARNINGS=0
INFOS=0
SCANNED=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

finding() {
    local sev="$1" title="$2" file="$3" issue="$4" convention="$5" fix="$6"
    echo "### [$sev] $title"
    echo ""
    echo "**File**: \`$file\`"
    echo "**Issue**: $issue"
    echo "**Convention**: $convention"
    echo "**Suggested fix**: $fix"
    echo ""
    echo "---"
    echo ""
    case "$sev" in
        Error)   ERRORS=$((ERRORS + 1)) ;;
        Warning) WARNINGS=$((WARNINGS + 1)) ;;
        Info)    INFOS=$((INFOS + 1)) ;;
    esac
}

days_since() {
    local file="$1"
    local file_epoch
    file_epoch=$(git log -1 --format='%ct' -- "$file" 2>/dev/null)
    if [[ -n "$file_epoch" ]]; then
        echo $(( (TODAY_EPOCH - file_epoch) / 86400 ))
    else
        echo "-1"
    fi
}

# Count tracked .md files
SCANNED=$(git ls-files '*.md' 2>/dev/null | wc -l | tr -d ' ')

echo "# Automated audit results"
echo ""
echo "Generated: $(date +%Y-%m-%d)"
echo "Files in repo: $SCANNED"
echo ""

# ===================================================================
# STRUCTURE CHECKS
# ===================================================================

echo "## Structure findings"
echo ""

# --- 1. Required root files ---
for f in CLAUDE.md CLAUDE.local.example.md CONTRIBUTING.md README.md .gitignore; do
    if [[ ! -f "$f" ]]; then
        finding "Error" "Missing required root file: $f" "$f" \
            "Required root file does not exist." \
            "Directory structure > Top-level layout" \
            "Create $f at repository root."
    fi
done

# departments/ directory must exist
if [[ ! -d "departments" ]]; then
    finding "Error" "Missing departments/ directory" "departments/" \
        "The departments/ directory does not exist." \
        "Directory structure > Top-level layout" \
        "Create departments/ directory and move department folders into it."
fi

# No MCP configuration check: the personal MCP config file is gitignored and
# never committed (CONTRIBUTING.md > "MCP configuration"), so its absence at
# the repo root is the expected state and not a finding. A tracked copy is
# caught by security-lint, not by this script.

# --- 2. Department/team directories must have CLAUDE.md ---
# Check direct children of departments/ (these are departments)
if [[ -d "departments" ]]; then
    while IFS= read -r dir; do
        dir="${dir#./}"
        [[ -z "$dir" ]] && continue
        bname=$(basename "$dir")
        [[ "$bname" =~ ^\. ]] && continue

        if [[ ! -f "$dir/CLAUDE.md" ]]; then
            finding "Warning" "Missing CLAUDE.md in $dir" "$dir/" \
                "Department directory exists but has no CLAUDE.md." \
                "Directory structure > Department and team folders" \
                "Add CLAUDE.md to $dir/ or remove the directory if not a department folder."
        fi
    done < <(find departments -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort)

    # Check teams/ subdirectories within departments
    while IFS= read -r dir; do
        dir="${dir#./}"
        [[ -z "$dir" ]] && continue
        bname=$(basename "$dir")
        [[ "$bname" =~ ^\. ]] && continue

        if [[ ! -f "$dir/CLAUDE.md" ]]; then
            finding "Warning" "Missing CLAUDE.md in $dir" "$dir/" \
                "Team directory exists but has no CLAUDE.md." \
                "Directory structure > Department and team folders" \
                "Add CLAUDE.md to $dir/ or remove the directory if not a team folder."
        fi
    done < <(find departments/*/teams -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort)
fi

# --- 3. Root-level .md files ---
while IFS= read -r f; do
    f="${f#./}"
    case "$f" in
        CLAUDE.md|CLAUDE.local.md|CLAUDE.local.example.md|CONTRIBUTING.md|README.md) ;;
        *)
            finding "Info" "Unexpected root-level .md file: $f" "$f" \
                "Root-level .md file beyond CLAUDE.md, CLAUDE.local.md, CLAUDE.local.example.md, CONTRIBUTING.md, README.md." \
                "Directory structure > Files at root level" \
                "Move to context/ (if cross-functional) or a department folder (if department-specific)."
            ;;
    esac
done < <(find . -maxdepth 1 -name '*.md' -type f 2>/dev/null | sort)

# --- 4. Knowledge hierarchy depth ---
while IFS= read -r cfile; do
    cfile="${cfile#./}"
    # Count CLAUDE.md inheritance levels (skip grouping dirs: departments/, teams/)
    # Effective depth: root=1, departments/X=2, departments/X/teams/Y=3
    depth=1
    path_part=$(dirname "$cfile")
    if [[ "$path_part" == "." ]]; then
        depth=1
    elif [[ "$path_part" =~ ^departments/[^/]+$ ]]; then
        depth=2
    elif [[ "$path_part" =~ ^departments/[^/]+/teams/[^/]+$ ]]; then
        depth=3
    else
        # Count actual directory separators for unexpected paths
        depth=$(echo "$path_part" | tr -cd '/' | wc -c | tr -d ' ')
        depth=$((depth + 1))
    fi

    if (( depth > 3 )); then
        finding "Warning" "Knowledge hierarchy too deep: $cfile" "$cfile" \
            "CLAUDE.md effective nesting depth is $depth (max recommended: 3)." \
            "Directory structure > Knowledge hierarchy depth" \
            "Flatten the hierarchy or merge with parent CLAUDE.md."
    fi
done < <(find . -name 'CLAUDE.md' \
    ! -path './.git/*' \
    ! -path '*/projects/*' \
    ! -path '*/node_modules/*' 2>/dev/null | sort)

# --- 5. Directory naming (kebab-case) ---
if [[ -d "departments" ]]; then
    while IFS= read -r dir; do
        dir="${dir#./}"
        [[ -z "$dir" ]] && continue
        bname=$(basename "$dir")
        [[ "$bname" =~ ^\. ]] && continue
        # Skip known grouping dirs
        [[ "$bname" == "departments" ]] && continue
        [[ "$bname" == "teams" ]] && continue
        [[ "$bname" == "context" ]] && continue
        [[ "$bname" == "projects" ]] && continue
        [[ "$bname" == "scripts" ]] && continue

        # Check for kebab-case: lowercase letters, digits, and hyphens only
        if [[ ! "$bname" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
            finding "Warning" "Directory not kebab-case: $bname" "$dir/" \
                "Directory name is not kebab-case (expected: lowercase letters, digits, hyphens)." \
                "Content quality > File naming" \
                "Rename to kebab-case."
        fi
    done < <(find departments -mindepth 1 -maxdepth 4 -type d \
        ! -path '*/.git*' \
        ! -path '*/.claude*' \
        ! -path '*/projects/*' \
        ! -path '*/node_modules/*' 2>/dev/null | sort)
fi

# ===================================================================
# CONTENT QUALITY CHECKS
# ===================================================================

echo "## Content quality findings"
echo ""

# Collect all CLAUDE.md files once
claude_files=()
while IFS= read -r f; do
    claude_files+=("${f#./}")
done < <(find . -name 'CLAUDE.md' \
    ! -path './.git/*' \
    ! -path '*/projects/*' \
    ! -path '*/node_modules/*' 2>/dev/null | sort)

# --- 6. H1 checks ---
for file in "${claude_files[@]}"; do
    # Must start with exactly one H1
    h1_count=$(grep -c '^# [^#]' "$file" 2>/dev/null || echo 0)

    if (( h1_count == 0 )); then
        finding "Warning" "No H1 heading" "$file" \
            "File has no H1 heading." \
            "Content quality > Heading hierarchy" \
            "Add an H1 (#) heading at the top of the file."
    elif (( h1_count > 1 )); then
        finding "Warning" "Multiple H1 headings ($h1_count)" "$file" \
            "File has $h1_count H1 headings (should be exactly 1)." \
            "Content quality > Heading hierarchy" \
            "Keep one H1 as the file title, demote others to H2."
    fi

    # First heading should be H1
    first_heading=$(awk '/^```/{c=!c} !c && /^#/{print; exit}' "$file" 2>/dev/null)
    if [[ -n "$first_heading" ]]; then
        hashes="${first_heading%%[^#]*}"
        level=${#hashes}
        if (( level != 1 )); then
            finding "Warning" "First heading is not H1" "$file" \
                "First heading is H$level, should be H1." \
                "Content quality > Heading hierarchy" \
                "Change the first heading to H1 (#)."
        fi
    fi
done

# --- 7. Heading level skips and H4+ ---
for file in "${claude_files[@]}"; do
    prev_level=0
    while IFS= read -r heading; do
        [[ -z "$heading" ]] && continue
        hashes="${heading%%[^#]*}"
        level=${#hashes}

        if (( level >= 4 )); then
            finding "Info" "Deep heading (H$level)" "$file" \
                "Heading: '$heading'. Consider if content should be in a separate file." \
                "Content quality > Heading hierarchy" \
                "Restructure or move content to reduce nesting."
        fi

        if (( prev_level > 0 && level > prev_level + 1 )); then
            finding "Warning" "Heading level skip (H$prev_level to H$level)" "$file" \
                "Heading jumps from H$prev_level to H$level: '$heading'" \
                "Content quality > Heading hierarchy" \
                "Don't skip heading levels."
        fi

        prev_level=$level
    done < <(awk '/^```/{c=!c} !c && /^#/{print}' "$file" 2>/dev/null)
done

# --- 8. TODO format consistency ---
for file in "${claude_files[@]}"; do
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        lineno=$(echo "$line" | cut -d: -f1)
        content=$(echo "$line" | cut -d: -f2-)
        finding "Warning" "TODO in heading format" "$file:$lineno" \
            "TODO marker in heading: '$content'. Should be in section body." \
            "Content quality > TODO conventions" \
            "Change to a regular heading followed by [TODO: description] in the body."
    done < <(grep -n '^##* \[TODO\]' "$file" 2>/dev/null || true)
done

# --- 9. Empty sections (heading immediately followed by another heading) ---
for file in "${claude_files[@]}"; do
    prev_was_heading=false
    prev_heading=""
    prev_lineno=0
    lineno=0
    while IFS= read -r line; do
        lineno=$((lineno + 1))
        if [[ "$line" =~ ^##+ ]]; then
            if $prev_was_heading; then
                finding "Info" "Empty section" "$file:$prev_lineno" \
                    "Section '$prev_heading' has no content before next heading." \
                    "Content quality > Markdown formatting" \
                    "Add content or a [TODO: description] placeholder."
            fi
            prev_was_heading=true
            prev_heading="$line"
            prev_lineno=$lineno
        elif [[ -n "$line" ]]; then
            prev_was_heading=false
        fi
        # Blank lines don't reset; only non-empty non-heading lines do
    done < "$file"
done

# --- 10. Context Index completeness ---
if [[ -f "CLAUDE.md" ]]; then
    # Extract file paths referenced in Context Index
    indexed_files=$(grep -oE 'context/[a-zA-Z_-]+\.md' CLAUDE.md 2>/dev/null | sort -u || true)

    # Actual context files
    actual_files=""
    if [[ -d "context" ]]; then
        actual_files=$(find context -maxdepth 1 -name '*.md' -type f 2>/dev/null | sort -u || true)
    fi

    # Indexed but file missing
    if [[ -n "$indexed_files" ]]; then
        while IFS= read -r f; do
            [[ -z "$f" ]] && continue
            if [[ ! -f "$f" ]]; then
                finding "Error" "Context Index references missing file" "CLAUDE.md" \
                    "Context Index references '$f' but file does not exist." \
                    "Context files > Conventions" \
                    "Create the file or remove the row from the Context Index."
            fi
        done <<< "$indexed_files"
    fi

    # File exists but not indexed
    if [[ -n "$actual_files" ]]; then
        while IFS= read -r f; do
            [[ -z "$f" ]] && continue
            if [[ -n "$indexed_files" ]]; then
                if ! echo "$indexed_files" | grep -qF "$f"; then
                    finding "Warning" "Context file not in Context Index" "$f" \
                        "File exists in context/ but has no row in the Context Index." \
                        "Context files > Conventions" \
                        "Add a row to the Context Index in CLAUDE.md."
                fi
            else
                finding "Warning" "Context file not in Context Index" "$f" \
                    "File exists in context/ but Context Index is empty or missing." \
                    "Context files > Conventions" \
                    "Add a Context Index table to CLAUDE.md."
            fi
        done <<< "$actual_files"
    fi
fi

# ===================================================================
# CONVENTION COMPLIANCE CHECKS
# ===================================================================

echo "## Convention compliance findings"
echo ""

# --- 11. Agent frontmatter and structure ---
while IFS= read -r agent; do
    agent="${agent#./}"
    bname=$(basename "$agent" .md)

    # Check frontmatter exists
    if ! head -1 "$agent" 2>/dev/null | grep -q '^---'; then
        finding "Error" "Agent missing frontmatter" "$agent" \
            "Agent file has no YAML frontmatter." \
            "Agent file conventions > Structure" \
            "Add YAML frontmatter with name, description, tools, and model fields."
        continue
    fi

    # Extract frontmatter
    fm=$(awk '/^---$/{n++; next} n==1{print} n>=2{exit}' "$agent" 2>/dev/null)

    # Required fields
    for field in name description tools model; do
        if ! echo "$fm" | grep -q "^${field}:"; then
            finding "Warning" "Agent missing '$field' field" "$agent" \
                "Frontmatter is missing the '$field' field." \
                "Agent file conventions > Structure" \
                "Add '$field' to the YAML frontmatter."
        fi
    done

    # Name matches filename
    name_val=$(echo "$fm" | grep '^name:' | sed 's/^name: *//' | tr -d "\"'" | xargs)
    if [[ -n "$name_val" && "$name_val" != "$bname" ]]; then
        finding "Warning" "Agent name doesn't match filename" "$agent" \
            "Frontmatter name is '$name_val' but filename is '$bname.md'." \
            "Agent file conventions > Naming" \
            "Make the name field match the filename (without .md)."
    fi

    # Body structure
    if ! grep -q '^## Your [Rr]ole' "$agent" 2>/dev/null; then
        finding "Info" "Agent missing '## Your Role' section" "$agent" \
            "Agent body doesn't have a '## Your Role' section." \
            "Agent file conventions > Body structure" \
            "Add a '## Your Role' section."
    fi
    if ! grep -q '^## Boundaries' "$agent" 2>/dev/null; then
        finding "Info" "Agent missing '## Boundaries' section" "$agent" \
            "Agent body doesn't have a '## Boundaries' section." \
            "Agent file conventions > Body structure" \
            "Add a '## Boundaries' section."
    fi
done < <(find . -path '*/.claude/agents/*.md' \
    ! -path './.git/*' \
    ! -path '*/projects/*' \
    ! -path '*/node_modules/*' 2>/dev/null | sort)

# --- 12. Skill frontmatter ---
while IFS= read -r skill; do
    skill="${skill#./}"

    if ! head -1 "$skill" 2>/dev/null | grep -q '^---'; then
        finding "Error" "Skill missing frontmatter" "$skill" \
            "SKILL.md has no YAML frontmatter." \
            "Skill conventions > SKILL.md format" \
            "Add YAML frontmatter with name and description fields."
        continue
    fi

    fm=$(awk '/^---$/{n++; next} n==1{print} n>=2{exit}' "$skill" 2>/dev/null)

    for field in name description; do
        if ! echo "$fm" | grep -q "^${field}:"; then
            finding "Warning" "Skill missing '$field' field" "$skill" \
                "Frontmatter is missing the '$field' field." \
                "Skill conventions > SKILL.md format" \
                "Add '$field' to the YAML frontmatter."
        fi
    done
done < <(find . -name 'SKILL.md' \
    ! -path './.git/*' \
    ! -path '*/projects/*' \
    ! -path '*/node_modules/*' 2>/dev/null | sort)

# --- 13. README agent table accuracy ---
if [[ -f "README.md" ]]; then
    # Extract agent names from README table (lines with | ... agent ... |)
    readme_agents=$(grep -oE '[a-z]+-[a-z-]+' README.md 2>/dev/null | sort -u || true)

    # Actual agent filenames
    actual_agents=""
    while IFS= read -r a; do
        actual_agents+="$(basename "$a" .md)"$'\n'
    done < <(find . -path '*/.claude/agents/*.md' \
        ! -path './.git/*' \
        ! -path '*/projects/*' \
        ! -path '*/node_modules/*' 2>/dev/null | sort)
    actual_agents=$(echo "$actual_agents" | sort -u | grep -v '^$' || true)

    # Agents in repo but not in README
    if [[ -n "$actual_agents" ]]; then
        while IFS= read -r a; do
            [[ -z "$a" ]] && continue
            if [[ -n "$readme_agents" ]]; then
                if ! echo "$readme_agents" | grep -qF "$a"; then
                    finding "Info" "Agent not listed in README: $a" "README.md" \
                        "Agent '$a' exists but is not mentioned in README.md." \
                        "README accuracy" \
                        "Add the agent to the agents table in README.md."
                fi
            fi
        done <<< "$actual_agents"
    fi
fi

# ===================================================================
# FRESHNESS DATA
# ===================================================================

echo "## Freshness data"
echo ""
echo "| File | Last modified | Days ago | Threshold | Status |"
echo "|------|---------------|----------|-----------|--------|"

freshness_check() {
    local file="$1" threshold="$2"
    local last_mod days status
    last_mod=$(git log -1 --format='%ai' -- "$file" 2>/dev/null | cut -d' ' -f1)
    days=$(days_since "$file")

    if [[ "$days" == "-1" ]]; then
        status="Untracked"
    elif (( days > threshold )); then
        status="**STALE**"
    else
        status="Fresh"
    fi

    echo "| \`$file\` | $last_mod | $days | ${threshold}d | $status |"

    # Also emit a finding for stale files
    if [[ "$days" != "-1" ]] && (( days > threshold )); then
        # Print finding to stderr so it doesn't break the table
        finding "Warning" "Stale file: $file" "$file" \
            "Last modified $days days ago (threshold: ${threshold} days)." \
            "Freshness expectations" \
            "Review and update this file." >&2
    fi
}

# Redirect freshness findings to a temp file, print table to stdout
STALE_FINDINGS=$(mktemp)
trap 'rm -f "$STALE_FINDINGS"' EXIT

{
    # Root & navigation (30d)
    freshness_check "CLAUDE.md" 30
    freshness_check "README.md" 30

    # Context files carry their own cadence in the maintenance header;
    # tools/maintenance/check.py --report owns their freshness, not this table.

    # Department/team CLAUDE.md files (90d)
    for file in "${claude_files[@]}"; do
        [[ "$file" == "CLAUDE.md" ]] && continue
        freshness_check "$file" 90
    done

    # Rules (180d)
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        freshness_check "${f#./}" 180
    done < <(find .claude/rules -name '*.md' -type f 2>/dev/null | sort)
} 2>"$STALE_FINDINGS"

echo ""

# Print any stale findings that were captured
if [[ -s "$STALE_FINDINGS" ]]; then
    echo "## Freshness findings"
    echo ""
    cat "$STALE_FINDINGS"
fi

# ===================================================================
# TODO INVENTORY
# ===================================================================

echo "## TODO inventory"
echo ""
echo "| Location | Sections | Filled | TODO | Completeness |"
echo "|----------|----------|--------|------|--------------|"

total_sections=0
total_filled=0
total_todo=0

for file in "${claude_files[@]}"; do
    location=$(dirname "$file")
    [[ "$location" == "." ]] && location="Root"

    result=$(awk '
    /^## / {
        if (current != "" && has_todo) todo_count++;
        if (current != "" && !has_todo) filled_count++;
        current = $0;
        has_todo = 0;
    }
    /\[TODO/ { has_todo = 1 }
    END {
        if (current != "" && has_todo) todo_count++;
        if (current != "" && !has_todo) filled_count++;
        total = filled_count + todo_count;
        if (total > 0) pct = int(filled_count * 100 / total);
        else pct = 100;
        printf "%d|%d|%d|%d\n", total, filled_count, todo_count, pct
    }
    ' "$file")

    IFS='|' read -r sections filled todo pct <<< "$result"
    total_sections=$((total_sections + sections))
    total_filled=$((total_filled + filled))
    total_todo=$((total_todo + todo))

    echo "| $location | $sections | $filled | $todo | ${pct}% |"
done

if (( total_sections > 0 )); then
    overall_pct=$((total_filled * 100 / total_sections))
else
    overall_pct=100
fi
echo "| **Total** | **$total_sections** | **$total_filled** | **$total_todo** | **${overall_pct}%** |"
echo ""

# ===================================================================
# SUMMARY
# ===================================================================

echo "## Automated check summary"
echo ""
echo "- Errors: $ERRORS"
echo "- Warnings: $WARNINGS"
echo "- Info: $INFOS"
echo "- Total findings: $((ERRORS + WARNINGS + INFOS))"
