# Repository Guidelines

## Project Structure & Module Organization

This repository packages `spacemit-ai-gateway`, a Python 3.10+ FastAPI gateway for ASR, TTS, VAD, Vision, LLM, Embed, and Rerank services. Source lives under `src/spacemit_ai_gateway/`. The main app and CLI are in `app/`, shared utilities are in `common/`, gateway-wide auth/health/error helpers are in `gateway/`, and domain implementations are in `domains/{asr,tts,vad,vision,llm,embed,rerank}/` with the usual `api.py`, `service.py`, `schemas.py`, and `adapters/` layout. Runtime YAML lives in `configs/` and bundled fallback config lives in `src/spacemit_ai_gateway/configs/`. Tests are under `tests/unit`, `tests/integration`, and `tests/ws`. The frontend is static: `frontend/console/` contains the React console loaded by `index.html`, and `frontend/` contains the landing page. Debian packaging metadata lives in `debian/`; the package ships through SpacemiT's internal apt repo (see the Debian Packaging & Release section below).

## Build, Test, and Development Commands

- `pip install -e ".[dev]"`: install the package and pytest/dev dependencies.
- `uvicorn spacemit_ai_gateway.app.main:app --reload --host 0.0.0.0 --port 18790`: run the backend locally.
- `spacemit-ai-gateway`: run the installed CLI entry point.
- `SPACEMIT_AI_GATEWAY_CONFIG=configs/dev.yaml spacemit-ai-gateway`: run with development config.
- `cd frontend/console && python3 -m http.server 8326`: serve the static console; there is no npm build step.
- `python -m build --wheel`: build a distributable wheel in `dist/`.

## Coding Style & Naming Conventions

Use 4-space indentation, type hints, and async-first I/O patterns consistent with FastAPI, `httpx`, `aiosqlite`, and `asyncio`. Keep domain code inside the relevant `domains/<name>/` package and preserve the route/service/adapter split. Pydantic models belong in `schemas.py`; backend implementations belong in `adapters/`. Use snake_case for modules, functions, variables, config keys, and test names.

## Testing Guidelines

Run `pytest tests/` before submitting broad changes. Use focused commands while iterating, such as `pytest tests/unit/`, `pytest tests/integration/`, or `pytest tests/ws/`. Name tests `test_*.py` and prefer fake backends or fixtures from `tests/conftest.py` for unit coverage.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit-style subjects such as `feat(console): ...`, `fix(vision): ...`, `docs: ...`, and `chore: ...`. Keep subjects imperative and scoped when useful. Pull requests should describe the behavior change, list validation commands run, link related issues, and include screenshots or short recordings for frontend changes.

## Security & Configuration Tips

Do not commit local secrets or ignored runtime files such as `configs/ip_whitelist.txt`, `uv.lock`, or local test notes. Prefer environment overrides with the `SPACEMIT_AI_GATEWAY_` prefix for machine-specific settings.

## Debian Packaging & Release

The package is published to SpacemiT's internal apt repo and the release tooling lives in a separate repo (`bianbu-devscripts`). **Do not hand-roll `dpkg-buildpackage` for releases or push tags by guesswork** — use the flow below.

### One-time setup

```bash
# Clone the release tooling repo (always required)
git clone -b main https://gitlab.dc.com:8443/bianbu/bianbu-devscripts.git ~/bianbu-devscripts

# Install scripts dependencies — SKIP on lnode1 / snode1 / snode5 / SW-Station (already preinstalled)
cd ~/bianbu-devscripts
sudo apt-get update
./install-scripts-depends.sh

# Add to PATH (always required) — bash
echo 'export PATH=$PATH:~/bianbu-devscripts' >> ~/.bashrc && source ~/.bashrc
# Or zsh
echo 'export PATH=$PATH:~/bianbu-devscripts' >> ~/.zshrc && source ~/.zshrc

# Configure default distribution / environment (always required)
bianbu-dev set-default-dist bianbu-26.04
bianbu-dev set-default-dist bianbu
bianbu-dev set-default-env bianbu-scripts-env-1.9.1
```

### Daily code changes (no release)

Just `git commit && git push origin main`. Do not touch `packaging/main` and do not run `bianbu-dev tag`. CI does not rebuild the `.deb` until someone pushes a new tag, so plain main pushes are free.

### Release flow (only when a real version bump is intended)

**Confirm with the change requester that an actual release is needed before doing this.** Tagging is not "save my work"; every tag triggers a CI build that uploads to the internal apt repo.

1. Make source changes, commit, push to `main`.
2. Build the `.deb` locally on a build host (e.g. snode5):
   ```
   dpkg-buildpackage -us -uc -b -Zxz
   ```
3. Smoke-test the produced `.deb` on K3:
   ```
   sudo apt install ./spacemit-ai-gateway_*.deb
   systemctl is-active spacemit-ai-gateway spacemit-ai-gateway-frontend
   journalctl -u spacemit-ai-gateway -n 50 --no-pager
   ```
4. Sync the packaging branch — **mandatory**, CI checks out `packaging/main`, not `main`:
   ```
   git branch -f packaging/main main
   git push origin packaging/main
   ```
5. Generate the next tag with the helper (don't `git tag` manually — the helper writes `debian/changelog` and computes the next version):
   ```
   bianbu-dev tag
   ```
6. Push the tag to trigger the GitLab pipeline that builds and uploads to the apt repo:
   ```
   git push origin bianbu/<new-version>     # e.g. bianbu/0.0.3
   ```

If you skip step 4, the pipeline will check out a stale `packaging/main` and silently rebuild an old version of the source. `bianbu-dev tag` does not sync `packaging/main` for you.

### What the `.deb` does on install

The package's `postinst` creates `/opt/spacemit-ai-gateway/venv` and pip-installs the SpacemiT wheels (`spacemit-asr/tts/vad/audio/vision` and `spacemit-ai-gateway`) from the internal PyPI; `dh_installsystemd` registers and starts both `spacemit-ai-gateway.service` (:18790, backend) and `spacemit-ai-gateway-frontend.service` (:8326, static console). When installed via `sudo` from a non-root user, postinst writes a systemd drop-in switching `User=` and `HOME=` to that user, so model caches land in the invoker's `~/.cache/models/` instead of `/root/.cache/`. `apt remove` cleans up the venv and drop-in directories; `apt purge` wipes everything under `/opt/spacemit-ai-gateway/`. Frontend assets are shipped via `debian/spacemit-ai-gateway.install`; system apt deps are declared in `debian/control` Depends.
