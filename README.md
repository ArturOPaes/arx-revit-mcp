# Revit MCP Server

MCP server for Autodesk Revit 2024/2025/2026/2027 via pyRevit — 48 tools for building design, editing, analysis, clash detection, MEP, interop, documentation, and model persistence.

Works with any MCP client: Claude Desktop, Claude Code, Cursor, Windsurf, Copilot, or any other MCP-compatible application.

## How It Works

```
AI Client ──stdio/SSE/HTTP──> MCP Server (Python/FastMCP) ──HTTP :48884──> pyRevit Routes ──> Revit API
```

The MCP server runs on your machine and communicates with Revit through pyRevit's Routes API. Any MCP-compatible AI client can connect to it.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Windows 10/11** | Revit is Windows-only |
| **Autodesk Revit** | 2024, 2025, 2026, or 2027 |
| **pyRevit** | Installed and loaded in Revit |
| **uv** | Python package manager ([install](https://docs.astral.sh/uv/getting-started/installation/)) |
| **A project open in Revit** | Tools require an active document |

## Install pyRevit (if not already installed)

pyRevit is a free add-in that lets scripts run inside Revit. This MCP server needs it to communicate with Revit.

1. Go to https://github.com/pyrevitlabs/pyRevit/releases
2. Download the latest **.exe installer** (e.g. `pyRevit_CLI_x.x.x.x_admin_signed.exe`)
3. Run the installer — accept all defaults, click **Next** through each screen
4. Open (or restart) Revit — you should see a **pyRevit** tab in the ribbon at the top
5. In the pyRevit tab, click **Settings** (gear icon)
6. In the Settings window, go to the **Routes** section on the left
7. Check the box to **Enable Routes Server**
8. Click **Save Settings** and let pyRevit reload

To verify: open a browser and go to `http://localhost:48884/` — you should see a response (not a "connection refused" error).

## Quick Start

### Step 1: Clone and install

```bash
git clone https://github.com/Demolinator/revit-mcp-server.git
cd revit-mcp-server
uv sync
```

### Step 2: Install the pyRevit extension

The `revit_mcp/` folder and `startup.py` need to run inside Revit via pyRevit.

**Option A — Install from pyRevit (recommended):**

1. In Revit, go to pyRevit tab > Extensions
2. Find "MCP Server for Revit Python" > Install
3. Wait for pyRevit to reload

**Option B — Manual install:**

1. Copy the entire repo folder to `%APPDATA%\pyRevit\Extensions\`
2. Rename the folder to `mcp-server-for-revit-python.extension`
3. In Revit, go to pyRevit tab > Settings > Custom Extensions
4. Add the path to the `.extension` folder
5. Reload pyRevit (or restart Revit)

### Step 3: Activate pyRevit Routes

1. In Revit, go to pyRevit tab > Settings
2. Navigate to Routes > activate **Routes Server**
3. pyRevit will start listening on `http://localhost:48884/`

### Step 4: Verify connection

Open a browser and go to:

```
http://localhost:48884/revit_mcp/status/
```

You should see:

```json
{
  "status": "active",
  "health": "healthy",
  "revit_available": true,
  "document_title": "your_project_name",
  "api_name": "revit_mcp"
}
```

### Step 5: Start the MCP server

```bash
uv run main.py
```

That's it. Your AI client can now connect.

## Connecting Your AI Client

### Claude Desktop / Claude Code

Add to your MCP config:

```json
{
  "mcpServers": {
    "revit": {
      "command": "uv",
      "args": ["run", "main.py"],
      "cwd": "/path/to/revit-mcp-server"
    }
  }
}
```

### Cursor / Windsurf / Other MCP Clients

Use HTTP transport:

```bash
uv run main.py --streamable-http
```

Then configure your client to connect to `http://localhost:8000/mcp`.

### Transport Modes

| Flag | Transport | Endpoints | Use Case |
|------|-----------|-----------|----------|
| *(none)* | stdio | stdin/stdout | Claude Desktop / Claude Code |
| `--sse` | SSE | `/sse`, `/messages/` | Legacy clients |
| `--streamable-http` | HTTP | `/mcp` | HTTP-based clients |
| `--combined` | Both | All above | Maximum compatibility |

### Testing with MCP Inspector

```bash
mcp dev main.py
```

Then open `http://127.0.0.1:6274` in your browser.

## Supported Tools (48)

### Create (15)

| Tool | Description |
|------|-------------|
| `create_level` | Create new levels with elevations |
| `create_line_based_element` | Create walls, beams, and other line-based elements |
| `create_surface_based_element` | Create floors, roofs, and surface elements |
| `place_family` | Place a family instance at specified location |
| `create_grid` | Create column grid lines |
| `create_structural_framing` | Create structural beams and framing |
| `create_sheet` | Create new drawing sheets |
| `create_schedule` | Create schedules with custom fields |
| `create_room` | Create rooms at specified levels |
| `create_room_separation` | Create room separation boundary lines |
| `create_duct` | Create ducts between two points (MEP) |
| `create_pipe` | Create pipes between two points (MEP) |
| `create_mep_system` | Create mechanical or piping systems |
| `create_detail_line` | Create view-specific detail lines |
| `create_view` | Create floor plans, sections, elevations, 3D views |

### Query (12)

| Tool | Description |
|------|-------------|
| `get_revit_status` | Check if the API is active and responding |
| `get_revit_model_info` | Get model information |
| `list_levels` | Get all levels with elevations |
| `list_families` | Get available family types |
| `list_family_categories` | Get all family categories |
| `get_revit_view` | Export a view as an image |
| `list_revit_views` | List all exportable views |
| `get_current_view_info` | Get active view details |
| `get_current_view_elements` | Get elements in current view |
| `get_selected_elements` | Get currently selected elements |
| `list_category_parameters` | List parameters for a category |
| `get_element_properties` | Get all parameters and properties of an element |

### Modify (8)

| Tool | Description |
|------|-------------|
| `delete_elements` | Delete elements from the model |
| `modify_element` | Modify element parameter values |
| `color_splash` | Color elements by parameter values |
| `clear_colors` | Reset element colors |
| `tag_walls` | Tag all walls in current view |
| `set_parameter` | Set a single parameter value on an element |
| `tag_elements` | Tag specific elements with annotation symbols |
| `transform_elements` | Move, copy, rotate, or mirror elements |
| `set_active_view` | Switch the active view in Revit |

### Analyze (5)

| Tool | Description |
|------|-------------|
| `ai_element_filter` | Filter elements by category and parameters |
| `export_room_data` | Export room areas, volumes, boundaries |
| `get_material_quantities` | Material takeoff data |
| `check_clashes` | Detect hard clashes (interferences) between disciplines, e.g. structure vs MEP |
| `analyze_model_statistics` | Element counts and model stats |

### Document (3)

| Tool | Description |
|------|-------------|
| `create_dimensions` | Create dimension annotations |
| `export_document` | Export views to PDF or image |

### Interop & Persistence (4)

| Tool | Description |
|------|-------------|
| `export_ifc` | Export model to IFC format (IFC2x3/IFC4) |
| `link_file` | Link or import DWG, DXF, DGN, SAT, SKP, 3DM, or RVT files |
| `load_family` | Load a Revit family (`.rfa`) from disk so its types can be placed |
| `save_document` | Save / Save-As the model to disk (persistence across sessions) |

### Advanced (1)

| Tool | Description |
|------|-------------|
| `execute_revit_code` | Execute IronPython code in Revit context |

## Architecture

Two runtimes communicate over HTTP:

| Component | Runtime | Location | Purpose |
|-----------|---------|----------|---------|
| `main.py` + `tools/` | Python 3.11+ (CPython) | Your machine | MCP protocol, tool definitions |
| `startup.py` + `revit_mcp/` | IronPython 2.7 (inside Revit) | Revit process | pyRevit route handlers, Revit API |

## Multi-Version Revit Support

This server supports Revit 2024, 2025, 2026, and 2027 through centralized helper functions that handle the ElementId API differences across versions:

- `get_element_id_value()` — Extracts integer IDs using `.Value` (2024+) with `.IntegerValue` fallback
- `make_element_id()` — Creates ElementIds using `System.Int64` (2024+) with `int` fallback

No configuration needed — version detection is automatic via try/except at runtime.

> **Revit 2027 note:** Revit 2027 runs on **.NET 10** (vs .NET 8 in 2025/2026). This MCP server is pyRevit-based, so .NET compatibility is handled by pyRevit itself — ensure you run a **pyRevit build with Revit 2027 support**. None of the 48 tools use APIs removed in 2027 (AXM/FormIt import, `Mechanical.Zone` members, legacy rebar creation, or the dropped `EnergyDataSettings` properties).

## Unit Handling

All tools accept **millimeters (mm)**. The server converts to Revit's internal feet.

| From | To mm |
|------|-------|
| meters | x 1000 |
| feet | x 304.8 |
| inches | x 25.4 |

## Creating Your Own Tools

Adding a new tool requires 2 files + 2 registration lines:

1. **Route handler** in `revit_mcp/new_module.py` (IronPython 2.7)
2. **Tool definition** in `tools/new_tools.py` (Python 3.11+)
3. **Register routes** in `startup.py`
4. **Register tools** in `tools/__init__.py`

See `LLM.txt` for full context that helps AI assistants understand the codebase.

## Contributing

Contributions are welcome! Feel free to submit pull requests or open issues.

## Author

**Talal Ahmed**

## License

MIT

## The write report (`changes_report`) — contract

**Eight** of the 30 routes that change the model return a `changes_report`
object today, and the MCP relays it untouched. The other twenty-two are debt,
listed in `tests/test_rotas_que_relatam.py`, and that test fails if the list
grows or if one of the eight stops reporting.

The first version of this paragraph said 26, because the inventory only looked
for `Transaction(` inside the handler — missing transactions opened in a
helper, and routes that write to disk or pull things into the model without a
transaction at all. A reviewer measured it. An undercounted debt is worse than
a large one: nobody knows the size of the hole.

This paragraph used to say *"every route that changes the model returns a
`changes_report`"*. It was false when written — a reviewer measured — and it is
the most expensive kind of false line, because whoever reads it stops
checking. A route that writes and does not report sums to zero in a rehearsal,
and the architect approves a plan that never mentions what is about to happen.
relays it untouched. It is what the ARCHITECTUS approval gate decides on, and
what the conformity check reads before quoting a standard back at the
architect — so the shape is fixed, and it is fixed on the server side
(`cli/src/cad_env.rs`, `conformidade.Ambiente`).

```json
{
  "created":  ["<element id>"],
  "modified": ["<element id>"],
  "deleted":  ["<element id>"],
  "measurements": {
    "ambientes": [
      {
        "id": "sala-01",
        "nome": "Suíte",
        "uso": "dormitorio",
        "medicoes": {
          "area_piso_m2": {"valor": 12.5, "procedencia": "medida_pela_ponte"},
          "iluminacao":   {"valor": 1.5, "base": 12.5, "bruta": "1.5 m² / 12.5 m²",
                           "procedencia": "medida_pela_ponte"}
        }
      }
    ]
  }
}
```

Build it with `revit_mcp.changes.ChangeReport`, never by hand:

```python
from revit_mcp.changes import ChangeReport

report = ChangeReport()
report.created(new_ids).modified(changed_ids)
report.room(room.Id, "dormitorio", {"area_piso_m2": area}, nome=room.Name)
return routes.make_response(data={"success": True, "changes_report": report.to_dict()})
```

Three rules that are not obvious, and that the tests hold:

- **The four top-level keys are always present**, empty when nothing changed.
  A missing key reads as "the route forgot"; an empty list says "I changed
  nothing". The gate treats those differently.
- **`procedencia` is stamped by this module and cannot be set by the caller.**
  `medida_pela_ponte` means the number was read from the model through the
  Revit API. The server's other value, `declarada_pelo_agente`, is what a
  number written by the agent in the workdir gets — and the whole point of
  this contract is that the two must never be confusable. A route that returns
  a number it did not measure must not put it here.
- **`measurements.ambientes` is omitted when the route measures no rooms.** An
  empty list would read as "I looked and found none", which the conformity
  check records as a gap.

What none of this proves: that Revit accepted the operation. The suite runs
without Revit; the report is only as true as the API call that produced it.

> **Why `changes_report` and not `changes`.** `set_parameter` already returned
> a `changes` field meaning "the parameters that changed on this element".
> Reusing the name would have silently overwritten one with the other. The
> report gets the unambiguous name; the domain field keeps its own.

## One undo for a whole job

Every route opens its own transaction and commits — twenty-eight of them
across sixteen files. If the agent makes eight calls and the sixth fails, the
first five are already in the model.

`DB.TransactionGroup` wraps the lot: the inner transactions still commit, and
the *group* can be rolled back afterwards. Three routes drive it:

| route | body | what Revit does |
|---|---|---|
| `POST /begin_job/` | `{"job_id": "..."}` | starts the group |
| `POST /commit_job/` | `{"job_id": "..."}` | `Assimilate()` — the job becomes one undo entry |
| `POST /abort_job/` | `{"job_id": "..."}` | `RollBack()` — the whole job is undone |

Rules that are decisions, not details:

- **A begin for a *different* job discards the one left open**, and the answer
  says which job was discarded, by name. Someone will need to know why the
  model went back.
- **A repeated begin for the same job discards nothing.** It is not a new job;
  it is the previous answer that got lost on the way back.
- **Commit or abort naming a job that is not the open one is refused** (409).
  Assimilating someone else's group would make the wrong job's work permanent.
- **Commit with nothing open is a refusal, not a quiet success.** The gate
  would otherwise read "committed" and believe a group wrapped the work.
- **There is no timer.** If the agent dies mid-job, nothing runs on its own —
  the next begin cleans up. The cost is real and stated: a model can sit with
  an open group until someone calls again.

The deciding lives in `revit_mcp/job_group.py`, which imports nothing from
Revit and is covered on any machine. `job_routes.py` is three Revit calls and
the plumbing.

### Rehearsal (dry run)

`POST /begin_job/` with `{"job_id": "...", "dry_run": true}` runs the job for
real and rolls the group back at the end. `commit_job` then answers with the
accumulated `changes_report` — what *would* have changed — and nothing
persists in the model.

This is what turns the ARCHITECTUS approval plan from prose the agent wrote
into a report of an execution that actually happened. The format is the same
as a real run, so the screen the architect reads does not change.

**A rehearsal is neither free nor harmless: it executes.** A `RollBack` undoes
the model, not the world. Anything that left the model already left — an
exported file is on disk, a reloaded link points where it now points, a print
job has printed. The report names those under `not_undone`, and the field is
absent when nothing escaped, so it never becomes noise people learn to skip.

What the suite proves: the accumulation, the deduplication across calls, that
a rehearsal rolls back instead of assimilating, that the mode never leaks into
the next job, and that the warnings appear by name. What it does not prove:
that Revit assimilates or rolls a group back. That needs Revit.
