from agents.orchestrator.graph_phase1 import montage_workflow
from shared.utils.output_generator import save_outputs
import os
from dotenv import load_dotenv

# Load API keys from .env file
load_dotenv()

def run_project_montage(user_input: str, mode: str = "auto"):
    """
    Main entry point for PROJECT MONTAGE - Phase 1.
    """
    print(f"=== PROJECT MONTAGE: PHASE 1 STARTING ({mode}) ===")
    
    # Initialize initial state
    initial_state = {
        "user_prompt": user_input if mode == "auto" else "",
        "raw_script": user_input if mode == "manual" else "",
        "input_mode": mode,
        "status": "processing",
        "errors": [],
        "current_agent": "Entry",
        "scenes": [],
        "characters": []
    }

    # Compile and run the LangGraph workflow
    app = montage_workflow()
    final_output = app.invoke(initial_state)

    # Save results
    save_outputs(final_output)
    
    print(f"=== PROJECT MONTAGE: COMPLETED SUCCESSFULLY ===")
    print(f"Deliverables generated in './output/'")

if __name__ == "__main__":
    # Example: Autonomous generation
    sample_prompt = "A high-stakes heist in a rainy neon-lit megacity where the protagonist discovers the prize is a digital ghost."
    run_project_montage(sample_prompt, mode="auto")
