"""Interview agent (DSC-005): deterministic state machine, injected extraction port.

The agent asks the questions of the template question list (questions.json), in Arabic or English,
extracts structured answers through an injected model port and validates every value itself. The
model output and every owner or document text are untrusted data. Output is a Blueprint-draft input;
the agent never writes a Blueprint, and values read from documents stay `proposed` until the owner
confirms them (agents draft, humans approve).
"""
from .agent import Interviewer, InterviewError, Prompt, TurnResult
from .catalog import Catalog, Question, load_catalog
from .session import InMemoryStore, Session

__all__ = ["Interviewer", "InterviewError", "Prompt", "TurnResult", "Catalog", "Question",
           "load_catalog", "InMemoryStore", "Session"]
