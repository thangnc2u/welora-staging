"""Test helper (GP P0b): answer a served KUAT attempt the way a learner who knows the lesson does —
match each served question to the bank by its prompt and pick the option TEXT that is right
(the served option order is shuffled per attempt)."""

from __future__ import annotations

from welora import academy


def solve(node_id: str, questions: list[dict], *, correct: bool = True) -> list[dict]:
    bank = {q["prompt"]: q for q in academy.QUESTIONS[node_id]}
    out = []
    for q in questions:
        b = bank[q["prompt"]]
        right = q["choices"].index(b["choices"][b["answer"]])
        out.append({"question_id": q["id"], "choice": right if correct else (right + 1) % len(q["choices"])})
    return out


def pass_kuat_http(c, uid: str, headers: dict, node_id: str, *, correct: bool = True):
    """read → start attempt → submit. Returns (status, passed, response json)."""
    c.post(f"/academy/nodes/{node_id}/read", json={"user_id": uid, "node_id": node_id}, headers=headers)
    st = c.post("/academy/kuat/start", json={"user_id": uid, "node_id": node_id}, headers=headers)
    if st.status_code != 200:
        return st.status_code, None, st.json()
    a = st.json()
    r = c.post("/academy/kuat", json={"user_id": uid, "node_id": node_id, "attempt_id": a["attempt_id"],
                                      "answers": solve(node_id, a["questions"], correct=correct)}, headers=headers)
    return r.status_code, (r.json().get("kuat_result") or {}).get("passed"), r.json()
