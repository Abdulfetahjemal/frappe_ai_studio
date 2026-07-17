# -*- coding: utf-8 -*-
"""Agent Orchestrator — asynchronous generation pipeline with state management.

PILLAR 1: ASYNCHRONOUS AGENT ORCHESTRATION & STATE MANAGEMENT
- Uses frappe.enqueue for background task execution
- Tracks state via AI Generation Task DocType
- Streams progress via frappe.publish_realtime (Socketio)
"""

from __future__ import unicode_literals

import json

import frappe
from frappe import _

# ---------------------------------------------------------------------------
# Stage constants
# ---------------------------------------------------------------------------

STAGE_PENDING = "Pending"
STAGE_PLANNING = "Planning"
STAGE_AWAITING_APPROVAL = "Awaiting Approval"
STAGE_IN_PROGRESS = "In Progress"
STAGE_LINTING = "Linting"
STAGE_TESTING = "Testing"
STAGE_COMPLETED = "Completed"
STAGE_FAILED = "Failed"
STAGE_ROLLED_BACK = "Rolled Back"

STAGE_PROGRESS = {
    STAGE_PENDING: 0,
    STAGE_PLANNING: 15,
    STAGE_AWAITING_APPROVAL: 30,
    STAGE_IN_PROGRESS: 45,
    STAGE_LINTING: 60,
    STAGE_TESTING: 80,
    STAGE_COMPLETED: 100,
    STAGE_FAILED: 0,
    STAGE_ROLLED_BACK: 0,
}

# ---------------------------------------------------------------------------
# Public API: enqueue a new generation task
# ---------------------------------------------------------------------------


