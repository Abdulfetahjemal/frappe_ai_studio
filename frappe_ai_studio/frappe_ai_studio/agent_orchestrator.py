# -*- coding: utf-8 -*-
"""Agent Orchestrator — asynchronous generation pipeline with state management.

PILLAR 1: ASYNCHRONOUS AGENT ORCHESTRATION & STATE MANAGEMENT
- Uses frappe.enqueue for background task execution
- Tracks state via AI Generation Task DocType
- Streams progress via frappe.publish_realtime (Socketio)
"""

from __future__ import unicode_literals

import json
import time

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# Stage constants
# ---------------------------------------------------------------------------

STAGE_PENDING = "Pending"
STAGE_IN_PROGRESS = "In Progress"
STAGE_LINTING = "Linting"
STAGE_TESTING = "Testing"
STAGE_COMPLETED = "Completed"
STAGE_FAILED = "Failed"
STAGE_ROLLED_BACK = "Rolled Back"

STAGE_PROGRESS = {
    STAGE_PENDING: 0,
    STAGE_IN_PROGRESS: 10,
    STAGE_LINTING: 40,
    STAGE_TESTING: 70,
    STAGE_COMPLETED: 100,
    STAGE_FAILED: 0,
    STAGE_ROLLED_BACK: 0,
}

# ---------------------------------------------------------------------------
# Public API: enqueue a new generation task
# ---------------------------------------------------------------------------


def enqueue_generation_task(user_prompt, target_app=None, provider=None, model=None, temperature=None, prompt_name="__direct__", conversation_history=None):
    """Create an AI Generation Task and enqueue it for background processing.

    Returns the task document name so the frontend can poll or listen for
    realtime events.
    """
    if not user_prompt:
        frappe.throw(_("User prompt is required"))

    task = frappe.get_doc(
        {
            "doctype": "AI Generation Task",
            "user_request": user_prompt,
            "target_app": target_app or "",
            "status": STAGE_PENDING,
            "progress_percent": 0,
            "current_stage": STAGE_PENDING,
        }
    )
    task.insert(ignore_permissions=True)
    frappe.db.commit()

    # Enqueue the background job on the "long" queue with a 5-minute timeout
    frappe.enqueue(
        method="frappe_ai_studio.frappe_ai_studio.agent_orchestrator._run_generation_pipeline",
        queue="long",
        timeout=300,
        job_id=f"ai-gen-{task.name}",
        task_name=task.name,
        user_prompt=user_prompt,
        target_app=target_app,
        provider=provider,
        model=model,
        temperature=temperature,
        prompt_name=prompt_name,
        conversation_history=conversation_history,
    )

    return task.name


# ---------------------------------------------------------------------------
# Background pipeline
# ---------------------------------------------------------------------------


