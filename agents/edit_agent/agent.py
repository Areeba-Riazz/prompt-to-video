"""
Edit Agent — agent.py
Contains the ScriptValidator and the HITL (Human-in-the-Loop) node.
Sourced from the old agents/validation_worker.py and the hitl_node in graph.py.

LangGraph node functions exported:
    validator_node(state) -> MontageState
    hitl_node(state)      -> MontageState
"""

import os
import re

from shared.schemas.state import MontageState, Scene


# ─────────────────────────────────────────────────────────────────────────────
# Script Validator
# ─────────────────────────────────────────────────────────────────────────────

class ScriptValidator:
    """
    Validates the structure of scripts (manual or generated).
    Checks for Scene Headings, Dialogue Labels, and Action Descriptions.
    """

    def validate(self, state: MontageState) -> MontageState:
        print("--- [Validator] Checking script structure ---")
        script_text = state.get("raw_script", "")
        errors = []

        # 1. Check Scene Headings (e.g., INT. or EXT.)
        if not re.search(r"(INT\.|EXT\.)", script_text, re.IGNORECASE):
            errors.append("Missing Scene Headings (INT. or EXT.)")

        # 2. Check Dialogue Labels (e.g., KAEL: ...)
        if not re.search(r"^[A-Z][A-Z\s]{1,30}:\s+.+$", script_text, re.MULTILINE):
            errors.append("Missing Dialogue Labels (e.g., KAEL: ...)")

        # 3. Check Action Description lines enclosed in brackets [ ... ]
        if not re.search(r"^\[.+\]$", script_text, re.MULTILINE):
            errors.append("Missing Action Descriptions ([ ... ])")

        if errors:
            state["status"] = "failed"
            state["errors"] = errors
            print("--- [Validator] Validation failed ---")
            for err in errors:
                print(f"  - {err}")
            print("--- [Validator] Suggested fix template ---")
            print("INT. LOCATION - TIME")
            print("[Action description line]")
            print("CHARACTER: Dialogue line")
        else:
            state["status"] = "validated"
            # Script is already in state['raw_script'] or state['scenes'] from previous node or upload


        state["current_agent"] = "Validator"
        return state


# ─────────────────────────────────────────────────────────────────────────────
# HITL Node
# ─────────────────────────────────────────────────────────────────────────────

def hitl_node(state: MontageState) -> MontageState:
    """Human-in-the-Loop checkpoint for the backend."""
    print("\n--- [HITL] WAITING FOR HUMAN REVIEW ---")
    
    approved = state.get("hitl_approved")
    
    if approved is False:
        # Explicit rejection by user
        print("--- [HITL] Script explicitly rejected ---")
        return {
            "status": "failed",
            "errors": state.get("errors", []) + ["Script rejected by user."],
            "current_agent": "HITL",
        }

    if approved is True:
        print("--- [HITL] Review approved: proceeding to synthesis ---")
        return {"current_agent": "HITL"}

    # If it's None (waiting), we don't set status to failed
    return {"current_agent": "HITL"}


# ─────────────────────────────────────────────────────────────────────────────
# LangGraph node functions
# ─────────────────────────────────────────────────────────────────────────────

def validator_node(state: MontageState) -> MontageState:
    return ScriptValidator().validate(state)
