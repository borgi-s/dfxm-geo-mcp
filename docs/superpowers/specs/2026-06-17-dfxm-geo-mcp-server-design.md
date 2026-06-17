# dfxm-geo MCP server design

Date: 2026-06-17
Repo: `dfxm-geo-mcp` (new standalone repo; depends on `dfxm-geo>=3.0.0` via pip)
Status: revised after two-reviewer spec review (2026-06-17); ready to plan, with one
author decision flagged in section 16.

## 0. Revision log (what the spec review changed)

Two parallel reviewers (feasibility-vs-codebase and MCP-design) ran against the
v1 draft. The material changes folded in here:

- **Analytic backend is the preview default (was: ship a blessed MC kernel).**
  The feasibility review confirmed `[reciprocal] backend="analytic"` with
  `beamstop=false` renders a preview in ~0.14-0.30 s with **no kernel file and no
  bootstrap** (verified live). Real MC kernels are **128 MB** (set by the
  400x200x200 grid, independent of ray count), so shipping one in a wheel was
  never viable. The analytic default dissolves the kernel-wheel problem, the
  money-shot wait, and the feasibility risk together. This **reverses the
  grill-time "ship one small blessed kernel" decision**, which was made on the
  false premise that preview kernels are small.
- **MC bootstrap survives as an opt-in high-fidelity path** and remains the
  async-job-handle showcase (the roadmap's named centerpiece). Because the
  analytic default gives a complete demo on its own, the whole MC/bootstrap arm
  is a clean v1.5/v2 cut line if the sprint runs long (section 16).
- **FastMCP foundation: standalone `fastmcp>=3`, not `mcp[cli]`.** The bundled
  `mcp.server.fastmcp` is the frozen FastMCP 1.0; the in-memory test `Client` and
  the `Image` return type the design leans on are standalone-v3 features. (mcp
  SDK is 1.28.0 as of June 2026; the installed `build-mcp-server` skill warns
  about exactly this trap.)
- **`run_forward` gets its image via a temp HDF5 read-back**, not in-memory:
  `run_simulation` renders frames straight into HDF5 and returns `Hg`/`q_hkl`,
  not the detector image. Running to a temp dir and reading
  `/1.1/instrument/dfxm_sim_detector/data` back reuses all validated plumbing.
- Smaller corrections: `validate_config` must catch four exception types; the
  loader is `SimulationConfig.from_toml(path: Path)` (write text to a temp file);
  kernel lookup uses a hardcoded source-tree path (`fm.pkl_fpath`) that breaks on
  pip installs and must be monkeypatched to the cache dir; preview caps are
  runtime knobs (`Npixels`, `Nsub`, frame count), not a ray count; the
  `detector.apply()` OOM is already chunk-mitigated; tool annotations + a server
  `instructions` line + stdio stdout discipline + inline-image size caveat are
  added; `NUMBA_CACHE_DIR` must point at a writable dir so the JIT cache persists.

## 1. Motivation

`dfxm-geo` is a TOML-driven forward model for dark-field X-ray microscopy with
seven console entry points (`dfxm-init`, `dfxm-find-reflections`,
`dfxm-bootstrap`, `dfxm-forward`, `dfxm-identify`, two migrators). A new user
faces a real onboarding cliff: which `[crystal]` / `[geometry]` / `[scan]` /
`[detector]` blocks to set, which reflections a given mount and energy can even
reach, the kernel dependency for MC-fidelity runs, and a set of non-obvious edge
cases (oblique geometry needs an exact eta; HCP (0002) is not Laue-reachable in
the standard mount; the non-FCC poisson-ratio gate raises).

This project builds an MCP server that lets an AI client (Claude Desktop,
Cursor, anything speaking MCP) *drive* `dfxm-geo`: validate a config, enumerate
reachable reflections, scaffold a starting config, and run a preview-scale
forward simulation that returns a rendered image. The server is execution
centered: the "help a confused scientist" value is a byproduct of correct,
richly described, real tools, not a separate documentation-retrieval feature.

Two audiences, in priority order:

1. **Primary: AI-engineer / builder reviewers.** This is the portfolio
   centerpiece for the fallback branch of the autonomous-DFXM career roadmap
   (`C:\Users\borgi\autonomous-dfxm-pitch-roadmap.md`, line 86: "build the
   dfxm-geo MCP server (1-2 weeks; tool schemas, async long-running jobs, HDF5
   resources)"). What earns signal: clean typed tool schemas, a correct async
   long-running-job pattern, use of all three MCP primitives (tools, resources,
   prompts), a real test suite, and a one-command run story.
2. **Secondary: working scientists**, reached through their MCP client. Served
   automatically if the tools are correct and self-describing.

**Dual-use note.** The four operations this server wraps (validate, find
reflections, scaffold, run forward) are the same primitives the autonomous-DFXM
measurement loop would import in-process if the main pitch lands. Building them
as a clean, importable ops layer means nothing is wasted either way. This is an
architecture consequence, not extra scope (section 5).

## 2. Goals and non-goals

### Goals

- A plain-Python **ops layer** (no MCP knowledge) wrapping four `dfxm-geo`
  operations: `validate_config`, `find_reflections`, `scaffold_config`,
  `run_forward`. Fully unit-testable in isolation.
- A **thin FastMCP adapter** (standalone `fastmcp>=3`) exposing those as MCP
  tools, plus a generic **async job engine** for the one genuinely long
  operation (MC kernel bootstrap).
- `run_forward` defaults to the **analytic backend** (no kernel, sub-second),
  returns a **rendered PNG inline** (MCP image content) plus numeric metadata,
  **hard-bounded to preview scale**, with numba JIT **pre-warmed** at server
  startup so the common path is snappy. An optional `fidelity="mc"` mode uses a
  Monte-Carlo kernel (built on demand via the async bootstrap job).
- A small curated **knowledge layer**: three resources (annotated config schema,
  a handful of example configs, the list of cached kernels) and two prompts
  (guided forward simulation; diagnose a failing config).
- **Structured errors**: `validate_config` and `run_forward` return
  `{block, field, problem, fix}`-shaped objects, never stringly-typed blobs, and
  never let an exception escape to the transport.
- MC kernels for non-default reflections are **built on demand** through the
  async bootstrap job and **cached on disk** (`platformdirs` user cache dir). No
  kernel is shipped in the wheel.
- **Local stdio** transport (the canonical MCP shape), built on FastMCP so an
  HTTP transport is a later one-line flip.
- Published to **PyPI** with a `uvx dfxm-geo-mcp` run story plus a Claude Desktop
  config snippet. README leads with the `run_forward` money-shot screenshot.
- Test-first ops layer + **in-memory MCP integration tests** (FastMCP `Client`
  over in-memory transport, no live client needed).

### Non-goals (v1)

- **`run_identify`.** Needs a candidate library + a target image + matching
  machinery; heavier, worse first-touch. Deferred to v2, stated in the README.
- **The autonomous-loop pieces** (cross-correlation matcher, greedy
  reflection-chooser, stop criterion). They belong to the main pitch, not this
  portfolio piece. Hard guardrail: if a "pick the next best reflection" tool
  appears, scope has drifted.
- **Shipping a kernel in the wheel** (128 MB; unnecessary given the analytic
  default).
- **Remote HTTP transport, hosting, auth.** FastMCP keeps the door open; no paid
  endpoint is stood up. The capability is documented, not deployed.
- **A docs-RAG / semantic-search layer over `docs/`.** Low portfolio signal; the
  agent can already read the repo. Resources stay curated and small (section 10).
- **A fake / canned "demo mode".** It would undercut real-execution credibility.
  The heavy first-run install (numba/scipy) is documented honestly instead.
- **Production-scale runs.** `run_forward` refuses configs above the preview caps
  and points the user at the CLI on a cluster. No sweeps, no fan-out.
- **An `.mcpb` one-click bundle.** Stretch goal.

## 3. Grounding facts (current `dfxm-geo` surface, verified at v3.0.0)

Verified against the `Geometrical_Optics_master` tree (several confirmed live
through the venv interpreter during spec review).

- **Console scripts + entry points**: exact match to the spec's understanding;
  `[cif]` is a real optional extra, so `dfxm-geo[cif]>=3.0.0` is a valid dep. The
  MCP imports library functions, not these CLIs.
- **Forward config loader**: `dfxm_geo.config.SimulationConfig.from_toml(path:
  Path)` (`config.py:796`). It takes a **Path, not a string** -> the ops layer
  writes `toml_text` to a temp file before calling it. `load_identification_config`
  is the identify-side loader. An empty `.toml` is valid (centered FCC, Al 111 @
  17 keV).
- **Config validation raises in `__post_init__` / `from_dict`** with useful
  messages, across **four** exception types (all confirmed live): `ValueError`
  (range without steps; unknown mode), `KeyError` (missing required field such as
  `b`), `TypeError` (unknown TOML key in a dataclass), `tomllib.TOMLDecodeError`
  (malformed TOML). `validate_config` must catch all four.
- **Find reflections**: `dfxm_geo.crystal.oblique.find_reflections(mount,
  keV, *, theta_range, hkl_max, eta_target, eta_tol) -> list[ReflectionGeometry]`
  (`oblique.py:416`). Each record carries **two** solutions
  (`theta_1/eta_1/omega_1` and `theta_2/eta_2/omega_2`), NaN-filled when
  unreachable. Kernel-sharing "grouping" is done in the **CLI**
  (`find_reflections_cmd.py:95-106`), not the library; the CLI takes solution-1,
  falling back to solution-2 on NaN. The ops layer builds the mount from a parsed
  config via `_crystal_mount_from_toml(crystal_dict)`
  (`reciprocal_space/kernel.py:58`); verified to return 116 reflections for the
  default Al cubic mount @ 17 keV. HCP (0002) returns NaN (not Laue-reachable),
  confirmed live.
- **Config -> TOML**: `_dataclass_to_toml_str(config)` lives in `config.py:1096`
  and is re-exported from `orchestrator`; round-trips through `from_toml`. It does
  **not** emit `[detector]` / `[detector_geometry]` blocks (they default), so
  `scaffold_config` cannot surface those knobs through it -> scaffold emits TOML
  **text directly** (template per structure) and then validates (section 5).
- **`forward()` returns an in-memory numpy image** (`forward_model.py:1039`,
  shape `(NN2//Nsub, NN1//Nsub)`), **but the orchestrator never hands it back**:
  `run_simulation` -> `_run_simulation_inner` renders frames straight into HDF5
  (`write_simulation_h5`) and returns `{"h5_path", "Hg", "q_hkl", ...}`, not the
  image. v1 therefore runs `run_simulation` to a **temp dir** and reads
  `/1.1/instrument/dfxm_sim_detector/data` (uint16, shape `(frames, H, W)`) back
  with h5py (section 8, "Option B"). A truly in-memory path is possible by
  re-plumbing `_run_simulation_inner` (all sub-functions are public on
  `forward_model`) but is ~50-80 lines and forks for wall mode; not v1.
- **Analytic backend needs no kernel**: `[reciprocal] backend="analytic"` with
  `beamstop=false` routes through `_load_analytic_resolution`
  (`orchestrator.py:195-208`, `forward_model.py:620`) and runs **with no kernel
  file**. Verified live: 96-px single frame, cold 0.30 s / warm 0.14 s. NOTE the
  shipped `default.toml` uses `beamstop=true` (forces MC), so the preview path
  must override `beamstop=false`.
- **MC kernel + bootstrap**: `generate_kernel(Nrays, output_path, hkl, keV,
  mount, theta, eta, omega, batch_size)` (`reciprocal_space/kernel.py:514`) is
  library-callable; `dfxm-bootstrap` is a thin wrapper. **~50 s at the default
  `Nrays=1e8`** (documented in `default.toml:23`), one MC fill into a
  400x200x200 histogram. Output npz is **128 MB**, set by the **grid**
  (`400*200*200` float64), **independent of `Nrays`**. So a smaller ray count
  does not shrink the file.
- **Kernel lookup path is a hardcoded source-tree global**: `fm.pkl_fpath =
  str(_REPO_ROOT / "reciprocal_space" / "pkl_files")` (`forward_model.py:111`).
  It is **not** env-configurable and, on a pip/uvx install, points inside
  `site-packages`. To use a `platformdirs` cache, the ops layer must either
  monkeypatch `fm.pkl_fpath` to the cache dir before any orchestrator call, or
  bypass lookup and call `fm._load_default_kernel(explicit_path, expected_hkl,
  expected_keV)` (`forward_model.py:399`) directly. `_lookup_and_load_kernel`
  (`orchestrator.py:100`) globs `Resq_i_h{h}_k{k}_l{l}_{keV}keV_*.npz`, picks
  newest, verifies bundled `hkl`/`keV` metadata, raises `KeyError` on miss.
- **Runtime preview knobs**: the forward ray grid is `NN1*NN2*NN3` derived from
  `Npixels`/`Nsub` (`forward_model.py:136-138`), not a free "ray count". Image
  shape is `(Npixels, ~Npixels//3)`. So preview caps are `Npixels`, `Nsub`, and
  frame count (section 8); there is no `max_rays` runtime knob.
- **`detector.apply()` OOM is already chunk-mitigated**: `apply_in_chunks` +
  `DETECTOR_APPLY_CHUNK_FRAMES=256` (`detector.py:111`,
  `orchestrator.py:1621-1630`). Caps are still good for speed, but the OOM
  justification is stale.
- **Startup costs (honest, for the README)**: cold `import dfxm_geo` ~8.8 s
  (numba/scipy/matplotlib/h5py); true cold numba JIT for the MC forward kernel
  ~2.0 s for one frame. The JIT on-disk cache lives under
  `site-packages/.../__pycache__/*.nbc`; in a read-only/ephemeral `uvx` env it
  may not be writable, so set `NUMBA_CACHE_DIR` to a writable cache dir to make
  `cache=True` persist across runs.

## 4. Repo layout (architecture)

```
dfxm-geo-mcp/
  pyproject.toml          # name=dfxm-geo-mcp; deps: fastmcp>=3, dfxm-geo[cif]>=3.0.0, pillow, platformdirs
  README.md               # money-shot screenshot, uvx one-liner, Claude Desktop snippet, heavy-first-run note
  src/dfxm_geo_mcp/
    __init__.py
    server.py             # FastMCP app: tool/resource/prompt registration + instructions ONLY (thin)
    runtime.py            # startup wiring: NUMBA_CACHE_DIR, fm.pkl_fpath monkeypatch, JIT pre-warm thread, stdout guard
    ops/                  # the plain-Python ops layer (no MCP imports)
      __init__.py
      validate.py         # validate_config
      reflections.py      # find_reflections
      scaffold.py         # scaffold_config
      forward.py          # run_forward (analytic default, bounded) + caps + temp-HDF5 readback + PNG render
      types.py            # ValidationReport, ForwardResult, ReflectionRecord, typed sub-models
    jobs.py               # generic async job engine (registry + background executor + TTL + dedup)
    kernels.py            # cache dir, kernel-presence check, bootstrap driver (MC path only)
    knowledge/
      schema.py           # annotated config schema (generated from dataclasses)
      examples/           # example .toml configs (resources)
  tests/
    test_ops_validate.py
    test_ops_reflections.py
    test_ops_scaffold.py
    test_ops_forward.py
    test_jobs.py
    test_server_integration.py   # in-memory FastMCP Client end-to-end
```

Dependency direction: `server.py` depends on `ops/*`, `jobs.py`, `kernels.py`,
`knowledge/*`, `runtime.py`. The `ops/*` modules depend only on `dfxm_geo` (and
pillow/numpy for the PNG). `jobs.py` depends only on the stdlib. Nothing under
`ops/` imports `fastmcp`; that is what makes the layer reusable by the
autonomous loop and unit-testable without a server.

## 5. The ops layer (`ops/`)

Plain Python, no MCP. Signatures (refined during implementation):

```python
# types.py
@dataclass(frozen=True)
class ConfigIssue:
    block: str; field: str; problem: str; fix: str

class ResolvedSummary(TypedDict):
    scan_mode: str; structure_type: str; reflection: tuple[int, int, int]; backend: str

@dataclass(frozen=True)
class ValidationReport:
    ok: bool; issues: list[ConfigIssue]; resolved: ResolvedSummary | None

@dataclass(frozen=True)
class ReflectionRecord:
    hkl: tuple[int, int, int]
    theta_deg: float; eta_deg: float; omega_deg: float    # chosen solution (sol-1, sol-2 fallback on NaN)
    energy_keV: float; reachable: bool; note: str

class ForwardStats(TypedDict):
    shape: tuple[int, ...]; vmin: float; vmax: float; backend: str
    kernel: str | None; wall_s: float

@dataclass(frozen=True)
class ForwardResult:
    png_bytes: bytes; stats: ForwardStats; bounded: bool

# validate.py
def validate_config(toml_text: str) -> ValidationReport:
    """Write toml_text to a temp file, call SimulationConfig.from_toml, catch
    ValueError / KeyError / TypeError / tomllib.TOMLDecodeError, map each to a
    ConfigIssue with a fix hint. On success, report the resolved summary."""

# reflections.py
def find_reflections(toml_text: str) -> list[ReflectionRecord]:
    """Build the mount via _crystal_mount_from_toml, call
    crystal.oblique.find_reflections, project each two-solution ReflectionGeometry
    to one record (sol-1, sol-2 fallback on NaN), annotate reachability + known
    edge cases (HCP (0002), oblique exact-eta)."""

# scaffold.py
def scaffold_config(*, material=None, structure_type=None, reflection=None,
                    energy_keV=17.0, geometry_mode="symmetric", cif_path=None,
                    scan_mode="single", backend="analytic") -> str:
    """Emit a config as TOML text from a per-structure template (NOT via
    _dataclass_to_toml_str, which omits [detector] and cannot express every
    knob). For non-FCC, include material/poisson_ratio (the non-FCC ny-gate
    raises without them) and, for oblique, the exact eta. Guaranteed to pass
    validate_config (a test enforces the contract)."""

# forward.py
PREVIEW_CAPS = {"max_npixels": 128, "max_nsub": 1, "max_frames": 9}

def run_forward(toml_text: str, *, fidelity="preview", caps=PREVIEW_CAPS) -> ForwardResult:
    """Validate; enforce caps (refuse over-cap with a clear message naming the
    dimension and the CLI alternative). fidelity="preview" forces
    backend="analytic", beamstop=false (no kernel). fidelity="mc" requires a
    cached/blessed kernel; if absent, return a structured needs-bootstrap result
    naming start_bootstrap with the hkl/energy. Run run_simulation to a temp
    dir, read /1.1/instrument/dfxm_sim_detector/data back, max-project multi-frame
    to 2D, render a small PNG, return ForwardResult."""
```

`scaffold_config` -> `validate_config` is always green by contract (a test
enforces it).

## 6. Async job engine (`jobs.py`)

The job-handle pattern (`start_bootstrap` -> `get_job_status` ->
`get_job_result`), used for MC kernel bootstrap (the only >client-timeout
operation). Chosen deliberately over MCP-native blocking-with-progress for three
reasons the spec states explicitly:

1. **Timeout behavior is host-dependent.** MCP progress notifications can act as
   a keepalive in *some* hosts, but the protocol does not guarantee it, so a
   ~50 s+JIT blocking call is fragile across clients.
2. **The result is a durable, cacheable side effect.** The kernel naturally
   outlives a single tool call; a job handle models that, a blocking call does
   not.
3. **Fire-and-come-back.** The user (or agent) can start a bootstrap, do other
   work, and collect it later.

```python
JobState = Literal["pending", "running", "succeeded", "failed"]

@dataclass
class Job:
    id: str; state: JobState; progress: float; message: str
    result: Any | None; error: str | None; key: tuple | None    # dedup key

class JobRegistry:
    def submit(self, key, fn) -> str: ...     # if key has a live job, RETURN its id (dedup)
    def status(self, job_id) -> Job: ...
    def result(self, job_id) -> Any: ...
    def cancel(self, job_id) -> bool: ...      # best-effort; numba work is not cleanly cancellable
    def _evict_expired(self) -> None: ...       # TTL on finished jobs so the registry doesn't leak
```

- One process-wide registry; a small `ThreadPoolExecutor` runs jobs (bootstrap
  releases the GIL in numba; threads keep the in-process kernel cache visible to
  later `run_forward`). `uuid4` job ids.
- **Dedup**: a second `start_bootstrap(hkl, energy)` for an in-flight target
  returns the existing job id (no duplicate ~50 s build).
- **TTL/eviction** on finished jobs so a long-lived server does not leak.
- **Cancellation**: `cancel` is best-effort; the spec states numba work is not
  cleanly interruptible, so a running bootstrap may finish anyway. Documented,
  not hidden.
- Jobs are in-memory; a restart loses them (documented; fine for single-user
  stdio).
- Written generically so a future "larger forward above some cap" could also be
  submitted as a job.

## 7. MCP tool surface (`server.py`)

Thin standalone-FastMCP registrations (`from fastmcp import FastMCP`). Each tool
coerces args, calls an ops function or the registry, shapes a typed result.
Every tool carries **annotations** (`title`, `readOnlyHint`, etc.) and the server
sets a top-level **`instructions`** string; workflow ordering lives in
`instructions`, **not** in tool descriptions (the Anthropic Directory rule treats
"always call X first" in a tool description as prompt injection).

| Tool | Annotations | Kind | Returns |
|---|---|---|---|
| `validate_config(toml_text)` | readOnly, idempotent | inline | `ValidationReport` |
| `find_reflections(toml_text)` | readOnly, idempotent | inline | `list[ReflectionRecord]` |
| `scaffold_config(...)` | readOnly, idempotent | inline | TOML string |
| `run_forward(toml_text, fidelity)` | readOnly (writes only a temp dir) | inline, bounded, analytic-default | PNG image content + `ForwardStats` |
| `start_bootstrap(hkl, energy_keV, ...)` | not readOnly, idempotent, non-destructive | async | `{job_id}` |
| `get_job_status(job_id)` | readOnly | inline | `{state, progress, message}` |
| `get_job_result(job_id)` | readOnly | inline | kernel summary or error string |

`instructions` (example): "A `fidelity='mc'` forward needs a bootstrapped kernel
for its reflection/energy; if `run_forward` reports a missing kernel, call
`start_bootstrap` then poll `get_job_status`. Most previews need only the default
analytic fidelity."

## 8. `run_forward`: backend, bounding, image, pre-warm

- **Default backend = analytic**, `beamstop=false`: no kernel, sub-second. This
  is the money-shot path and works on a fresh install with zero bootstrap.
- **`fidelity="mc"`** uses a Monte-Carlo kernel from the cache; if absent, returns
  the structured needs-bootstrap result (no compute).
- **Bounding**: caps on `Npixels` (<=128), `Nsub` (1), frame count (<=9),
  enforced before compute. Over-cap -> refuse, naming the dimension and pointing
  to `dfxm-forward`. (The `detector.apply()` OOM is already chunk-mitigated; caps
  are for latency, not OOM.)
- **Image extraction (Option B)**: run `run_simulation` to a temp dir, read
  `/1.1/instrument/dfxm_sim_detector/data` (uint16 `(frames, H, W)`) back,
  max-project multi-frame to 2D.
- **Render**: small PNG (128x42-ish at the cap) with a perceptual colormap;
  returned as `fastmcp` `Image(data=png_bytes, format="png")` (the framework
  encodes base64 `ImageContent`). Inline base64 is fine at this size (a few KB);
  if a larger render is ever wanted, use a resource link instead of inline image.
- **JIT pre-warm**: a startup background thread runs one tiny forward through the
  **full population -> Hg -> forward path** (two `@njit` functions need warming:
  `_mc_lut_forward` and `find_hg_population`), so the first real call is fast.
  The server reports ready immediately; a `run_forward` arriving mid-warmup waits
  on it. Pre-warm failures are logged (to stderr), not fatal.

## 9. Kernels and cache (`kernels.py`, `runtime.py`)

- **No kernel shipped.** The analytic preview default needs none.
- **MC kernels built on demand** by `start_bootstrap` (driving `generate_kernel`)
  into a `platformdirs.user_cache_dir("dfxm-geo-mcp")` subtree; discovered on
  later runs.
- Because `fm.pkl_fpath` is a hardcoded source-tree global, `runtime.py`
  **monkeypatches `fm.pkl_fpath` to the cache dir** at startup (or the ops layer
  calls `fm._load_default_kernel(explicit_path, ...)` directly). Without this the
  orchestrator lookup never sees the cache.
- `runtime.py` sets **`NUMBA_CACHE_DIR`** to a writable cache subdir so the JIT
  cache persists across `uvx` runs.

## 10. Resources and prompts (`knowledge/`)

Curated and small (deliberately not the whole docs tree).

- **Resources**:
  - `schema://config` - annotated config schema, **generated from the dataclasses**
    so it cannot drift: every block, field, type, default, one-line meaning.
  - `examples://{name}` - a **resource template** (RFC 6570) with a list callback
    so the host can enumerate the handful of canonical configs (default Al 111,
    oblique, multi-reflection, a BCC, an HCP).
  - `kernels://cached` - the kernels currently in the cache (so the agent knows
    which `fidelity="mc"` runs need a bootstrap job first). Re-read on each access;
    update-subscription is a v2 nicety.
- **Prompts** (arguments are string-only per MCP):
  - `guided_forward_simulation` - scaffold -> validate -> run_forward (analytic);
    bootstrap only if `fidelity="mc"` is asked for.
  - `diagnose_config` - structured triage of a failing config via
    `validate_config` output.

## 11. Error handling

- Bad TOML / bad config: `validate_config` returns `ok=False` with one
  `ConfigIssue` per problem, catching **all four** exception types
  (`ValueError`, `KeyError`, `TypeError`, `tomllib.TOMLDecodeError`). No
  exception escapes.
- `run_forward` over caps: structured refusal (not an exception), naming the
  dimension and the CLI alternative.
- `fidelity="mc"` with no kernel: structured needs-bootstrap result naming
  `start_bootstrap` with the right hkl/energy.
- `get_job_result` on a failed job: returns the captured error string.
- Unexpected errors are caught at the adapter boundary and returned as a
  structured tool error; the server never crashes the stdio connection.
- **stdio discipline**: all logging goes to **stderr** (or MCP logging
  notifications); the forward / bootstrap calls run under a `redirect_stdout`
  guard so chatty numba/scipy prints cannot corrupt the JSON-RPC frame.

## 12. Testing

- **ops/validate**: a valid config reports `ok=True` with the right resolved
  summary; each bad case (range-without-steps -> ValueError; unknown key ->
  TypeError; malformed TOML -> TOMLDecodeError; missing `b` -> KeyError) yields
  the expected `ConfigIssue`.
- **ops/reflections**: the default mount returns expected reachable records; HCP
  (0002) is flagged unreachable; two-solution projection picks sol-1 / falls back
  to sol-2 on NaN.
- **ops/scaffold**: scaffold for FCC/BCC/HCP each round-trips green through
  `validate_config`; non-FCC includes material/poisson_ratio; empty-args scaffold
  equals the documented default.
- **ops/forward**: an analytic preview returns a PNG of the expected shape with
  sane stats and **no kernel present**; an over-cap config is refused; a
  `fidelity="mc"` config with no kernel returns the structured bootstrap pointer.
- **jobs**: submit/status/result lifecycle; dedup returns the same id for an
  in-flight key; TTL evicts finished jobs; a failing worker surfaces as
  `state=failed` with the error.
- **server integration**: drive the FastMCP app through its in-memory `Client`;
  list tools/resources/prompts; assert annotations and the `instructions` string;
  call `validate_config` and `run_forward` (analytic) and assert the
  structured/image results; submit a monkeypatched-fast bootstrap job and poll to
  completion.
- `mypy src/dfxm_geo_mcp/` 0 errors; ruff clean.

## 13. Packaging and distribution

- `pyproject.toml`: name `dfxm-geo-mcp`, console script `dfxm-geo-mcp =
  dfxm_geo_mcp.server:main`. Runtime deps: **`fastmcp>=3.0`** (NOT `mcp[cli]` /
  `mcp.server.fastmcp`, which is the frozen FastMCP 1.0), `dfxm-geo[cif]>=3.0.0`,
  `pillow`, `platformdirs`. Package data: `knowledge/examples/*`.
- **Run story** (README, in order): `uvx dfxm-geo-mcp`, then the Claude Desktop
  `claude_desktop_config.json` snippet, then `pip install dfxm-geo-mcp`. Honest
  "heavy first run" note: ~8.8 s import + a one-time JIT warm; no fake demo mode.
- Published to **PyPI** (name availability checked first). No conda-forge step.
- Standalone repo, clean commit history showing MCP engineering, focused README
  and tests.

## 14. Open items (settle during build, not blocking)

- Exact preview caps in latency terms (pin `Npixels`/`Nsub`/frames so an analytic
  call returns well under a second on a laptop; MC preview separately).
- Whether `fidelity="mc"` ever ships an MC blessed kernel via build-and-cache on
  first run, or stays purely on-demand (analytic default makes this optional).
- Cache directory layout under `platformdirs`.
- Schema-resource generation detail (dataclass introspection coverage).
- `dfxm-geo-mcp` PyPI name availability.
- Threads vs processes for the executor (default threads; revisit only if
  numba/global state leaks across jobs).
- `find_reflections` `hkl_max` / `theta_range` defaults for the MCP (the CLI's
  defaults vs a tighter MCP default to keep result lists short).

## 15. Definition of done (CV-ready)

All five tools + three resources + two prompts work over stdio; the ops layer and
the in-memory MCP integration tests are green; `mypy` 0 / ruff clean; the package
installs and runs via `pip install dfxm-geo-mcp` and `uvx dfxm-geo-mcp`; and the
README leads with a screenshot of Claude Desktop rendering a DFXM image from a
plain-English request. Built as a focused ~2-week sprint (test-first ops layer,
`build-mcp-server` skill as the construction guide, subagent-driven where tasks
are independent).

## 16. Author decision flagged for planning

**Does the MC bootstrap / async-job arm ship in v1, or move to v1.5/v2?**

The analytic default gives a complete, instant, kernel-free demo on its own, so
the entire MC-kernel + `start_bootstrap` + cache + `fm.pkl_fpath` monkeypatch +
128 MB-build machinery is now a **clean, optional arm** rather than load-bearing.

- **Keep it in v1 (recommended):** the async long-running-job pattern is the
  roadmap's literally-named portfolio centerpiece (section 1); dropping it makes
  the server all-inline and removes the single most senior-signal feature. The
  analytic default just means it is opt-in fidelity, not mandatory-for-everything.
- **Cut to v2 if the 2-week clock slips:** because nothing in the money-shot path
  depends on it, this is the natural scope cut. If taken, the README roadmap lists
  MC fidelity + async bootstrap as "next", and v1 ships analytic-only.

Recommendation: plan v1 *with* the MC/async arm, but sequence it last so it is
the cut line if needed.
