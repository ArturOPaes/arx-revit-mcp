# -*- coding: utf-8 -*-
"""Job tools — one undo for a whole job, and the rehearsal.

Without these, the routes registered in `revit_mcp/job_routes.py` are
unreachable: the agent has no way to open a group even if it wanted to. A
reviewer measured exactly that — twenty-two tool modules registered, and none
exposing the three routes — and it is the plainest form of "built and
unreachable" there is.
"""

from mcp.server.fastmcp import Context

from .utils import format_response


def register_job_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register the transaction-group tools with the MCP server."""
    _ = revit_get, revit_image  # Acknowledge unused parameters

    @mcp.tool()
    async def begin_job(
        job_id: str,
        dry_run: bool = False,
        ctx: Context = None,
    ) -> str:
        """Open one undo group for everything you are about to do.

        Call this BEFORE the first change. Every write between here and
        commit_job becomes a single undo entry in Revit, so the whole job can
        be taken back at once instead of change by change.

        Set dry_run to rehearse: the work runs for real and is undone at the
        end, and commit_job answers with the full report of what WOULD have
        changed. Nothing stays in the model. Careful — a rehearsal executes:
        anything that leaves the model (an exported file, a reloaded link, a
        print) already left, and the report names those.

        Starting a job while another is still open discards the one left open,
        and the answer says which.

        Args:
            job_id: the identifier of this piece of work
            dry_run: rehearse instead of keeping the changes
            ctx: MCP context for logging
        """
        data = {"job_id": job_id, "dry_run": dry_run}
        return format_response(await revit_post("/begin_job/", data, ctx))

    @mcp.tool()
    async def commit_job(job_id: str, ctx: Context = None) -> str:
        """Close the job, keeping what was done — one undo entry in Revit.

        For a rehearsal, this undoes everything and returns the report of what
        would have changed.

        Refuses if no job is open, or if the open one is not this one:
        assimilating someone else's group would make the wrong job's work
        permanent.

        Args:
            job_id: the same identifier passed to begin_job
            ctx: MCP context for logging
        """
        return format_response(await revit_post("/commit_job/", {"job_id": job_id}, ctx))

    @mcp.tool()
    async def abort_job(job_id: str, ctx: Context = None) -> str:
        """Undo everything this job did, in one go.

        Use it when a step fails and leaving half the work in the model would
        be worse than leaving none of it.

        Args:
            job_id: the same identifier passed to begin_job
            ctx: MCP context for logging
        """
        return format_response(await revit_post("/abort_job/", {"job_id": job_id}, ctx))