def enqueue_generation_task(
    user_prompt,
    target_app=None,
    provider=None,
    model=None,
    temperature=None,
    prompt_name="__direct__",
    conversation_history=None,
    planning=False,
):
    """Create an AI Generation Task and enqueue it for background processing.

    When ``planning`` is true the task first produces a human-readable PLAN and
    pauses at 'Awaiting Approval' — nothing is generated or executed until the
    user approves the plan via ``approve_plan``.

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
            "planning_mode": 1 if planning else 0,
        }
    )
    task.insert(ignore_permissions=True)
    frappe.db.commit()

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
        planning=planning,
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
    planning=False,
    approved_plan=None,
):
    """Background worker: executes the generation pipeline.

    If ``planning`` is true and no ``approved_plan`` is supplied, only a PLAN is
    produced and the task pauses at 'Awaiting Approval'. Once the user approves,
    ``approve_plan`` re-enqueues this with the approved plan to implement it.
    """
    task = frappe.get_doc("AI Generation Task", task_name)
    logger = frappe.logger("ai_studio")
    logger.info("[AI Generation Task %s] Pipeline started (planning=%s)", task_name, planning)

    if not task.started_at:
        task.started_at = frappe.utils.now()

    # -------------------------------------------------------------------
    # Stage 0: Planning — produce a plan and pause for explicit approval.
    # -------------------------------------------------------------------
    if planning and not approved_plan:
        task.set_stage(STAGE_PLANNING, STAGE_PROGRESS[STAGE_PLANNING])
        try:
            from frappe_ai_studio.frappe_ai_studio.api import execute_prompt

            result = execute_prompt(
                prompt_name="__plan__",
                user_prompt=user_prompt,
                target_app=target_app,
                provider=provider,
                model=model,
                temperature=temperature,
                conversation_history=conversation_history,
            )
            plan = _extract_plan(result.get("response", ""))
            task.set_plan_ready(json.dumps(plan))
            logger.info("[AI Generation Task %s] Plan ready — awaiting approval", task_name)
        except Exception as e:
            logger.error("[AI Generation Task %s] Planning failed: %s", task_name, str(e))
            task.set_failed(frappe.get_traceback())
        return

    task.set_stage(STAGE_IN_PROGRESS, STAGE_PROGRESS[STAGE_IN_PROGRESS])

    # If an approved plan is supplied, instruct the model to implement it exactly.
    effective_prompt = user_prompt
    if approved_plan:
        effective_prompt = (
            "{}\n\n## APPROVED PLAN — implement EXACTLY these steps as a single "
            "ordered changes[] array, in order:\n{}".format(user_prompt, approved_plan)
        )

    # -------------------------------------------------------------------
    # Stage 1: LLM Call
    # -------------------------------------------------------------------
    try:
        from frappe_ai_studio.frappe_ai_studio.api import execute_prompt

        result = execute_prompt(
            prompt_name=prompt_name,
            user_prompt=effective_prompt,
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
    # Stage 3: Testing — static, side-effect-free validation of all changes
    # -------------------------------------------------------------------
    task.set_stage(STAGE_TESTING, STAGE_PROGRESS[STAGE_TESTING])

    try:
        if changes_payload:
            _validate_changes(changes_payload, target_app)
        logger.info("[AI Generation Task %s] Validation passed", task_name)
    except Exception as e:
        logger.error("[AI Generation Task %s] Validation failed: %s", task_name, str(e))
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

    Tolerant by design: a conversational reply with no change payload is a
    valid outcome (returns ``None``), not an error. Tries, in order:
    a fenced ```json block, any fenced ``` block, then the whole response.
    """
    import re

    if not ai_response or not ai_response.strip():
        return None

    candidates = []
    # 1. ```json fenced block (allow optional language + flexible whitespace)
    for m in re.finditer(r"```(?:json)?\s*\n([\s\S]*?)```", ai_response, re.IGNORECASE):
        candidates.append(m.group(1).strip())
    # 2. The whole response as a last resort.
    candidates.append(ai_response.strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(payload, dict) and "changes" in payload:
            changes = payload.get("changes")
            return changes if isinstance(changes, list) else None

    # No structured change payload — this was a conversational answer.
    return None


def _extract_plan(ai_response):
    """Extract a structured plan from the planning LLM response.

    Returns a dict: {"summary": str, "steps": [ {"step", "action", "risk",
    "requires_approval", "detail"} ... ]}. Falls back to a single free-text
    step if the model didn't return JSON.
    """
    import re

    if not ai_response or not ai_response.strip():
        return {"summary": "", "steps": []}

    candidates = []
    for m in re.finditer(r"```(?:json)?\s*\n([\s\S]*?)```", ai_response, re.IGNORECASE):
        candidates.append(m.group(1).strip())
    candidates.append(ai_response.strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(payload, dict) and payload.get("steps"):
            return payload

    # Fallback: keep the prose as a single informational step.
    return {"summary": ai_response.strip()[:2000], "steps": []}


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
        # Code & schema
        "write",
        "inject_method",
        "update_json",
        "create_doctype",
        "sync_doctype",
        "run_bench",
        # Core-app customization
        "custom_field",
        "property_setter",
        "server_script",
        "client_script",
        "workspace_link",
        "workspace_link_remove",
        "workspace_shortcut",
        "workspace_shortcut_remove",
        # Bench-level (senior developer)
        "create_app",
        "install_app",
        "create_module",
        # Advanced customization (senior developer)
        "workflow",
        "workflow_state",
        "workflow_action",
        "create_workspace",
        "report",
        "notification",
        "dashboard_chart",
        "number_card",
        "role",
        "permission",
        "print_format",
        "web_form",
    }

    for idx, change in enumerate(changes):
        ctype = change.get("type")
        if ctype not in allowed_types:
            raise ValueError("Unknown change type '{}' at index {}".format(ctype, idx))

        # Script Report code is executed server-side — scan it.
        if ctype == "report":
            _d = change.get("definition") or change
            if _d.get("report_type") == "Script Report" and _d.get("report_script"):
                ok, msg = validate_code_security(_d.get("report_script"))
                if not ok:
                    raise ValueError("Security violation in report script at index {}: {}".format(idx, msg))

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


def _validate_changes(changes, target_app):
    """Statically validate all changes without any side effects.

    Replaces the old savepoint "dry run", which actually wrote files to disk
    because DB savepoints cannot roll back filesystem or DDL operations.
    """
    from frappe_ai_studio.frappe_ai_studio.api import validate_changes

    return validate_changes(target_app, changes)


# Backwards-compatible alias (older imports referenced _dry_run_changes).
_dry_run_changes = _validate_changes


# ---------------------------------------------------------------------------
# Public API: deploy / reject
# ---------------------------------------------------------------------------


@frappe.whitelist()
def approve_plan(task_name, provider=None, model=None, temperature=None, conversation_history=None):
    """Approve a generated plan and start implementing it.

    Re-enqueues the generation pipeline with the approved plan so the model
    produces the actual changes (which then still pass through validation and
    the Deploy gate before anything executes).
    """
    from frappe_ai_studio.frappe_ai_studio.api import _guard

    _guard()
    task = frappe.get_doc("AI Generation Task", task_name)
    if task.status != STAGE_AWAITING_APPROVAL:
        frappe.throw(
            _("Task must be in 'Awaiting Approval' state to approve. Current state: {0}").format(task.status)
        )

    task.set_stage(STAGE_IN_PROGRESS, STAGE_PROGRESS[STAGE_IN_PROGRESS])

    frappe.enqueue(
        method="frappe_ai_studio.frappe_ai_studio.agent_orchestrator._run_generation_pipeline",
        queue="long",
        timeout=300,
        job_id=f"ai-gen-impl-{task.name}",
        task_name=task.name,
        user_prompt=task.user_request,
        target_app=task.target_app or None,
        provider=provider,
        model=model,
        temperature=temperature,
        prompt_name="__direct__",
        conversation_history=conversation_history,
        planning=False,
        approved_plan=task.plan,
    )
    return {"status": "approved", "task_id": task.name}


@frappe.whitelist()
def reject_plan(task_name):
    """Reject a generated plan; nothing is implemented."""
    from frappe_ai_studio.frappe_ai_studio.api import _guard

    _guard()
    task = frappe.get_doc("AI Generation Task", task_name)
    if task.status != STAGE_AWAITING_APPROVAL:
        frappe.throw(
            _("Task must be in 'Awaiting Approval' state to reject. Current state: {0}").format(task.status)
        )
    task.set_rolled_back()
    return {"status": "rolled_back"}


@frappe.whitelist()
def approve_and_deploy(task_name, confirm_high_risk=False):
    """Apply the validated changes for real.

    High-impact operations (app scaffolding, bench commands, permission/role
    changes, workflows, core-app edits) must be explicitly confirmed:
    ``confirm_high_risk`` must be truthy or the call is refused with the list of
    high-risk items so the UI can prompt the user first.

    Called when the user clicks "Deploy" in the frontend.
    """
    from frappe_ai_studio.frappe_ai_studio.api import _guard
    from frappe_ai_studio.frappe_ai_studio.risk import summarize_risk

    _guard()
    task = frappe.get_doc("AI Generation Task", task_name)
    if task.status != STAGE_COMPLETED:
        frappe.throw(_("Task must be in 'Completed' state to deploy. Current state: {0}").format(task.status))

    changes = json.loads(task.changes_payload) if task.changes_payload else []
    if not changes:
        frappe.throw(_("No changes to deploy"))

    # Enforce explicit approval for high-risk changes before executing.
    summary = summarize_risk(changes, app_name=task.target_app or None)
    confirmed = str(confirm_high_risk).lower() in ("1", "true", "yes")
    if summary["requires_approval"] and not confirmed:
        labels = ", ".join(it["label"] for it in summary["high_risk"])
        frappe.throw(
            _(
                "This deployment includes high-impact changes that need explicit "
                "confirmation: {0}. Re-run Deploy with confirmation to proceed."
            ).format(labels),
            frappe.PermissionError if hasattr(frappe, "PermissionError") else None,
        )

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
    from frappe_ai_studio.frappe_ai_studio.api import _guard

    _guard()
    task = frappe.get_doc("AI Generation Task", task_name)
    if task.status not in (STAGE_COMPLETED, STAGE_FAILED):
        frappe.throw(
            _("Task must be in 'Completed' or 'Failed' state to reject. Current state: {0}").format(
                task.status
            )
        )

    task.set_rolled_back()
    return {"status": "rolled_back"}


@frappe.whitelist()
def get_generation_task_status(task_name):
    """Return the current status of a generation task."""
    from frappe_ai_studio.frappe_ai_studio.api import _guard

    _guard()
    task = frappe.get_doc("AI Generation Task", task_name)

    plan = None
    if task.plan:
        try:
            plan = json.loads(task.plan)
        except (ValueError, TypeError):
            plan = {"summary": task.plan, "steps": []}

    risk = None
    if task.changes_payload:
        try:
            from frappe_ai_studio.frappe_ai_studio.risk import summarize_risk

            risk = summarize_risk(json.loads(task.changes_payload), app_name=task.target_app or None)
        except Exception:
            risk = None

    return {
        "task_id": task.name,
        "status": task.status,
        "progress_percent": task.progress_percent,
        "current_stage": task.current_stage,
        "planning_mode": task.planning_mode,
        "plan": plan,
        "risk_level": task.risk_level,
        "requires_approval": task.requires_approval,
        "risk": risk,
        "ai_response": task.ai_response,
        "changes_payload": task.changes_payload,
        "error_trace": task.error_trace,
        "started_at": str(task.started_at) if task.started_at else None,
        "completed_at": str(task.completed_at) if task.completed_at else None,
        "duration_seconds": task.duration_seconds,
    }