def _run_generation_pipeline(
    task_name,
    user_prompt,
    target_app,
    provider,
    model,
    temperature,
    prompt_name,
    conversation_history,
):
    """Background worker: executes the full generation pipeline."""
    task = frappe.get_doc("AI Generation Task", task_name)
    logger = frappe.logger("ai_studio")
    logger.info("[AI Generation Task %s] Pipeline started", task_name)

    task.started_at = frappe.utils.now()
    task.set_stage(STAGE_IN_PROGRESS, STAGE_PROGRESS[STAGE_IN_PROGRESS])

    # -------------------------------------------------------------------
    # Stage 1: LLM Call
    # -------------------------------------------------------------------
    try:
        from frappe_ai_studio.frappe_ai_studio.api import execute_prompt

        result = execute_prompt(
            prompt_name=prompt_name,
            user_prompt=user_prompt,
            target_app=target_app,
            provider=provider,
            model=model,
            temperature=temperature,
            conversation_history=conversation_history,
        )
        ai_response = result.get("response", "")
        logger.info("[AI Generation Task %s] LLM call succeeded", task_name)
    except Exception as e:
        logger.error("[AI Generation Task %s] LLM call failed: %s", task_name, str(e))
        task.set_failed(frappe.get_traceback())
        return

    # -------------------------------------------------------------------
    # Stage 2: Linting — parse JSON, validate change types, AST scan
    # -------------------------------------------------------------------
    task.set_stage(STAGE_LINTING, STAGE_PROGRESS[STAGE_LINTING])

    try:
        changes_payload = _extract_changes(ai_response)
        if changes_payload:
            _lint_changes(changes_payload, target_app)
        logger.info("[AI Generation Task %s] Linting passed", task_name)
    except Exception as e:
        logger.error("[AI Generation Task %s] Linting failed: %s", task_name, str(e))
        task.set_failed(frappe.get_traceback())
        return

    # -------------------------------------------------------------------
    # Stage 3: Testing — dry-run all changes in a transaction
    # -------------------------------------------------------------------
    task.set_stage(STAGE_TESTING, STAGE_PROGRESS[STAGE_TESTING])

    try:
        if changes_payload:
            _dry_run_changes(changes_payload, target_app)
        logger.info("[AI Generation Task %s] Dry-run passed", task_name)
    except Exception as e:
        logger.error("[AI Generation Task %s] Dry-run failed: %s", task_name, str(e))
        task.set_failed(frappe.get_traceback())
        return

    # -------------------------------------------------------------------
    # Stage 4: Completed — changes are staged, waiting for user approval
    # -------------------------------------------------------------------
    task.set_success(
        ai_response=ai_response,
        changes_payload=json.dumps(changes_payload) if changes_payload else None,
    )
    logger.info("[AI Generation Task %s] Pipeline completed successfully", task_name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_changes(ai_response):
    """Extract the JSON changes payload from the AI response text.

    Looks for ```json blocks first, then falls back to parsing the entire
    response as JSON.
    """
    import re

    m = re.search(r"```json\n([\s\S]*?)\n```", ai_response)
    if m:
        payload = json.loads(m.group(1))
    else:
        payload = json.loads(ai_response)

    if not payload or not isinstance(payload, dict):
        return None

    return payload.get("changes")


def _lint_changes(changes, target_app):
    """Validate all changes before dry-run.

    - Checks for unknown change types
    - Runs AST sanitizer on any Python code
    - Validates JSON payloads
    """
    from frappe_ai_studio.frappe_ai_studio.ast_sanitizer import validate_code_security

    if not isinstance(changes, list):
        raise ValueError("Changes must be a list")

    allowed_types = {
        "write",
        "inject_method",
        "update_json",
        "create_doctype",
        "sync_doctype",
        "run_bench",
        "custom_field",
        "property_setter",
        "server_script",
        "client_script",
        "workspace_link",
        "workspace_link_remove",
        "workspace_shortcut",
        "workspace_shortcut_remove",
    }

    for idx, change in enumerate(changes):
        ctype = change.get("type")
        if ctype not in allowed_types:
            raise ValueError("Unknown change type '{}' at index {}".format(ctype, idx))

        # AST security scan for Python code
        if ctype == "write" and change.get("relative_path", "").endswith(".py"):
            code = change.get("content", "")
            if code:
                ok, msg = validate_code_security(code)
                if not ok:
                    raise ValueError("Security violation in write change at index {}: {}".format(idx, msg))

        if ctype == "inject_method":
            code = change.get("method_code", "")
            if code:
                ok, msg = validate_code_security(code)
                if not ok:
                    raise ValueError("Security violation in inject_method at index {}: {}".format(idx, msg))

        if ctype == "server_script":
            code = change.get("script", "")
            if code:
                ok, msg = validate_code_security(code)
                if not ok:
                    raise ValueError("Security violation in server_script at index {}: {}".format(idx, msg))

        if ctype == "client_script":
            code = change.get("script", "")
            if code:
                ok, msg = validate_code_security(code)
                if not ok:
                    raise ValueError("Security violation in client_script at index {}: {}".format(idx, msg))


def _dry_run_changes(changes, target_app):
    """Execute all changes inside a database savepoint that is rolled back.

    This ensures structural integrity without persisting anything.
    """
    from frappe_ai_studio.frappe_ai_studio.transaction_guard import DryRunContext

    with DryRunContext():
        from frappe_ai_studio.frappe_ai_studio.api import apply_ai_changes
        apply_ai_changes(target_app, json.dumps(changes))


# ---------------------------------------------------------------------------
# Public API: deploy / reject
# ---------------------------------------------------------------------------


@frappe.whitelist()
def approve_and_deploy(task_name):
    """Apply the validated changes for real (outside a dry-run transaction).

    Called when the user clicks "Deploy" in the frontend.
    """
    task = frappe.get_doc("AI Generation Task", task_name)
    if task.status != STAGE_COMPLETED:
        frappe.throw(_("Task must be in 'Completed' state to deploy. Current state: {0}").format(task.status))

    changes = json.loads(task.changes_payload) if task.changes_payload else []
    if not changes:
        frappe.throw(_("No changes to deploy"))

    try:
        from frappe_ai_studio.frappe_ai_studio.api import apply_ai_changes
        result = apply_ai_changes(task.target_app, json.dumps(changes))
        return {"status": "deployed", "result": result}
    except Exception as e:
        frappe.throw(_("Deployment failed: {0}").format(str(e)))


@frappe.whitelist()
def reject_and_rollback(task_name):
    """Mark the task as rolled back. No database changes persist.

    Called when the user clicks "Reject" in the frontend.
    """
    task = frappe.get_doc("AI Generation Task", task_name)
    if task.status not in (STAGE_COMPLETED, STAGE_FAILED):
        frappe.throw(_("Task must be in 'Completed' or 'Failed' state to reject. Current state: {0}").format(task.status))

    task.set_rolled_back()
    return {"status": "rolled_back"}


@frappe.whitelist()
def get_generation_task_status(task_name):
    """Return the current status of a generation task."""
    task = frappe.get_doc("AI Generation Task", task_name)
    return {
        "task_id": task.name,
        "status": task.status,
        "progress_percent": task.progress_percent,
        "current_stage": task.current_stage,
        "ai_response": task.ai_response,
        "changes_payload": task.changes_payload,
        "error_trace": task.error_trace,
        "started_at": str(task.started_at) if task.started_at else None,
        "completed_at": str(task.completed_at) if task.completed_at else None,
        "duration_seconds": task.duration_seconds,
    }
