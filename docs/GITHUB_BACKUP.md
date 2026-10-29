# GitHub Backup Strategy - PythonXAU

**Repository**: https://github.com/skyt19/PythonXAU  
**Local Path**: C:\z  
**Primary Branch**: master  
**Development Branch**: claude/end-to-end-build

---

## Remote Configuration

```bash
# Remote URL
origin: https://github.com/skyt19/PythonXAU.git

# Verify remote
git remote -v
git ls-remote origin
```

---

## Branch Strategy

### master
- Stable checkpoints only
- Fully tested code
- Complete documentation
- Clean commits with Co-Authored-By attribution

### claude/end-to-end-build
- Active development branch
- Incremental progress commits
- Checkpoint after each completed phase
- Merged to master after full verification

### Branch Protection
- Never force-push to any branch
- Always fetch before push
- Preserve remote-only commits
- Use safe merge/rebase strategies

---

## Checkpoint Cadence

Commit and push after:
1. Each phase completion
2. All phase tests passing
3. Documentation updated
4. Git diff reviewed
5. Secrets excluded verified

Typical checkpoint frequency: Every 1-2 hours of work or major milestone

---

## Secret Exclusions

### Never Commit
- `.env` files (credentials)
- `*.key`, `*.pem` (private keys)
- `credentials.json`
- `secrets.yaml`
- Database files with secrets (`*.db` with credentials)
- Sensitive logs
- MT5 account numbers/passwords
- API tokens
- Private account details

### `.gitignore` Coverage
```
.env
.env.local
*.key
*.pem
credentials.json
secrets.yaml
*.db
*.sqlite
*.sqlite3
logs/*.log
```

---

## Push Workflow

### Before Every Push

```bash
# 1. Verify clean state
git status

# 2. Check for secrets
git diff --cached | grep -i "password\|token\|key\|secret" || echo "No obvious secrets"

# 3. Review .gitignore
cat .gitignore

# 4. Fetch remote changes
git fetch origin

# 5. Check for divergence
git log origin/claude/end-to-end-build..HEAD
git log HEAD..origin/claude/end-to-end-build

# 6. Push safely (no force)
git push origin claude/end-to-end-build
```

### Push Commands

```bash
# Push development branch
git push origin claude/end-to-end-build

# Push master (after merge)
git push origin master

# Push tags (for releases)
git push origin --tags
```

---

## Recovery Commands

### If Push Fails (Network)

```bash
# Continue working locally
git commit -m "Work continues offline"

# Later, when network returns
git fetch origin
git push origin claude/end-to-end-build
```

### If Push Fails (Authentication)

```bash
# Check credentials
git config credential.helper

# Use Personal Access Token
git remote set-url origin https://USERNAME:TOKEN@github.com/skyt19/PythonXAU.git

# Or use SSH
git remote set-url origin git@github.com:skyt19/PythonXAU.git
```

### If Push Fails (Divergence)

```bash
# Fetch and inspect
git fetch origin
git log HEAD..origin/claude/end-to-end-build

# Integrate safely (rebase OR merge, never force)
git rebase origin/claude/end-to-end-build
# OR
git merge origin/claude/end-to-end-build

# Then push
git push origin claude/end-to-end-build
```

### If Accidentally Committed Secret

```bash
# DO NOT PUSH
# Remove from staging
git reset HEAD~1

# Remove secret from file
# Edit .env.example instead

# Create new commit without secret
git add -A
git commit -m "Fix: Remove accidental secret"
```

---

## Verification

### Verify Local Commits

```bash
# Show recent commits
git log --oneline -10

# Show current branch and HEAD
git branch -v
```

### Verify Remote Backup

```bash
# Check remote branches
git ls-remote origin

# Verify specific commit exists remotely
git ls-remote origin | grep <commit-hash>

# Check remote branch status
git fetch origin
git log origin/claude/end-to-end-build --oneline -5
```

### Verify No Secrets

```bash
# Search for common secret patterns
git log -p | grep -i "password" && echo "WARNING: Found password"
git log -p | grep -i "MT5_LOGIN" && echo "WARNING: Found login"

# Check current tracked files
git ls-files | grep -E "\.env$|\.key$|\.pem$|credentials"
```

---

## Checkpoint Metadata

Each checkpoint commit includes:
- Phase number and name
- What was implemented/tested
- Test results summary
- Blockers (if any)
- Co-Authored-By: Claude <noreply@anthropic.com>

Example commit message:
```
Phase 2: MT5 Data Collection - Read-Only Mode

✅ Implemented
- app/data/collector.py: Resumable M15 OHLC collection
- app/data/storage.py: Database persistence
- MT5 connection with account verification
- Duplicate detection and gap reporting

✅ Tests
- 12 unit tests PASS
- 6 integration tests PASS
- Account guard safety tests PASS

📊 Data Collection
- Symbol: XAUUSD
- Timeframe: M15
- Collected: 2024-01-01 to 2024-12-31 (XX,XXX bars)
- Gaps: X identified
- Validation: PASS

⚠️ Blockers
- None

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Recovery Scenarios

### Lost Network During Push

1. Work continues locally
2. All commits preserved
3. When network returns:
   - `git fetch origin`
   - `git push origin claude/end-to-end-build`

### Need to Restart from Clean State

```bash
# Clone fresh copy
git clone https://github.com/skyt19/PythonXAU.git pythonxau-fresh
cd pythonxau-fresh

# Checkout development branch
git checkout claude/end-to-end-build

# Install dependencies
pip install -r requirements.txt

# Copy .env (do not commit)
cp .env.example .env
# Edit .env with actual credentials
```

### Rollback to Previous Checkpoint

```bash
# View history
git log --oneline -20

# Create rollback branch
git checkout -b rollback/<commit-hash>
git reset --hard <commit-hash>

# Verify
python -m pytest tests/
python -m app.main  # Test startup

# If good, can merge back
git checkout claude/end-to-end-build
git merge rollback/<commit-hash>
```

---

## Status Reporting

Every push updates `PROJECT_STATUS.md` with:

```markdown
## GitHub Backup Status

**Remote**: https://github.com/skyt19/PythonXAU  
**Branch**: claude/end-to-end-build  
**Local HEAD**: <commit-hash> (<message>)  
**Remote HEAD**: <commit-hash> (<message>)  
**Last Push**: 2026-10-29 23:45 UTC  
**Push Status**: ✅ SUCCESS / ⏳ PENDING / ❌ FAILED  
**Verification**: Remote commit confirmed via git ls-remote  
**Excluded**: .env, *.db, logs/*.log (see .gitignore)  
```

---

## Safe Practices

### Always
- ✅ Review `git diff` before commit
- ✅ Check `.gitignore` includes secrets
- ✅ Use descriptive commit messages
- ✅ Run tests before push
- ✅ Fetch before push
- ✅ Verify remote after push

### Never
- ❌ `git push --force`
- ❌ Commit `.env` files
- ❌ Commit credentials
- ❌ Delete remote branches
- ❌ Rewrite published history
- ❌ Push without testing

---

## Integration with PROJECT_STATUS.md

The GitHub Backup Status section in `PROJECT_STATUS.md` is automatically updated after each push, showing:
- Current branch
- Local and remote HEAD commits
- Last successful push timestamp
- Verification status
- Excluded file patterns

---

**Last Updated**: 2026-10-29  
**Document Version**: 1.0
