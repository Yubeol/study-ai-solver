"""평가 질문 일부를 실행 중인 서버의 질의 API(POST /qa)로 돌려 답변을 저장한다.

Gemini 무료 한도 때문에 질문 id를 골라서 돌린다(전체 실행 금지).

    cd backend
    uv run uvicorn app.main:app            # 다른 창에서 서버 실행(모델 로딩 약 1분)
    uv run python -m app.qa.sample_run --ids c06,c09,n08,a01
    uv run python -m app.qa.sample_run --ids c06 --url http://127.0.0.1:8000

결과: {REPORTS_DIR}/answers/{시각}.json(응답 전체) + .md(질문·판정·답변·인용 근거 raw_text).
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.ingestion.team_import import load_map
from app.retrieval.evaluate import parse_questions

MAX_IDS = 12  # 한 번에 돌릴 최대 질문 수(Gemini 무료 한도 보호)


def to_markdown(items: list[dict]) -> str:
    lines = ["# 질의 API 샘플 실행", ""]
    for it in items:
        q, r = it["question"], it["response"]
        lines += [f"## {q['id']} — {q['question']}", ""]
        gold = f"{q['subject']} {'|'.join(q['pages'])}쪽" if q["pages"] else "자료에 없는 질문"
        lines.append(f"- 정답 쪽(평가 세트): {gold}")
        if "error" in it:
            lines += [f"- 요청 실패: {it['error']}", ""]
            continue
        s, t = r["scores"], r["timings_ms"]
        lines.append(f"- 판정: zone=`{r['zone']}`({r['zone_reason']}) / status=`{r['status']}` / "
                     f"confidence={r.get('confidence')} / 확신 낮음={r['low_confidence']}")
        lines.append(f"- 점수: 벡터 1위 {s['vector_top']} / 리랭커 1위 {s['rerank_top']}")
        lines.append("- 시간(ms): " + ", ".join(f"{k}={v}" for k, v in t.items()))
        llm = r.get("llm") or {}
        if llm.get("model"):
            lines.append(f"- 모델: {llm['model']} / 인용 검증: {json.dumps(llm.get('citation_check'), ensure_ascii=False)}")
        if llm.get("failed_attempts"):
            lines.append(f"- 실패한 시도: {json.dumps(llm['failed_attempts'], ensure_ascii=False)}")
        lines += ["", f"**답**: {r['answer']}", ""]
        if r.get("explanation"):
            lines += [f"**설명**: {r['explanation']}", ""]
        if r.get("confusions"):
            lines += [f"**헷갈리는 개념**: {r['confusions']}", ""]
        lines.append("**넘긴 근거**: " + ", ".join(
            f"[{e['n']}] {e['book_title']} {e['page']}쪽(리랭커 {e['rerank_score']}){' ✔' if e['cited'] else ''}"
            for e in r["evidence"]))
        lines.append("")
        for c in r["citations"]:
            raw = c["raw_text"].strip().replace("\n", "\n> ")
            lines += [f"**인용 [{c['n']}]** {c['book_title']} {c['page']}쪽 · {c['path']}", "", f"> {raw}", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="평가 질문 일부를 /qa로 실행")
    ap.add_argument("--ids", required=True, help="질문 id(쉼표 구분)")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--questions", default=None, help="질문 CSV(기본 EVAL_QUESTIONS_PATH)")
    args = ap.parse_args(argv)

    settings = get_settings()
    ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    if len(ids) > MAX_IDS:
        print(f"질문은 한 번에 {MAX_IDS}개까지(Gemini 무료 한도)")
        return 2
    path = args.questions or settings.eval_questions_file
    subject_keys = {c["key"] for c in load_map(settings)["books"]}
    qs = {q.id: q for q in parse_questions(Path(path).read_text(encoding="utf-8"), subject_keys)}
    missing = [i for i in ids if i not in qs]
    if missing:
        print(f"질문 파일에 없는 id: {', '.join(missing)}")
        return 2

    items = []
    with httpx.Client(base_url=args.url, timeout=300) as client:
        for i in ids:
            q = qs[i]
            item = {"question": {"id": q.id, "question": q.question, "subject": q.subject, "pages": q.pages}}
            try:
                resp = client.post("/qa", json={"question": q.question})
                resp.raise_for_status()
                item["response"] = resp.json()
                r = item["response"]
                print(f"{q.id}: {r['zone']}/{r['status']} 인용 {[c['n'] for c in r['citations']]} "
                      f"{r['timings_ms']['total_ms']}ms")
            except httpx.HTTPError as e:
                item |= {"response": None, "error": f"{type(e).__name__}: {e}"}
                print(f"{q.id}: 실패 {item['error']}")
            items.append(item)

    out_dir = settings.reports_path / "answers"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out_dir / f"{stem}.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / f"{stem}.md").write_text(to_markdown(items), encoding="utf-8")
    print(f"저장: {out_dir / stem}.json / .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
