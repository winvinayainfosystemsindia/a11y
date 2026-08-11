"""
AI Audit Agent (Phase 2).

Runs the Perceive -> Plan -> Execute -> Reflect -> Learn loop for a single
crawled page. `agent.py` is the *only* entry point the rest of the app
(controllers) is allowed to import from this package - everything else here
(planner, executor, reflector, memory/, tools/, prompts/) is an internal
collaborator agent.py wires together. See app/ai/agent.py for the full flow.
"""
