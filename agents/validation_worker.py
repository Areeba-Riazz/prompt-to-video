from schema.state import MontageState, Scene
import re

class ScriptValidator:
    """
    Validates the structure of scripts (manual or generated).
    Checks for Scene Headings, Dialogue Labels, and Action Descriptions.
    """
    def validate(self, state: MontageState) -> MontageState:
        print(f"--- [Validator] Checking script structure ---")
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
            # In a real scenario, this would parse the text into Scene objects
            # For now, we'll simulate a valid parse
            state["scenes"] = [
                Scene(
                    scene_id=1, 
                    location="City Street", 
                    characters=["A", "B"], 
                    dialogue=[{"speaker": "A", "line": "Hello", "visual_cue": "Close-up"}]
                )
            ]
            
        state["current_agent"] = "Validator"
        return state

def validator_node(state: MontageState):
    return ScriptValidator().validate(state)
