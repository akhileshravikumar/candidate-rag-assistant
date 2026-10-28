import re

from app.models import Answer, Unknown
from app.privacy import ATTACK, SENSITIVE, blocked_question, redact
from app.retrieval import retrieve
import logging

logger = logging.getLogger(__name__)

NOTICE = "Advisory evidence only. A hiring manager must verify it and make the decision."
MESSAGES = {
    "answered": "Evidence-based answer; inspect the citations and unknowns.",
    "abstained": "Insufficient validated evidence to answer. This does not establish lack of skill.",
    "refused": "Use job-relevant evidence only; personal attributes and final automated decisions are out of scope.",
}


class InputError(ValueError):
    pass


def empty_answer(status="abstained"):
    return Answer(status=status, findings=[], unknowns=[], shortlist=[])


def valid_citation(citation, candidate_id, evidence):
    chunk = next((c for c in evidence if c["id"] == citation.chunk_id), None)
    return bool(
        chunk and chunk["candidate_id"] == candidate_id
        and len(citation.quote.strip()) >= 12
        and citation.quote in chunk["text"]
    )


def validate_answer(answer, evidence, allowed_ids, criteria, mode, aliases):
    if answer.status == "refused":
        if answer.findings or answer.unknowns or answer.shortlist:
            raise ValueError("Refusal must have no candidate claims.")
        return
    for finding in answer.findings:
        if finding.candidate_id not in allowed_ids or not finding.text.strip():
            raise ValueError("Invalid candidate or claim.")
        if not finding.citations or not all(
            valid_citation(c, finding.candidate_id, evidence) for c in finding.citations
        ):
            raise ValueError("Unsupported citation.")
        if not finding.requirement_ids or not set(finding.requirement_ids) <= criteria:
            raise ValueError("Unknown requirement.")
    for unknown in answer.unknowns:
        if unknown.candidate_id not in allowed_ids or not 1 <= len(unknown.topic) <= 160:
            raise ValueError("Invalid unknown.")
    serialized = answer.model_dump_json()
    if redact(serialized, aliases) != serialized or SENSITIVE.search(serialized) or ATTACK.search(serialized):
        raise ValueError("Unsafe output.")
    if answer.status == "answered" and not answer.findings:
        raise ValueError("Answered without evidence.")
    if answer.status == "abstained" and (answer.findings or answer.shortlist):
        raise ValueError("Abstention must not claim an answer.")
    supported = {f.candidate_id for f in answer.findings}
    if (len(answer.shortlist) > 3 or len(set(answer.shortlist)) != len(answer.shortlist)
            or not set(answer.shortlist) <= supported):
        raise ValueError("Unsupported shortlist.")
    if mode == "qa" and answer.shortlist:
        raise ValueError("Unexpected shortlist.")
    if mode == "shortlist" and answer.status == "answered" and not answer.shortlist:
        raise ValueError("No proposed shortlist.")


class Service:
    def __init__(self, store, gateway):
        self.store, self.gateway = store, gateway

    def ask(self, request, extra_evidence=None):
        # extra_evidence is an internal evaluation seam, never an HTTP parameter.
        if blocked_question(request.question):
            return self.package(empty_answer("refused"), [], [], "policy")
        self.store.ready()
        aliases = self.store.aliases()
        question = redact(request.question.strip(), aliases)
        if len(question) < 3:
            raise InputError("Enter a question.")
        known = self.store.candidates()
        mentioned = set(re.findall(r"\bCAND-\d{3}\b", question, re.I))
        mentioned = {x.upper() for x in mentioned}
        ids = sorted(set(request.candidate_ids) | mentioned)
        if not set(ids) <= set(known):
            raise InputError("Unknown candidate ID. Use the candidate list.")
        if request.mode == "shortlist" and ids:
            raise InputError("Clear candidate selection for an all-candidate shortlist.")
        criteria = self.store.criteria()
        if request.mode == "shortlist":
            evidence = self.store.all_evidence()
            strategy = "all_candidate_sections"
        else:
            evidence = retrieve(self.store, self.gateway, question, ids)
            strategy = "per_candidate_top4" if ids else "global_top8"
        if extra_evidence:
            # Exercise the downstream guardrail with malicious retrieved content.
            evidence = evidence + extra_evidence
        allowed = known if request.mode == "shortlist" or not ids else ids
        if not evidence:
            return self.package(empty_answer(), evidence, criteria, strategy)
        payload = {
            "mode": request.mode, "question": question,
            "candidate_scope": allowed, "jd_criteria": criteria,
            "untrusted_resume_evidence": evidence,
        }
        answer = self.gateway.answer(payload)
        try:
            validate_answer(answer, evidence, set(allowed),
                            {c["section"] for c in criteria}, request.mode, aliases)
        except ValueError as exc:
            logger.warning("Answer validation failed: %s", exc)
            return self.package(empty_answer(), evidence, criteria, strategy,
                                validation_failed=True)
        if answer.status != "refused":
            covered = {f.candidate_id for f in answer.findings} | {
                u.candidate_id for u in answer.unknowns
            }
            for candidate_id in ids:
                if candidate_id not in covered:
                    answer.unknowns.append(Unknown(
                        candidate_id=candidate_id, topic="Evidence addressing this question"
                    ))
        return self.package(answer, evidence, criteria, strategy)

    @staticmethod
    def package(answer, evidence, criteria, strategy, validation_failed=False):
        return {
            **answer.model_dump(), "message": MESSAGES[answer.status],
            "notice": NOTICE, "evidence": evidence, "jd_criteria": criteria,
            "retrieval_strategy": strategy, "validation_failed": validation_failed,
        }